"""Create ProgramBench-compatible submission archives."""

from __future__ import annotations

import gzip
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
        "submission.tar.gz",
    }
    EXCLUDED_DIRS = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "evidence",
        "reports",
        "compliance",
        "logs",
        "node_modules",
        "__pycache__",
        ".rebuilder",
        ".venv",
        "venv",
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
        with archive.open("wb") as raw_archive:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_archive,
                mtime=0,
            ) as gzip_archive:
                with tarfile.open(fileobj=gzip_archive, mode="w") as tar:
                    for path in sorted(source.rglob("*")):
                        if not path.is_file() or self._excluded(path, source):
                            continue
                        tar.add(
                            path,
                            arcname=path.relative_to(source).as_posix(),
                            filter=self._normalize_tarinfo,
                        )
                    if not (source / "compile.sh").exists():
                        compile_script = self._default_compile_script(source)
                        if compile_script:
                            self._add_bytes(
                                tar,
                                name="compile.sh",
                                payload=compile_script.encode("utf-8"),
                                mode=0o755,
                            )
        return archive

    def _add_bytes(
        self,
        tar: tarfile.TarFile,
        *,
        name: str,
        payload: bytes,
        mode: int,
    ) -> None:
        info = tarfile.TarInfo(name)
        info.size = len(payload)
        info.mode = mode
        tar.addfile(self._normalize_tarinfo(info), io.BytesIO(payload))

    def _normalize_tarinfo(self, info: tarfile.TarInfo) -> tarfile.TarInfo:
        executable = bool(info.mode & 0o111) or info.name == "compile.sh"
        info.mode = 0o755 if executable else 0o644
        info.mtime = 0
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        return info

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

    def _entrypoint_rank(self, path: Path) -> tuple[int, int, str]:
        name = path.name.lower()
        content = path.read_text(encoding="utf-8", errors="ignore")
        has_main_guard = "__name__" in content and "__main__" in content
        name_score = 0 if any(token in name for token in ("main", "cli", "program")) else 1
        guard_score = 0 if has_main_guard else 1
        return (guard_score, name_score, path.as_posix())
