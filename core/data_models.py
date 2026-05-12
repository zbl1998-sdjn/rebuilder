"""
Core data models for ReBuilder framework.
All domain objects are defined as Pydantic models for validation and serialization.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ProbeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TestResult(BaseModel):
    """Result of executing a test case against a program."""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    output_files: Dict[str, bytes] = Field(default_factory=dict)
    execution_time_ms: float = 0.0
    timeout_triggered: bool = False


TestResult.__test__ = False


class TestCase(BaseModel):
    """A single test input for probing or differential testing."""
    name: str
    args: List[str] = Field(default_factory=list)
    stdin: str = ""
    input_files: Dict[str, bytes] = Field(default_factory=dict)
    env_vars: Dict[str, str] = Field(default_factory=dict)
    description: str = ""


TestCase.__test__ = False


class BehaviorSample(BaseModel):
    """An observed input-output pair from the original executable."""
    test_case: TestCase
    observed_result: TestResult
    tags: List[str] = Field(default_factory=list)  # e.g., ["error_mode", "edge_case", "happy_path"]


class BehaviorContract(BaseModel):
    """Exact observed behavior that generated code should prioritize."""
    test_name: str
    args: List[str] = Field(default_factory=list)
    stdin: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    output_files: List[str] = Field(default_factory=list)
    output_file_previews: Dict[str, str] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)


class CLISurface(BaseModel):
    """Discovered CLI interface of the target program."""
    subcommands: List[str] = Field(default_factory=list)
    flags: List[FlagSpec] = Field(default_factory=list)
    positional_args: List[ArgSpec] = Field(default_factory=list)
    stdin_mode: bool = False
    file_input_mode: bool = False
    file_output_mode: bool = False
    exit_codes: List[int] = Field(default_factory=list)


class FlagSpec(BaseModel):
    name: str
    short_form: Optional[str] = None
    type_hint: str = "bool"  # bool, string, int, float, path
    required: bool = False
    default_value: Optional[str] = None
    description: str = ""


class ArgSpec(BaseModel):
    name: str
    position: int
    type_hint: str = "string"
    required: bool = True
    variadic: bool = False


class Invariant(BaseModel):
    """An inferred behavioral invariant."""
    description: str
    invariant_type: str  # "deterministic", "idempotent", "monotonic", "ordered", etc.
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_samples: List[int] = Field(default_factory=list)  # indices into corpus


class ProgramSpec(BaseModel):
    """Synthesized specification of the target program."""
    summary: str = ""
    input_formats: List[str] = Field(default_factory=list)
    output_formats: List[str] = Field(default_factory=list)
    cli_surface: CLISurface = Field(default_factory=CLISurface)
    behavior_graph: Optional[str] = None  # Mermaid or DOT representation
    edge_cases: List[str] = Field(default_factory=list)
    complexity_hints: Dict[str, Any] = Field(default_factory=dict)
    invariants: List[Invariant] = Field(default_factory=list)
    stateful: bool = False
    raw_observations: str = ""  # LLM-readable summary of all observations
    behavior_contracts: List[BehaviorContract] = Field(default_factory=list)


class ModuleBlueprint(BaseModel):
    name: str
    responsibility: str
    interfaces: List[InterfaceSpec] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)


class InterfaceSpec(BaseModel):
    name: str
    signature: str
    input_types: List[str] = Field(default_factory=list)
    output_type: str = "void"
    description: str = ""


class ArchitectureBlueprint(BaseModel):
    """High-level design for the replacement implementation."""
    language: str
    language_version: str = ""
    modules: List[ModuleBlueprint] = Field(default_factory=list)
    entry_point: str = "main"
    build_system: str = "auto"  # auto, cmake, makefile, cargo, poetry, etc.
    test_harness: str = ""
    architecture_notes: str = ""


class Codebase(BaseModel):
    """A generated codebase candidate."""
    root_path: Path
    language: str
    files: Dict[str, str] = Field(default_factory=dict)  # relative_path -> content
    build_script: Optional[str] = None
    executable_path: Optional[Path] = None
    generation_metadata: Dict[str, Any] = Field(default_factory=dict)


class DiffReport(BaseModel):
    """Result of differential testing between original and replacement."""
    test_case: TestCase
    original_result: TestResult
    replacement_result: TestResult
    stdout_match: bool = False
    stderr_match: bool = False
    exit_code_match: bool = False
    file_outputs_match: bool = True
    timing_similar: bool = True
    
    @property
    def is_equivalent(self) -> bool:
        return (
            self.stdout_match
            and self.stderr_match
            and self.exit_code_match
            and self.file_outputs_match
        )
    
    @property
    def match_score(self) -> float:
        """Return a 0-1 score of behavioral equivalence."""
        checks = [self.stdout_match, self.stderr_match, self.exit_code_match, self.file_outputs_match]
        return sum(checks) / len(checks)


class RepairStrategy(BaseModel):
    """A diagnosed repair action."""
    strategy_type: str  # "fix_exit_code", "fix_output_format", "fix_file_handling", "add_edge_case", "refactor"
    description: str
    target_files: List[str] = Field(default_factory=list)
    hints: str = ""


class TaskResult(BaseModel):
    """Final result of processing a ProgramBench task."""
    task_id: str
    status: str  # "success", "partial", "failed"
    codebase: Optional[Codebase] = None
    final_diff_report: Optional[DiffReport] = None
    resolved_rate: float = 0.0
    almost_resolved: bool = False
    iterations_used: int = 0
    probes_conducted: int = 0
    exploration_cases: int = 0
    holdout_cases: int = 0
    holdout_resolved_rate: Optional[float] = None
    implementation_metadata: Dict[str, Any] = Field(default_factory=dict)
    logs: List[str] = Field(default_factory=list)
