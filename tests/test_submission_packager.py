import tarfile

from core.submission.packager import SubmissionPackager


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
