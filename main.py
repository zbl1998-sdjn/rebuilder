"""
ReBuilder - Cleanroom Program Reconstruction Framework
Entry point for running ProgramBench tasks.

Usage:
    python main.py --task examples/mock_task --provider kimi
    python main.py --task /path/to/programbench/task --provider glm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.meta_controller import MetaController
from core.execution import DockerExecutable, DockerExecutorBackend, WSLExecutorBackend
from core.programbench.documentation import load_documentation
from core.session import RunSession
from llm_clients.factory import create_llm_client, load_config

console = Console()


def _coerce_non_negative_int(name: str, value) -> int:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    if not parsed.is_integer():
        raise ValueError(f"{name} must be a non-negative integer")
    return int(parsed)


def _non_negative_int(value: str) -> int:
    try:
        return _coerce_non_negative_int("value", value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def print_banner():
    console.print(Panel(banner_text(), style="bold cyan"))


def banner_text() -> str:
    return (
        "+----------------------------------------------+\n"
        "|  ReBuilder Framework                         |\n"
        "|  Cleanroom Program Reconstruction Agent      |\n"
        "+----------------------------------------------+"
    )


def parse_args():
    parser = argparse.ArgumentParser(description="ReBuilder: Reconstruct programs from binaries")
    parser.add_argument("--task", required=True, help="Path to task directory containing executable and documentation")
    parser.add_argument(
        "--provider",
        choices=["glm", "kimi", "local_openai", "file_bridge"],
        default=None,
        help="Override LLM provider",
    )
    parser.add_argument("--config", default="config/settings.yaml", help="Path to config file")
    parser.add_argument("--output", default=None, help="Output directory for generated code")
    parser.add_argument("--max-repairs", type=_non_negative_int, default=None, help="Maximum repair iterations")
    parser.add_argument("--probe-iterations", type=_non_negative_int, default=None, help="Maximum probe planning iterations")
    parser.add_argument("--min-probe-samples", type=_non_negative_int, default=None, help="Minimum behavior samples to collect")
    parser.add_argument(
        "--reference-docker-image",
        default=None,
        help="Run the reference executable from this task_cleanroom Docker image",
    )
    parser.add_argument(
        "--reference-executable",
        default="/workspace/executable",
        help="Path to executable inside --reference-docker-image",
    )
    parser.add_argument(
        "--replacement-executor",
        choices=["local", "wsl"],
        default=None,
        help="Run generated replacement locally or through WSL during differential testing",
    )
    parser.add_argument(
        "--static-output-assets",
        choices=["config", "enabled", "disabled"],
        default="config",
        help="Override implementation.static_output_assets for ablation runs",
    )
    parser.add_argument(
        "--adaptive-probes",
        choices=["config", "enabled", "disabled"],
        default="config",
        help="Override probe.adaptive_probes for ablation runs",
    )
    parser.add_argument(
        "--adaptive-probe-exclude-domain",
        action="append",
        default=[],
        help=(
            "Exclude a task-profile domain from deterministic adaptive probes; "
            "repeatable for restore-axis ablations."
        ),
    )
    return parser.parse_args()


def load_task(task_path: Path) -> tuple[Path, str]:
    """Load executable and documentation from task directory."""
    if not task_path.exists():
        raise FileNotFoundError(f"Task path not found: {task_path}")
    
    # Look for executable. ProgramBench uses execute-only binaries, while the
    # local mock task may use a Python script or batch wrapper on Windows.
    executable = None
    candidates = [
        task_path / "executable",
        task_path / "program",
        task_path / "program.py",
        task_path / "program.bat",
        task_path / "program.cmd",
        task_path / "program.exe",
        task_path / "a.out",
    ]
    for candidate in candidates:
        if candidate.exists():
            executable = candidate
            break
    
    if executable is None:
        # Try any likely executable file.
        for f in task_path.iterdir():
            if f.is_file() and (not f.suffix or f.suffix in {".py", ".bat", ".cmd", ".exe"}):
                executable = f
                break
    
    if executable is None:
        raise FileNotFoundError(f"No executable found in {task_path}")
    
    documentation = load_documentation(task_path)
    if not documentation:
        console.print("[yellow]Warning: No documentation found in task directory[/yellow]")
    
    return executable.resolve(strict=False), documentation


def discover_run_session(task_path: Path) -> RunSession | None:
    """Load a prepared run session when task_path points at its workspace directory."""
    path = Path(task_path).resolve(strict=False)
    session_root = path.parent if path.name == "workspace" else path
    manifest = session_root / "session.json"
    if manifest.exists():
        return RunSession.load(session_root)
    return None


def build_reference_executable_and_backend(args):
    """Build optional Docker reference execution objects from CLI args."""
    if not getattr(args, "reference_docker_image", None):
        return None, None
    executable = DockerExecutable(
        image=args.reference_docker_image,
        executable_path=getattr(args, "reference_executable", "/workspace/executable"),
    )
    return executable, DockerExecutorBackend()


def build_replacement_executor_backend(config: dict, args):
    """Build optional backend for executing generated replacements."""
    selected = getattr(args, "replacement_executor", None)
    if selected is None:
        selected = config.get("execution", {}).get("replacement_backend", "local")
    if selected == "wsl":
        return WSLExecutorBackend()
    return None


def build_controller(
    llm_client,
    config: dict,
    args,
    run_session: RunSession | None = None,
    reference_executor_backend=None,
) -> MetaController:
    """Create the pipeline controller from YAML config plus CLI overrides."""
    probe_cfg = config.get("probe", {})
    architect_cfg = config.get("architect", {})
    controller_cfg = config.get("controller", {})
    implementation_cfg = config.get("implementation", {})
    differential_cfg = config.get("differential", {})
    static_output_assets = implementation_cfg.get("static_output_assets", True)
    adaptive_probes = probe_cfg.get("adaptive_probes", True)
    if getattr(args, "static_output_assets", "config") == "enabled":
        static_output_assets = True
    elif getattr(args, "static_output_assets", "config") == "disabled":
        static_output_assets = False
    if getattr(args, "adaptive_probes", "config") == "enabled":
        adaptive_probes = True
    elif getattr(args, "adaptive_probes", "config") == "disabled":
        adaptive_probes = False
    max_repairs = _coerce_non_negative_int(
        "max_repair_iterations",
        args.max_repairs
        if args.max_repairs is not None
        else controller_cfg.get("max_repair_iterations", 10),
    )
    probe_iterations = _coerce_non_negative_int(
        "max_probe_iterations",
        args.probe_iterations
        if getattr(args, "probe_iterations", None) is not None
        else probe_cfg.get("max_probe_iterations", 30),
    )
    min_probe_samples = _coerce_non_negative_int(
        "min_samples",
        args.min_probe_samples
        if getattr(args, "min_probe_samples", None) is not None
        else probe_cfg.get("min_samples", 0),
    )
    output_root = (
        Path(args.output)
        if args.output
        else (run_session.generated_path if run_session else Path("./output"))
    )
    return MetaController(
        llm_client=llm_client,
        max_repair_iterations=max_repairs,
        min_probe_coverage=controller_cfg.get("min_probe_coverage", 0.0),
        output_root=output_root,
        probe_iterations=probe_iterations,
        min_probe_samples=min_probe_samples,
        probe_timeout=probe_cfg.get("timeout_per_run", 10.0),
        internal_holdout_ratio=controller_cfg.get("internal_holdout_ratio", 0.0),
        holdout_seed=controller_cfg.get("holdout_seed", "rebuilder"),
        preferred_languages=architect_cfg.get("preferred_languages", []),
        architect_complexity_threshold=architect_cfg.get("complexity_threshold", 3),
        max_architecture_modules=architect_cfg.get("max_modules"),
        run_session=run_session,
        reference_executor_backend=reference_executor_backend,
        replacement_executor_backend=build_replacement_executor_backend(config, args),
        enable_static_output_assets=static_output_assets,
        enable_adaptive_probes=adaptive_probes,
        adaptive_probe_exclude_domains=getattr(args, "adaptive_probe_exclude_domain", []),
        differential_concurrency=differential_cfg.get("max_concurrency", 8),
    )


def resolve_provider_api_key(config: dict) -> tuple[str, str]:
    """Return the provider's environment variable name and resolved API key."""
    provider = config["llm"]["provider"]
    env_var_by_provider = {
        "glm": "GLM_API_KEY",
        "kimi": "KIMI_API_KEY",
        "local_openai": "LOCAL_OPENAI_API_KEY",
        "file_bridge": "FILE_BRIDGE_API_KEY",
    }
    env_var = env_var_by_provider.get(provider, f"{provider.upper()}_API_KEY")
    provider_key = config["llm"].get(provider, {}).get("api_key", "")
    api_key = os.environ.get(env_var) or provider_key
    if isinstance(api_key, str) and api_key.startswith("${"):
        api_key = ""
    return env_var, api_key


