"""
Spec Synthesizer: Infer program specification from observed behavior corpus.
"""

from __future__ import annotations

import json
from typing import Any, List

from core.data_models import BehaviorContract, BehaviorSample, ProgramSpec, Invariant, CLISurface
from core.llm_output import extract_json_object
from llm_clients.base import BaseLLMClient, Message
from llm_clients.options import configured_max_tokens
from pydantic import ValidationError


class SpecSynthesizer:
    """Use LLM to synthesize a human-readable program specification from behavior samples."""
    
    SYSTEM_PROMPT = """You are a senior software architect analyzing black-box behavior observations.
Your task is to synthesize a precise, implementable specification of the target program.

Output only a JSON object with these fields:
- "summary": One paragraph describing what the program does
- "input_formats": List of recognized input formats (e.g., ["plain_text", "json", "csv"])
- "output_formats": List of output formats
- "cli_surface": Object describing subcommands, flags, positional args
- "edge_cases": List of known edge cases and error conditions
- "stateful": Boolean indicating if the program maintains state across runs
- "invariants": List of objects with "description", "type" (deterministic/idempotent/monotonic/ordered), "confidence" (0-1)
- "complexity_hints": Object with estimated algorithmic complexity
- "raw_observations": Your detailed technical observations

Be precise and conservative. If you are uncertain about a behavior, note it as speculative."""
    
    def __init__(self, llm_client: BaseLLMClient):
        self.llm = llm_client
    
    async def synthesize(
        self,
        corpus: List[BehaviorSample],
        documentation: str,
        cli_surface: CLISurface,
    ) -> ProgramSpec:
        """Synthesize specification from behavior corpus."""
        
        # Build rich observation text
        observation_text = self._format_corpus(corpus)
        
        messages = [
            self.llm.system_prompt(self.SYSTEM_PROMPT),
            self.llm.user_prompt(
                f"Original documentation:\n{documentation}\n\n"
                f"Discovered CLI surface:\n{cli_surface.model_dump_json(indent=2)}\n\n"
                f"Behavior observations ({len(corpus)} samples):\n{observation_text}\n\n"
                f"Synthesize a complete implementable specification as JSON."
            ),
        ]
        
        resp = await self.llm.chat(
            messages,
            temperature=0.2,
            max_tokens=configured_max_tokens(self.llm, 8192),
        )
        spec = self._parse_spec(resp.content)
        failed_output = resp.content
        if self._is_parse_failure(spec):
            retry = await self.llm.chat(
                self._spec_repair_messages(resp.content),
                temperature=0.0,
                max_tokens=configured_max_tokens(self.llm, 4096),
            )
            repaired = self._parse_spec(retry.content)
            if not self._is_parse_failure(repaired):
                spec = repaired
            else:
                failed_output = retry.content
        if self._is_parse_failure(spec):
            spec = self._fallback_spec(
                corpus=corpus,
                documentation=documentation,
                cli_surface=cli_surface,
                failed_output=failed_output,
            )
        spec.behavior_contracts = self._contracts_from_corpus(corpus)
        return spec
    
    def _format_corpus(self, corpus: List[BehaviorSample]) -> str:
        """Format behavior samples into a readable text for the LLM."""
        chunks = []
        for i, sample in enumerate(corpus):
            tc = sample.test_case
            res = sample.observed_result
            stdout_limit = 8000 if self._is_shell_init_sample(sample) else 500
            stderr_limit = 2000 if self._is_shell_init_sample(sample) else 300
            chunks.append(
                f"=== Sample {i} [{', '.join(sample.tags)}] ===\n"
                f"Input: args={tc.args}, stdin={repr(tc.stdin[:200])}\n"
                f"Output: exit_code={res.exit_code}, stdout={repr(res.stdout[:stdout_limit])}, "
                f"stderr={repr(res.stderr[:stderr_limit])}\n"
                f"Files out: {list(res.output_files.keys())}\n"
                f"File previews: {self._output_file_previews(res.output_files)}\n"
            )
        return "\n".join(chunks)

    def _contracts_from_corpus(
        self,
        corpus: List[BehaviorSample],
        limit: int = 24,
    ) -> list[BehaviorContract]:
        contracts: list[BehaviorContract] = []
        for sample in corpus[:limit]:
            tc = sample.test_case
            res = sample.observed_result
            stdout_limit = 8000 if self._is_shell_init_sample(sample) else 2000
            stderr_limit = 8000 if self._is_shell_init_sample(sample) else 2000
            contracts.append(
                BehaviorContract(
                    test_name=tc.name,
                    args=tc.args,
                    stdin=tc.stdin[:1000],
                    stdout=res.stdout[:stdout_limit],
                    stderr=res.stderr[:stderr_limit],
                    exit_code=res.exit_code,
                    output_files=sorted(res.output_files),
                    output_file_previews=self._output_file_previews(res.output_files),
                    tags=sample.tags,
                )
            )
        return contracts

    def _is_shell_init_sample(self, sample: BehaviorSample) -> bool:
        tc = sample.test_case
        return (
            "shell_init" in sample.tags
            or tc.name.startswith("shell_init_")
            or tc.args[:1] == ["init"]
        )

    def _output_file_previews(
        self,
        output_files: dict[str, bytes],
        limit: int = 2000,
    ) -> dict[str, str]:
        previews: dict[str, str] = {}
        for name, content in sorted(output_files.items()):
            if isinstance(content, bytes):
                text = content.decode("utf-8", errors="replace")
            else:
                text = str(content)
            if len(text) > limit:
                text = f"{text[:limit]}\n...[truncated]"
            previews[name] = text
        return previews
    
    def _parse_spec(self, text: str) -> ProgramSpec:
        """Parse LLM JSON output into ProgramSpec."""
        import re
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "")
        
        try:
            data = extract_json_object(text)
            cli_surface = self._normalize_cli_surface(data.get("cli_surface", {}))
            invariants = self._normalize_invariants(data.get("invariants", []))
            raw_observations = data.get("raw_observations", "")
            if not isinstance(raw_observations, str):
                raw_observations = json.dumps(raw_observations, ensure_ascii=False)
            return ProgramSpec(
                summary=data.get("summary", ""),
                input_formats=self._normalize_string_list(data.get("input_formats", [])),
                output_formats=self._normalize_string_list(data.get("output_formats", [])),
                cli_surface=CLISurface(**cli_surface),
                edge_cases=self._normalize_string_list(data.get("edge_cases", [])),
                stateful=data.get("stateful", False),
                invariants=[Invariant(**inv) for inv in invariants],
                complexity_hints=data.get("complexity_hints", {}),
                raw_observations=raw_observations,
            )
        except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as e:
            # Fallback: return a minimal spec with raw text
            return ProgramSpec(
                summary="Failed to parse structured spec. Raw LLM output preserved.",
                raw_observations=text,
            )

    def _is_parse_failure(self, spec: ProgramSpec) -> bool:
        return spec.summary == "Failed to parse structured spec. Raw LLM output preserved."

    def _spec_repair_messages(self, invalid_output: str) -> list[Message]:
        return [
            self.llm.system_prompt(
                self.SYSTEM_PROMPT
                + "\nReturn a strictly valid JSON object. Do not include markdown fences or prose."
            ),
            self.llm.user_prompt(
                "The previous attempt was not valid JSON for the required schema. "
                "Reformat the draft below into a valid JSON object that preserves its meaning as conservatively as possible.\n\n"
                f"{invalid_output}"
            ),
        ]

    def _fallback_spec(
        self,
        corpus: List[BehaviorSample],
        documentation: str,
        cli_surface: CLISurface,
        failed_output: str,
    ) -> ProgramSpec:
        return ProgramSpec(
            summary=self._fallback_summary(documentation, corpus),
            cli_surface=cli_surface.model_copy(deep=True),
            edge_cases=self._fallback_edge_cases(corpus),
            stateful=any("stateful" in sample.tags for sample in corpus),
            raw_observations=(
                "Structured spec parsing failed; falling back to deterministic synthesis.\n\n"
                f"Documentation:\n{documentation.strip()}\n\n"
                f"Observed behavior:\n{self._format_corpus(corpus)}\n\n"
                f"Unparsed model draft:\n{failed_output.strip()}"
            ).strip(),
        )

    def _fallback_summary(
        self,
        documentation: str,
        corpus: List[BehaviorSample],
    ) -> str:
        lines = [line.strip() for line in documentation.splitlines() if line.strip()]
        if lines:
            return lines[0][:240]
        if corpus:
            sample = corpus[0]
            if sample.test_case.description:
                return sample.test_case.description[:240]
        return "Fallback specification derived from cleanroom observations."

    def _fallback_edge_cases(self, corpus: List[BehaviorSample]) -> list[str]:
        edge_cases: list[str] = []
        seen: set[str] = set()
        for sample in corpus:
            result = sample.observed_result
            if result.exit_code == 0 and not result.timeout_triggered:
                continue
            description = sample.test_case.description or sample.test_case.name
            detail = (
                f"{description}: exit={result.exit_code}"
                + (" timeout" if result.timeout_triggered else "")
            )
            if detail not in seen:
                seen.add(detail)
                edge_cases.append(detail)
        return edge_cases

    def _normalize_cli_surface(self, cli_surface: dict) -> dict:
        """Normalize common LLM JSON variants into CLISurface shape."""
        normalized = dict(cli_surface or {})

        subcommand_sections = []
        subcommands = normalized.get("subcommands", [])
        if isinstance(subcommands, dict):
            normalized["subcommands"] = list(subcommands.keys())
            subcommand_sections = [
                item for item in subcommands.values() if isinstance(item, dict)
            ]
        elif isinstance(subcommands, list):
            names = []
            for item in subcommands:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]))
                    subcommand_sections.append(item)
            normalized["subcommands"] = names
        else:
            normalized["subcommands"] = []

        flag_inputs = []
        flag_inputs.extend(normalized.get("global_flags", []) or [])
        flag_inputs.extend(normalized.get("flags", []) or [])
        for section in subcommand_sections:
            flag_inputs.extend(section.get("flags", []) or [])

        flags = []
        seen_flags = set()
        for item in flag_inputs:
            flag = self._normalize_flag(item)
            if flag and flag["name"] not in seen_flags:
                seen_flags.add(flag["name"])
                flags.append(flag)
        normalized["flags"] = flags

        positional_args = []
        positional_inputs = list(normalized.get("positional_args", []) or [])
        for section in subcommand_sections:
            positional_inputs.extend(section.get("positional_args", []) or [])
        for index, item in enumerate(positional_inputs):
            arg = self._normalize_positional_arg(item, index)
            if arg:
                positional_args.append(arg)
        normalized["positional_args"] = positional_args

        parsed_codes = set(self._parse_exit_codes(normalized.get("exit_codes", [])))
        for section in subcommand_sections:
            parsed_codes.update(self._parse_exit_codes(section.get("exit_codes", [])))
        normalized["exit_codes"] = sorted(parsed_codes)

        return normalized

    def _normalize_flag(self, item: Any) -> dict | None:
        if not isinstance(item, dict):
            return None
        raw_name = item.get("long") or item.get("name")
        if not raw_name:
            return None
        name = str(raw_name)
        if not name.startswith("-"):
            name = f"--{name}"
        flag = {
            "name": name,
            "short_form": item.get("short_form") or item.get("short"),
            "type_hint": item.get("type_hint") or item.get("type") or "bool",
            "required": bool(item.get("required", False)),
            "default_value": item.get("default_value"),
            "description": item.get("description", ""),
        }
        if flag["default_value"] is not None and not isinstance(flag["default_value"], str):
            flag["default_value"] = str(flag["default_value"])
        return flag

    def _normalize_positional_arg(self, item: Any, index: int) -> dict | None:
        if not isinstance(item, dict):
            return None
        if not item.get("name"):
            return None
        return {
            "name": str(item["name"]),
            "position": int(item.get("position", index)),
            "type_hint": item.get("type_hint") or item.get("type") or "string",
            "required": bool(item.get("required", True)),
            "variadic": bool(item.get("variadic", False)),
        }

    def _parse_exit_codes(self, exit_codes: Any) -> list[int]:
        parsed_codes = []
        if isinstance(exit_codes, dict):
            raw_values = exit_codes.keys()
        elif isinstance(exit_codes, list):
            raw_values = [
                item.get("code") if isinstance(item, dict) else item
                for item in exit_codes
            ]
        else:
            raw_values = []
        for value in raw_values:
            try:
                parsed_codes.append(int(value))
            except (TypeError, ValueError):
                continue
        return parsed_codes

    def _normalize_string_list(self, values: list) -> list[str]:
        normalized = []
        for item in values or []:
            if isinstance(item, str):
                normalized.append(item)
            else:
                normalized.append(json.dumps(item, ensure_ascii=False))
        return normalized

    def _normalize_invariants(self, invariants: list) -> list:
        normalized = []
        for item in invariants or []:
            invariant = dict(item)
            if "invariant_type" not in invariant and "type" in invariant:
                invariant["invariant_type"] = invariant.pop("type")
            normalized.append(invariant)
        return normalized
