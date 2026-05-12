"""Static integrity checks for generated codebases."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

from core.data_models import Codebase


@dataclass(frozen=True)
class CodebaseIntegrityIssue:
    kind: str
    path: str
    module: str
    message: str


class CodebaseIntegrityChecker:
    """Find structural problems that would prevent a candidate from running."""

    def find_issues(
        self,
        codebase: Codebase,
        entry_point: str | None = None,
    ) -> list[CodebaseIntegrityIssue]:
        if codebase.language.lower() != "python":
            return []
        return [
            *self._python_syntax_errors(codebase),
            *self._python_missing_entrypoint(codebase, entry_point),
            *self._python_non_executable_entrypoint(codebase, entry_point),
            *self._python_missing_imports(codebase),
        ]

    def _python_syntax_errors(self, codebase: Codebase) -> list[CodebaseIntegrityIssue]:
        issues: list[CodebaseIntegrityIssue] = []
        for path, content in sorted(codebase.files.items()):
            if not path.endswith(".py"):
                continue
            try:
                ast.parse(content, filename=path)
            except SyntaxError as exc:
                lineno = exc.lineno or 1
                offset = exc.offset or 1
                issues.append(
                    CodebaseIntegrityIssue(
                        kind="syntax_error",
                        path=path,
                        module=path,
                        message=f"Python file {path!r} has syntax error at {lineno}:{offset}: {exc.msg}",
                    )
                )
        return issues

    def _python_missing_entrypoint(
        self,
        codebase: Codebase,
        entry_point: str | None,
    ) -> list[CodebaseIntegrityIssue]:
        if not entry_point:
            return []
        normalized = entry_point.replace("\\", "/")
        if not normalized.endswith(".py"):
            normalized += ".py"
        if normalized in codebase.files:
            return []
        return [
            CodebaseIntegrityIssue(
                kind="missing_entrypoint",
                path=normalized,
                module=normalized,
                message=f"expected Python entry point {normalized!r} was not generated",
            )
        ]

    def _python_non_executable_entrypoint(
        self,
        codebase: Codebase,
        entry_point: str | None,
    ) -> list[CodebaseIntegrityIssue]:
        normalized = self._normalize_python_entrypoint(entry_point)
        if not normalized or normalized not in codebase.files:
            return []
        try:
            tree = ast.parse(codebase.files[normalized], filename=normalized)
        except SyntaxError:
            return []
        if self._entrypoint_has_runtime_dispatch(tree):
            return []
        return [
            CodebaseIntegrityIssue(
                kind="non_executable_entrypoint",
                path=normalized,
                module=normalized,
                message=f"Python entry point {normalized!r} does not dispatch a CLI",
            )
        ]

    def _normalize_python_entrypoint(self, entry_point: str | None) -> str | None:
        if not entry_point:
            return None
        normalized = entry_point.replace("\\", "/")
        if not normalized.endswith(".py"):
            normalized += ".py"
        return normalized

    def _entrypoint_has_runtime_dispatch(self, tree: ast.Module) -> bool:
        for node in tree.body:
            if self._is_docstring(node):
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if self._is_main_guard(node):
                return True
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                return True
            if isinstance(node, ast.Raise):
                return True
        return False

    def _is_docstring(self, node: ast.stmt) -> bool:
        return (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )

    def _is_main_guard(self, node: ast.stmt) -> bool:
        if not isinstance(node, ast.If):
            return False
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
            return False
        left = test.left
        right = test.comparators[0]
        if not isinstance(test.ops[0], ast.Eq):
            return False
        return (
            isinstance(left, ast.Name)
            and left.id == "__name__"
            and isinstance(right, ast.Constant)
            and right.value == "__main__"
        )

    def _python_missing_imports(self, codebase: Codebase) -> list[CodebaseIntegrityIssue]:
        issues: list[CodebaseIntegrityIssue] = []
        seen: set[tuple[str, str]] = set()
        local_modules = self._local_python_modules(codebase)
        stdlib_modules = set(getattr(sys, "stdlib_module_names", set()))
        stdlib_modules.update(sys.builtin_module_names)

        for path, content in sorted(codebase.files.items()):
            if not path.endswith(".py"):
                continue
            try:
                tree = ast.parse(content, filename=path)
            except SyntaxError:
                continue
            for module in sorted(self._import_roots(tree)):
                if module in local_modules or module in stdlib_modules:
                    continue
                key = (path, module)
                if key in seen:
                    continue
                seen.add(key)
                issues.append(
                    CodebaseIntegrityIssue(
                        kind="missing_import",
                        path=path,
                        module=module,
                        message=f"{path} imports missing module {module!r}",
                    )
                )
        return issues

    def _local_python_modules(self, codebase: Codebase) -> set[str]:
        modules: set[str] = set()
        for path in codebase.files:
            if not path.endswith(".py"):
                continue
            pure = PurePosixPath(path)
            if pure.name == "__init__.py" and pure.parent.parts:
                modules.add(pure.parent.parts[0])
            elif len(pure.parts) == 1:
                modules.add(pure.stem)
            elif pure.parts:
                modules.add(pure.parts[0])
        return modules

    def _import_roots(self, tree: ast.AST) -> set[str]:
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module:
                    roots.add(node.module.split(".", 1)[0])
        return roots