def provider_requires_api_key(provider: str) -> bool:
    return provider in {"glm", "kimi"}


def resolve_task_id(task_path: Path, run_session: RunSession | None) -> str:
    return run_session.task_id if run_session else Path(task_path).name


async def main():
    args = parse_args()
    print_banner()
    
    # Load configuration
    config = load_config(args.config)
    if args.provider:
        config["llm"]["provider"] = args.provider
    
    # Check API key
    provider = config["llm"]["provider"]
    env_var, api_key = resolve_provider_api_key(config)
    if provider_requires_api_key(provider) and not api_key:
        console.print(f"[red]Error: {env_var} environment variable not set.[/red]")
        console.print("Please set it in your environment or project .env file.")
        sys.exit(1)
    if api_key:
        config["llm"][provider]["api_key"] = api_key
    elif provider == "local_openai":
        config["llm"][provider]["api_key"] = ""
    
    console.print(f"Using LLM provider: [bold green]{provider}[/bold green]")
    console.print(f"Model: [bold]{config['llm'][provider]['model']}[/bold]")
    
    # Create LLM client
    llm_client = create_llm_client(config)
    
    # Load task
    task_path = Path(args.task)
    run_session = discover_run_session(task_path)
    try:
        executable, documentation = load_task(task_path)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    
    console.print(f"Task loaded: [bold]{task_path.name}[/bold]")
    console.print(f"Executable: [dim]{executable}[/dim]")
    console.print(f"Documentation length: [dim]{len(documentation)} chars[/dim]")
    console.print()
    
    # Run ReBuilder pipeline
    docker_executable, reference_backend = build_reference_executable_and_backend(args)
    reference_executable = docker_executable or executable
    controller = build_controller(
        llm_client,
        config,
        args,
        run_session=run_session,
        reference_executor_backend=reference_backend,
    )
    
    result = await controller.run(
        task_id=resolve_task_id(task_path, run_session),
        executable=reference_executable,
        documentation=documentation,
    )
    
    # Print results
    console.print()
    console.print(Panel("[bold]Task Complete[/bold]", style="bold green"))
    
    table = Table(show_header=False, title="Results")
    table.add_row("Task ID", result.task_id)
    table.add_row("Status", f"[bold {'green' if result.status == 'success' else 'yellow' if result.status == 'partial' else 'red'}]{result.status.upper()}[/]")
    table.add_row("Resolved Rate", f"{result.resolved_rate:.1%}")
    table.add_row("Almost Resolved", "Yes" if result.almost_resolved else "No")
    table.add_row("Repair Iterations", str(result.iterations_used))
    table.add_row("Probes Conducted", str(result.probes_conducted))
    if result.exploration_cases or result.holdout_cases:
        table.add_row("Exploration Cases", str(result.exploration_cases))
        table.add_row("Holdout Cases", str(result.holdout_cases))
    if result.holdout_resolved_rate is not None:
        table.add_row("Holdout Rate", f"{result.holdout_resolved_rate:.1%}")
    if result.implementation_metadata:
        asset_status = result.implementation_metadata.get("contract_asset_status")
        asset_enabled = result.implementation_metadata.get("static_output_assets_enabled")
        if asset_enabled is not None:
            label = "enabled" if asset_enabled else "disabled"
            if asset_status:
                label = f"{label} ({asset_status})"
            table.add_row("Static Assets", label)
    if result.codebase:
        table.add_row("Output Directory", str(result.codebase.root_path))
        table.add_row("Files Generated", str(len(result.codebase.files)))
    console.print(table)
    
    # Save result metadata
    output_meta = controller.output_root / result.task_id / "result.json"
    output_meta.parent.mkdir(parents=True, exist_ok=True)
    with open(output_meta, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(exclude={"codebase"}, mode="json"), f, indent=2, ensure_ascii=False)
    console.print(f"\nResult metadata saved to: [dim]{output_meta}[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
