import hashlib
import os
import tarfile

from core.submission.packager import SubmissionPackager


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_submission_packager_creates_programbench_layout(tmp_path):
    generated = tmp_path / "generated" / "task"
    generated.mkdir(parents=True)
    (generated / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (generated / "result.json").write_text("{}", encoding="utf-8")

    archive = SubmissionPackager().package(
        generated_path=generated,
        output_root=tmp_path / "submissions",
        instance_id="owner__repo.abcdef0",
    )

    assert archive == tmp_path / "submissions" / "owner__repo.abcdef0" / "submission.tar.gz"
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "main.py" in names
    assert "compile.sh" in names
    assert "result.json" not in names


def test_submission_packager_excludes_reference_and_evidence_artifacts(tmp_path):
    generated = tmp_path / "generated" / "task"
    generated.mkdir(parents=True)
    (generated / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (generated / "executable").write_text("reference", encoding="utf-8")
    (generated / "evidence").mkdir()
    (generated / "evidence" / "record.json").write_text("{}", encoding="utf-8")
    (generated / ".rebuilder").mkdir()
    (generated / ".rebuilder" / "implementation_raw.txt").write_text("debug", encoding="utf-8")

    archive = SubmissionPackager().package(generated, tmp_path / "out", "sample")

    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "main.py" in names
    assert "executable" not in names
    assert "evidence/record.json" not in names
    assert ".rebuilder/implementation_raw.txt" not in names


def test_submission_packager_excludes_local_repo_and_cache_artifacts(tmp_path):
    generated = tmp_path / "generated" / "task"
    generated.mkdir(parents=True)
    (generated / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (generated / "submission.tar.gz").write_text("old archive", encoding="utf-8")
    (generated / ".git").mkdir()
    (generated / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (generated / ".pytest_cache").mkdir()
    (generated / ".pytest_cache" / "state").write_text("cache", encoding="utf-8")
    (generated / "node_modules").mkdir()
    (generated / "node_modules" / "tool.js").write_text("console.log('x')\n", encoding="utf-8")

    archive = SubmissionPackager().package(generated, tmp_path / "out", "sample")

    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "main.py" in names
    assert "submission.tar.gz" not in names
    assert ".git/config" not in names
    assert ".pytest_cache/state" not in names
    assert "node_modules/tool.js" not in names


def test_submission_packager_creates_reproducible_archives_for_same_contents(tmp_path):
    first_source = tmp_path / "first" / "task"
    second_source = tmp_path / "second" / "task"
    first_source.mkdir(parents=True)
    second_source.mkdir(parents=True)
    for source in (first_source, second_source):
        (source / "main.py").write_text("print('hi')\n", encoding="utf-8")
    os.utime(first_source / "main.py", (100, 100))
    os.utime(second_source / "main.py", (200, 200))

    first_archive = SubmissionPackager().package(first_source, tmp_path / "out-first", "sample")
    second_archive = SubmissionPackager().package(second_source, tmp_path / "out-second", "sample")

    assert _sha256(first_archive) == _sha256(second_archive)
    with tarfile.open(first_archive, "r:gz") as tar:
        main_member = tar.getmember("main.py")
    assert main_member.mtime == 0
    assert main_member.uid == 0
    assert main_member.gid == 0
    assert main_member.uname == ""
    assert main_member.gname == ""


def test_submission_packager_adds_compile_script_for_python_entrypoint(tmp_path):
    generated = tmp_path / "generated" / "task"
    generated.mkdir(parents=True)
    (generated / "setup.py").write_text("#!/usr/bin/env python3\nprint('hi')\n", encoding="utf-8")

    archive = SubmissionPackager().package(generated, tmp_path / "out", "sample")

    with tarfile.open(archive, "r:gz") as tar:
        compile_member = tar.getmember("compile.sh")
        content = tar.extractfile("compile.sh").read().decode("utf-8")
    assert compile_member.mode & 0o111
    assert "setup.py" in content
    assert "python3" in content
    assert "chmod +x executable" in content


def test_submission_packager_prefers_main_like_python_entrypoint(tmp_path):
    generated = tmp_path / "generated" / "task"
    generated.mkdir(parents=True)
    (generated / "db.py").write_text("print('db')\n", encoding="utf-8")
    (generated / "main.main.py").write_text(
        "def main():\n"
        "    print('main')\n"
        "if __name__ == '__main__':\n"
        "    main()\n",
        encoding="utf-8",
    )
    (generated / "query.py").write_text("print('query')\n", encoding="utf-8")

    archive = SubmissionPackager().package(generated, tmp_path / "out", "sample")

    with tarfile.open(archive, "r:gz") as tar:
        content = tar.extractfile("compile.sh").read().decode("utf-8")
    assert "main.main.py" in content
    assert "db.py" not in content
