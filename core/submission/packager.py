"""Create ProgramBench-compatible submission archives."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path


class SubmissionPackager:
    """Package generated code as `<instance_id>/submission.tar.gz`."""

    EXCLUDED_NAMES = {
        "executable",
        "program",
        "program.exe",
        "result.json",
        "session.json",
    }
    EXCLUDED_DIRS = {
        "evidence",
        "reports",
        "compliance",
        "logs",
        "__pycache__",
        ".rebuilder",
    }

    def package(
        self,
        generated_path: Path | str,
        output_root: Path | str,
        instance_id: str,
    ) -> Path:
        source = Path(generated_path)
        target_dir = Path(output_root) / instance_id
        target_dir.mkdir(parents=True, exist_ok=True)
        archive = target_dir / "submission.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for path in sorted(source.rglob("*")):
                if not path.is_file() or self._excluded(path, source):
                    continue
                tar.add(path, arcname=path.relative_to(source).as_posix())
            if not (source / "compile.sh").exists():
                compile_script = self._default_compile_script(source)
                if compile_script:
                    info = tarfile.TarInfo("compile.sh")
                    payload = compile_script.encode("utf-8")
                    info.size = len(payload)
                    info.mode = 0o755
                    tar.addfile(info, io.BytesIO(payload))
        return archive

    def _excluded(self, path: Path, source: Path) -> bool:
        relative = path.relative_to(source)
        if path.name in self.EXCLUDED_NAMES:
            return True
        return any(part in self.EXCLUDED_DIRS for part in relative.parts)

    def _default_compile_script(self, source: Path) -> str | None:
        entry = self._python_entrypoint(source)
        if entry is None:
            return None
        return (
            "#!/bin/sh\n"
            "set -eu\n"
            "cat > executable <<'EOF'\n"
            "#!/bin/sh\n"
            "DIR=$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)\n"
            f"exec python3 \"$DIR/{entry}\" \"$@\"\n"
            "EOF\n"
            "chmod +x executable\n"
        )

    def _python_entrypoint(self, source: Path) -> str | None:
        for candidate in ("main.py", "setup.py", "program.py", "cli.py"):
            if (source / candidate).exists():
                return candidate
        python_files = sorted(
            path
            for path in source.rglob("*.py")
            if not self._excluded(path, source)
        )
        if not python_files:
            return None
        ranked = sorted(
            python_files,
            key=lambda path: self._entrypoint_rank(path),
        )
        return ranked[0].relative_to(source).as_posix()

    def _entrypoint_rank(self, path: Path) -> tuple[int, str]:
        name = path.name.lower()
        content = path.read_text(encoding="utf-8", errors="ignore")
        has_main_guard = "__name__" in content and "__main__" in content
        name_score = 0 if any(token in name for token in ("main", "cli", "program")) else 1
        guard_score = 0 if has_main_guard else 1
        return (guard_score, name_score, path.as_posix())
