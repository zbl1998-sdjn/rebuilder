import json

import pytest

from core.architect_agent import ArchitectAgent
from core.data_models import (
    ArchitectureBlueprint,
    BehaviorContract,
    ModuleBlueprint,
    ProgramSpec,
)
from core.implementer_agent import ImplementerAgent
from core.prompting.behavior_contracts import (
    behavior_contract_prompt,
    implementation_behavior_contract_prompt,
    spec_prompt_json,
)
from llm_clients.base import BaseLLMClient, LLMResponse
from tests.test_probe_engine import MockLLMClient


class CaptureArchitectLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.messages = []

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.messages.append(messages)
        return LLMResponse(
            content='{"language":"python","modules":[],"entry_point":"main.py","build_system":"none"}'
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


def test_architect_extracts_json_from_markdown_preamble():
    raw = """The architecture can stay compact:

```json
{
  "language": "python",
  "language_version": "3.11",
  "modules": [
    {
      "name": "main",
      "responsibility": "CLI entry",
      "interfaces": [],
      "dependencies": []
    }
  ],
  "entry_point": "main.py",
  "build_system": "none",
  "architecture_notes": "single-file replacement"
}
```
"""

    blueprint = ArchitectAgent(MockLLMClient())._parse_blueprint(raw)

    assert blueprint.language == "python"
    assert blueprint.entry_point == "main.py"
    assert blueprint.modules[0].name == "main"
    assert blueprint.architecture_notes == "single-file replacement"


def test_architect_enforces_preferred_language_when_model_chooses_unsupported():
    raw = """{
  "language": "Rust",
  "language_version": "1.75",
  "modules": [],
  "entry_point": "src/main.rs",
  "build_system": "cargo",
  "architecture_notes": "Rust CLI"
}
"""

    blueprint = ArchitectAgent(
        MockLLMClient(),
        preferred_languages=["python"],
    )._parse_blueprint(raw)

    assert blueprint.language == "python"
    assert blueprint.entry_point == "main.py"
    assert blueprint.build_system == "none"
    assert "Unsupported language" in blueprint.architecture_notes


def test_architect_normalizes_invalid_python_entrypoint_to_default():
    raw = """{
  "language": "python",
  "modules": [],
  "entry_point": "zoxide/py:main.py",
  "build_system": "none"
}
"""

    blueprint = ArchitectAgent(MockLLMClient())._parse_blueprint(raw)

    assert blueprint.language == "python"
    assert blueprint.entry_point == "main.py"


def test_architect_keeps_safe_python_entrypoint_forms():
    dotted = ArchitectAgent(MockLLMClient())._parse_blueprint(
        '{"language":"python","modules":[],"entry_point":"cli.main"}'
    )
    path = ArchitectAgent(MockLLMClient())._parse_blueprint(
        '{"language":"python","modules":[],"entry_point":"cli/main.py"}'
    )

    assert dotted.entry_point == "cli.main"
    assert path.entry_point == "cli/main.py"


@pytest.mark.asyncio
async def test_architect_design_uses_safe_spec_prompt_for_bytes_payloads():
    llm = CaptureArchitectLLM()
    spec = ProgramSpec(
        summary="tool",
        complexity_hints={"sample_bytes": b"\x00\x01"},
        behavior_contracts=[
            BehaviorContract(test_name="help_long", args=["--help"], stdout="usage\n")
        ],
    )

    await ArchitectAgent(llm).design(spec)

    prompt = llm.messages[0][1].content
    assert '"__type__": "bytes"' in prompt
    assert '"base64": "AAE="' in prompt
    assert "help_long" in prompt


def test_implementer_parses_json_file_manifest(tmp_path):
    raw = json.dumps(
        {
            "files": [
                {"path": "main.py", "content": "print('ok')\n"},
            ],
            "build_script": "",
        }
    )

    codebase = ImplementerAgent(MockLLMClient())._parse_codebase(
        raw,
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    assert codebase.files == {"main.py": "print('ok')\n"}
    assert codebase.executable_path == tmp_path / "main.py"
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "print('ok')\n"


def test_implementer_parses_json_array_file_manifest(tmp_path):
    raw = json.dumps(
        [
            {"path": "main.py", "content": "print('ok')\n"},
        ]
    )

    codebase = ImplementerAgent(MockLLMClient())._parse_codebase(
        raw,
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    assert codebase.files == {"main.py": "print('ok')\n"}
    assert codebase.executable_path == tmp_path / "main.py"


def test_implementer_parses_jsonish_manifest_with_unescaped_code_quotes(tmp_path):
    raw = '''```json
{
  "files": [
    {
      "path": "main.py",
      "content": "print("hello")\\n"
    }
  ],
  "build_script": ""
}
'''

    codebase = ImplementerAgent(MockLLMClient())._parse_codebase(
        raw,
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    assert codebase.files == {"main.py": 'print("hello")\n'}
    assert codebase.executable_path == tmp_path / "main.py"


def test_implementer_strips_nested_code_fence_from_file_content(tmp_path):
    raw = json.dumps(
        {
            "files": [
                {"path": "main.py", "content": "```python\nprint('ok')\n```"},
            ]
        }
    )

    codebase = ImplementerAgent(MockLLMClient())._parse_codebase(
        raw,
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    assert codebase.files == {"main.py": "print('ok')"}
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "print('ok')"


def test_implementer_parses_truncated_jsonish_manifest(tmp_path):
    raw = """```json
{
  "files": [
    {
      "path": "main.py",
      "content": "#!/usr/bin/env python3\\nimport argparse\\n\\ndef main():\\n    print(\\"ok\\")\\n\\nif __name__ == \\"__main__\\":\\n    main()\\n
"""

    codebase = ImplementerAgent(MockLLMClient())._parse_codebase(
        raw,
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    assert "main.py" in codebase.files
    assert codebase.files["main.py"].startswith("#!/usr/bin/env python3")
    assert "def main():" in codebase.files["main.py"]
    assert codebase.generation_metadata["parse_status"] == "ok"


def test_implementer_uses_entry_point_for_single_python_code_block(tmp_path):
    raw = """Here is the implementation:

```python
print('ok')
```
"""

    codebase = ImplementerAgent(MockLLMClient())._parse_codebase(
        raw,
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    assert codebase.files == {"main.py": "print('ok')"}
    assert codebase.executable_path == tmp_path / "main.py"


def test_implementer_normalizes_dotted_python_entrypoint_to_module_path(tmp_path):
    raw = """```python
print('ok')
```"""

    codebase = ImplementerAgent(MockLLMClient())._parse_codebase(
        raw,
        ArchitectureBlueprint(language="python", entry_point="cli.main"),
        tmp_path,
    )

    assert codebase.files == {"cli/main.py": "print('ok')"}
    assert codebase.executable_path == tmp_path / "cli" / "main.py"


class RetryImplementerLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.calls = 0

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(content="I would create a CLI implementation here.")
        return LLMResponse(
            content=json.dumps(
                {"files": [{"path": "main.py", "content": "print('retry')\n"}]}
            )
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


@pytest.mark.asyncio
async def test_implementer_retries_unparseable_first_response(tmp_path):
    llm = RetryImplementerLLM()

    codebase = await ImplementerAgent(llm).implement(
        ProgramSpec(summary="test"),
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    assert llm.calls == 2
    assert codebase.files == {"main.py": "print('retry')\n"}
    assert codebase.generation_metadata["implementation_retry"] == "unparseable_initial_output"


def materializable_shell_init_spec() -> ProgramSpec:
    return ProgramSpec(
        summary="tool",
        behavior_contracts=[
            BehaviorContract(
                test_name="shell_init_bash",
                args=["init", "bash"],
                stdout="# shellcheck shell=bash\n" + ("x" * 2000) + "\n# tail-marker\n",
                tags=["shell_init", "full_output"],
            )
        ],
    )


def test_static_asset_entrypoint_prompt_bans_shell_init_template_generation():
    messages = ImplementerAgent(MockLLMClient())._entrypoint_messages(
        materializable_shell_init_spec(),
        modular_python_blueprint(),
    )

    system_prompt = messages[0].content
    user_prompt = messages[1].content
    assert "Do not implement shell init script templates" in system_prompt
    assert "generated asset injection will handle those exact argv forms" in system_prompt
    assert "Keep the entrypoint compact" in system_prompt
    assert "materialized as generated assets" in user_prompt
    assert "# tail-marker" not in user_prompt


def test_disabled_asset_entrypoint_prompt_requests_compact_shell_init_generation():
    messages = ImplementerAgent(
        MockLLMClient(),
        enable_static_output_assets=False,
    )._entrypoint_messages(
        materializable_shell_init_spec(),
        modular_python_blueprint(),
    )

    system_prompt = messages[0].content
    assert "Static output asset mode is disabled" in system_prompt
    assert "Avoid giant escaped one-line literals" in system_prompt
    assert "so generated Python parses cleanly" in system_prompt


class StaticAssetRetryCaptureLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.messages = []

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.messages.append(messages)
        if len(self.messages) == 1:
            return LLMResponse(content="not parseable")
        return LLMResponse(
            content=json.dumps(
                {
                    "files": [
                        {
                            "path": "main.py",
                            "content": (
                                "def main():\n"
                                "    return 0\n"
                                "if __name__ == '__main__':\n"
                                "    raise SystemExit(main())\n"
                            ),
                        }
                    ]
                }
            )
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


@pytest.mark.asyncio
async def test_static_asset_retry_prompt_bans_shell_init_template_generation(tmp_path):
    llm = StaticAssetRetryCaptureLLM()

    await ImplementerAgent(llm).implement(
        materializable_shell_init_spec(),
        modular_python_blueprint(),
        tmp_path,
    )

    retry_system_prompt = llm.messages[1][0].content
    assert "Do not implement shell init script templates" in retry_system_prompt
    assert "generated asset injection will handle those exact argv forms" in retry_system_prompt


@pytest.mark.asyncio
async def test_disabled_asset_retry_prompt_requests_syntax_safe_shell_init_generation(tmp_path):
    llm = StaticAssetRetryCaptureLLM()

    await ImplementerAgent(
        llm,
        enable_static_output_assets=False,
    ).implement(
        materializable_shell_init_spec(),
        modular_python_blueprint(),
        tmp_path,
    )

    retry_system_prompt = llm.messages[1][0].content
    assert "Static output asset mode is disabled" in retry_system_prompt
    assert "Avoid giant escaped one-line literals" in retry_system_prompt


def test_implementer_records_unparseable_output_diagnostic(tmp_path):
    codebase = ImplementerAgent(MockLLMClient())._parse_codebase(
        "not parseable",
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    diagnostic = tmp_path / ".rebuilder" / "implementation_raw.txt"
    assert codebase.files == {}
    assert codebase.generation_metadata["parse_status"] == "no_files"
    assert diagnostic.read_text(encoding="utf-8") == "not parseable"


class MissingImportImplementerLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.calls = 0
        self.messages = []

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            return LLMResponse(
                content=json.dumps(
                    {
                        "files": [
                            {
                                "path": "main.py",
                                "content": "from database import load_db\nprint(load_db())\n",
                            }
                        ]
                    }
                )
            )
        return LLMResponse(
            content=json.dumps(
                {
                    "files": [
                        {
                            "path": "main.py",
                            "content": "def load_db():\n    return {}\nprint(load_db())\n",
                        }
                    ]
                }
            )
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


@pytest.mark.asyncio
async def test_implementer_retries_when_generated_python_imports_missing_modules(tmp_path):
    llm = MissingImportImplementerLLM()

    codebase = await ImplementerAgent(llm).implement(
        ProgramSpec(summary="test"),
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    assert llm.calls == 2
    assert codebase.files == {
        "main.py": "def load_db():\n    return {}\nprint(load_db())\n"
    }
    assert codebase.generation_metadata["implementation_retry"] == "integrity_issues"
    assert "Keep the implementation compact" in llm.messages[1][0].content


class MissingEntrypointImplementerLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.calls = 0

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content=json.dumps(
                    {
                        "files": [
                            {"path": "zoxide/core.py", "content": "def main():\n    return 0\n"}
                        ]
                    }
                )
            )
        return LLMResponse(
            content=json.dumps(
                {
                    "files": [
                        {"path": "main.py", "content": "print('entry')\n"},
                    ]
                }
            )
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


@pytest.mark.asyncio
async def test_implementer_retries_when_generated_python_entrypoint_missing(tmp_path):
    llm = MissingEntrypointImplementerLLM()

    codebase = await ImplementerAgent(llm).implement(
        ProgramSpec(summary="test"),
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    assert llm.calls == 2
    assert codebase.files == {"main.py": "print('entry')\n"}
    assert codebase.executable_path == tmp_path / "main.py"
    assert not (tmp_path / "zoxide" / "core.py").exists()


class StagedImplementerLLM(BaseLLMClient):
    def __init__(self, second_response: str | None = None):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.calls = 0
        self.messages = []
        self.second_response = second_response or json.dumps(
            {
                "files": [
                    {
                        "path": "helpers.py",
                        "content": "def label():\n    return 'module'\n",
                    }
                ]
            }
        )

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            return LLMResponse(
                content=json.dumps(
                    {
                        "files": [
                            {
                                "path": "main.py",
                                "content": (
                                    "def main():\n"
                                    "    print('entry')\n"
                                    "    return 0\n"
                                    "if __name__ == '__main__':\n"
                                    "    raise SystemExit(main())\n"
                                ),
                            }
                        ]
                    }
                )
            )
        return LLMResponse(content=self.second_response)

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


def modular_python_blueprint() -> ArchitectureBlueprint:
    return ArchitectureBlueprint(
        language="python",
        entry_point="main.py",
        modules=[
            ModuleBlueprint(name="cli", responsibility="CLI entry"),
            ModuleBlueprint(name="helpers", responsibility="support logic"),
        ],
    )


@pytest.mark.asyncio
async def test_implementer_generates_python_entrypoint_before_support_modules(tmp_path):
    llm = StagedImplementerLLM()

    codebase = await ImplementerAgent(llm).implement(
        ProgramSpec(summary="test"),
        modular_python_blueprint(),
        tmp_path,
    )

    assert llm.calls == 2
    assert "Generate only the Python CLI entrypoint" in llm.messages[0][0].content
    assert "Generate supporting Python files" in llm.messages[1][0].content
    assert codebase.files == {
        "main.py": (
            "def main():\n"
            "    print('entry')\n"
            "    return 0\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n"
        ),
        "helpers.py": "def label():\n    return 'module'\n",
    }
    assert codebase.executable_path == tmp_path / "main.py"
    assert codebase.generation_metadata["implementation_strategy"] == "python_staged"
    assert codebase.generation_metadata["module_stage_status"] == "accepted"


@pytest.mark.asyncio
async def test_implementer_keeps_entrypoint_when_support_module_stage_fails(tmp_path):
    llm = StagedImplementerLLM(second_response="not parseable")

    codebase = await ImplementerAgent(llm).implement(
        ProgramSpec(summary="test"),
        modular_python_blueprint(),
        tmp_path,
    )

    assert llm.calls == 2
    assert codebase.files == {
        "main.py": (
            "def main():\n"
            "    print('entry')\n"
            "    return 0\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n"
        )
    }
    assert codebase.generation_metadata["module_stage_status"] == "rejected_no_files"
    assert not (tmp_path / "helpers.py").exists()


class StagedRetryFallbackLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.calls = 0

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        # Staged entrypoint response 1: non-executable (no runtime dispatch).
        if self.calls == 1:
            return LLMResponse(
                content=json.dumps(
                    {"files": [{"path": "main.py", "content": "def helper():\n    return 1\n"}]}
                )
            )
        # Staged retry response 2: still non-executable to trigger fallback.
        if self.calls == 2:
            return LLMResponse(
                content=json.dumps(
                    {"files": [{"path": "main.py", "content": "def helper():\n    return 2\n"}]}
                )
            )
        # Single-pass fallback response 3: runnable entrypoint.
        return LLMResponse(
            content=json.dumps(
                {
                    "files": [
                        {
                            "path": "main.py",
                            "content": (
                                "def main():\n"
                                "    return 0\n"
                                "if __name__ == '__main__':\n"
                                "    raise SystemExit(main())\n"
                            ),
                        }
                    ]
                }
            )
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


@pytest.mark.asyncio
async def test_implementer_falls_back_to_single_pass_when_staged_retry_entrypoint_still_invalid(tmp_path):
    llm = StagedRetryFallbackLLM()

    codebase = await ImplementerAgent(llm).implement(
        ProgramSpec(summary="test"),
        modular_python_blueprint(),
        tmp_path,
    )

    assert llm.calls == 3
    assert codebase.files == {
        "main.py": (
            "def main():\n"
            "    return 0\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n"
        )
    }
    assert codebase.generation_metadata["implementation_strategy"] == "python_staged_fallback_single_pass"
    assert codebase.generation_metadata["entrypoint_stage_retry_failed_issues"]


class ContractCaptureLLM(BaseLLMClient):
    def __init__(self):
        super().__init__("fake-key", "http://fake", "mock-model")
        self.messages = []

    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        self.messages.append(messages)
        return LLMResponse(
            content=json.dumps(
                {
                    "files": [
                        {
                            "path": "main.py",
                            "content": (
                                "def main():\n"
                                "    return 0\n"
                                "if __name__ == '__main__':\n"
                                "    raise SystemExit(main())\n"
                            ),
                        }
                    ]
                }
            )
        )

    async def chat_stream(self, messages, temperature=None, max_tokens=None, **kwargs):
        yield "mock"


@pytest.mark.asyncio
async def test_implementer_prompts_with_exact_behavior_contracts(tmp_path):
    llm = ContractCaptureLLM()
    spec = ProgramSpec(
        summary="tool",
        behavior_contracts=[
            BehaviorContract(
                test_name="help_long",
                args=["--help"],
                stdout="exact help\n",
                stderr="",
                exit_code=0,
            ),
            BehaviorContract(
                test_name="no_args",
                args=[],
                stdout="",
                stderr="exact stderr\n",
                exit_code=2,
            ),
        ],
    )

    await ImplementerAgent(llm).implement(
        spec,
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    prompt = llm.messages[0][1].content
    assert "Exact behavior contracts" in prompt
    assert "exact help\\n" in prompt
    assert "exact stderr\\n" in prompt
    assert '"exit_code": 2' in prompt
    assert prompt.count("exact help\\n") == 1


@pytest.mark.asyncio
async def test_implementer_contract_prompt_is_compact_and_prioritized(tmp_path):
    llm = ContractCaptureLLM()
    contracts = [
        BehaviorContract(test_name=f"case_{index}", args=[str(index)], stdout="x" * 200)
        for index in range(20)
    ]
    contracts.append(
        BehaviorContract(test_name="no_args", args=[], stderr="usage\n", exit_code=2)
    )
    spec = ProgramSpec(summary="tool", behavior_contracts=contracts)

    await ImplementerAgent(llm).implement(
        spec,
        ArchitectureBlueprint(language="python", entry_point="main.py"),
        tmp_path,
    )

    prompt = llm.messages[0][1].content
    assert "no_args" in prompt
    assert "case_19" not in prompt
    assert len(prompt) < 6000


def test_behavior_contract_prompt_prioritizes_shell_init_full_output():
    stdout = "function __zoxide_z() {}\n" + ("x" * 5000) + "\n# tail-marker\n"
    spec = ProgramSpec(
        summary="tool",
        behavior_contracts=[
            BehaviorContract(test_name=f"case_{index}", args=[str(index)], stdout="ok\n")
            for index in range(20)
        ]
        + [
            BehaviorContract(test_name="no_args", args=[], stderr="usage\n", exit_code=2),
            BehaviorContract(
                test_name="shell_init_bash",
                args=["init", "bash"],
                stdout=stdout,
                tags=["shell_init", "full_output", "shell:bash"],
            ),
        ],
    )

    prompt = behavior_contract_prompt(spec)

    assert "shell_init_bash" in prompt
    assert "# tail-marker\\n" in prompt
    assert "case_19" not in prompt


def test_behavior_contract_prompt_includes_output_file_previews():
    spec = ProgramSpec(
        summary="tool",
        behavior_contracts=[
            BehaviorContract(
                test_name="file_io_input_output_flags",
                args=["--input", "input.txt", "--output", "out.txt"],
                output_files=["out.txt"],
                output_file_previews={"out.txt": "result: alpha\n"},
                tags=["file_io", "side_effect"],
            )
        ],
    )

    prompt = behavior_contract_prompt(spec)

    assert '"output_files": [' in prompt
    assert '"out.txt": "result: alpha\\n"' in prompt


def test_spec_prompt_json_is_bytes_safe_and_excludes_behavior_contracts():
    spec = ProgramSpec(
        summary="tool",
        complexity_hints={"sample_bytes": b"\x00\x01"},
        behavior_contracts=[
            BehaviorContract(test_name="help_long", args=["--help"], stdout="usage\n")
        ],
    )

    prompt = spec_prompt_json(spec)

    assert '"__type__": "bytes"' in prompt
    assert '"base64": "AAE="' in prompt
    assert "behavior_contracts" not in prompt


def test_implementation_contract_prompt_summarizes_materialized_shell_init_outputs():
    stdout = "# shellcheck shell=bash\n" + ("x" * 5000) + "\n# tail-marker\n"
    spec = ProgramSpec(
        summary="tool",
        behavior_contracts=[
            BehaviorContract(
                test_name="shell_init_bash",
                args=["init", "bash"],
                stdout=stdout,
                tags=["shell_init", "full_output"],
            ),
            BehaviorContract(test_name="no_args", args=[], stderr="usage\n", exit_code=2),
        ],
    )

    prompt = implementation_behavior_contract_prompt(spec)

    assert "materialized as generated assets" in prompt
    assert "rebuilder_contracts.py" in prompt
    assert "shell_init_bash" in prompt
    assert "# tail-marker" not in prompt
    assert "usage\\n" in prompt


def test_implementation_contract_prompt_does_not_materialize_shell_init_variants():
    stdout = "# shellcheck shell=bash\n" + ("x" * 5000) + "\n# variant-tail\n"
    spec = ProgramSpec(
        summary="tool",
        behavior_contracts=[
            BehaviorContract(
                test_name="shell_init_bash_cmd_variant",
                args=["init", "--cmd", "j", "bash"],
                stdout=stdout,
                tags=["shell_init", "full_output"],
            )
        ],
    )

    prompt = implementation_behavior_contract_prompt(spec)

    assert "materialized as generated assets" not in prompt
    assert "shell_init_bash_cmd_variant" in prompt
    assert "# variant-tail\\n" in prompt


