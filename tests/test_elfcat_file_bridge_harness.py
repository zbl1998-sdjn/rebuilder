from __future__ import annotations

import importlib.util
import os
import base64
import struct
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "output" / "file_bridge_manual" / "run_elfcat_file_bridge.py"
PATCH_VARIANT = "reference_html_patch3"


def load_harness():
    spec = importlib.util.spec_from_file_location("run_elfcat_file_bridge", HARNESS_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_main_py(artifact: str) -> str:
    start = "--- FILE: main.py ---\n"
    end = "\n--- END FILE ---"
    assert artifact.startswith(start)
    assert artifact.endswith(end + "\n") or artifact.endswith(end)
    return artifact[len(start) : artifact.rfind(end)]


def elf64_header(
    *, endian: str = "<", elf_type: int = 2, machine: int = 62, osabi: int = 0, abi_version: int = 0
) -> bytes:
    data_encoding = 1 if endian == "<" else 2
    ident = b"\x7fELF" + bytes([2, data_encoding, 1, osabi, abi_version]) + b"\x00" * 7
    return ident + struct.pack(
        endian + "HHIQQQIHHHHHH",
        elf_type,
        machine,
        1,
        0,
        0,
        0,
        0,
        64,
        0,
        0,
        0,
        0,
        0,
    )


def malformed_string_table_elf64() -> bytes:
    header = b"\x7fELF" + bytes([2, 1, 1, 0, 0]) + b"\x00" * 7
    header += struct.pack(
        "<HHIQQQIHHHHHH",
        2,
        62,
        1,
        0,
        0,
        64,
        0,
        64,
        0,
        0,
        64,
        1,
        0,
    )
    section = struct.pack("<IIQQQQIIQQ", 0, 3, 0, 0, 4096, 8, 0, 0, 1, 0)
    return header + section


def one_null_section_elf64() -> bytes:
    header = b"\x7fELF" + bytes([2, 1, 1, 0, 0]) + b"\x00" * 7
    header += struct.pack(
        "<HHIQQQIHHHHHH",
        2,
        62,
        1,
        0,
        0,
        64,
        0,
        64,
        0,
        0,
        64,
        1,
        0,
    )
    return header + (b"\x00" * 64)


def one_empty_program_header_elf64() -> bytes:
    header = b"\x7fELF" + bytes([2, 1, 1, 0, 0]) + b"\x00" * 7
    header += struct.pack(
        "<HHIQQQIHHHHHH",
        2,
        62,
        1,
        0,
        64,
        0,
        0,
        64,
        56,
        1,
        0,
        0,
        0,
    )
    phdr = struct.pack("<IIQQQQQQ", 1, 4, 0, 0, 0, 0, 0, 0)
    return header + phdr


def shstr_exact_boundary_elf64() -> bytes:
    return base64.b64decode(
        "f0VMRgIBAQAAAAAAAAAAAAIAPgABAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAEAAAAAAAEAAAgAB"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB"
        "AAAAAwAAAAAAAAAAAAAAAAAAAAAAALwAAAAAAAAABAAAAAAAAGEA"
    )


def run_main(main_py: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(main_py), *args],
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_reference_html_patch_renders_elfcat_shell_and_metadata(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    (tmp_path / ".hiddenelf").write_bytes(elf64_header())

    result = run_main(main_py, [".hiddenelf"], tmp_path)

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    html_text = (tmp_path / ".hiddenelf.html").read_text(encoding="utf-8")
    assert html_text.startswith("<!doctype html>\n<html>\n  <head>\n")
    assert "<title>.hiddenelf</title>" in html_text
    assert "generated with elfcat 0.1.10" in html_text
    assert "<tr class='fileinfo_file_name'> <td>File name:</td> <td>.hiddenelf</td> </tr>" in html_text
    assert "<tr class='fileinfo_class'> <td>Object class:</td> <td>64-bit</td> </tr>" in html_text
    assert "<tr class='fileinfo_abi_ver'>" not in html_text
    assert "<span class='e_type'>02 00</span>" in html_text
    assert "<span class='e_machine'>3e 00</span>" in html_text
    assert "<div id='bytes'><span class='ehdr'>" in html_text
    assert "<div id='ascii'>.ELF............" in html_text


def test_reference_html_patch_handles_paths_big_endian_and_aarch64(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    nested = tmp_path / "dir with space"
    nested.mkdir()
    (nested / "minimal file.elf").write_bytes(elf64_header())
    (tmp_path / "minimal_be.elf").write_bytes(elf64_header(endian=">"))
    (tmp_path / "dyn_aarch64.elf").write_bytes(elf64_header(elf_type=3, machine=183))

    spaced = run_main(main_py, ["dir with space/minimal file.elf"], tmp_path)
    big_endian = run_main(main_py, ["minimal_be.elf"], tmp_path)
    aarch64 = run_main(main_py, ["dyn_aarch64.elf"], tmp_path)

    assert spaced.returncode == 0
    assert big_endian.returncode == 0
    assert aarch64.returncode == 0
    assert (tmp_path / "minimal file.elf.html").exists()
    spaced_html = (tmp_path / "minimal file.elf.html").read_text(encoding="utf-8")
    assert "<title>minimal file.elf</title>" in spaced_html
    assert (
        "<tr class='fileinfo_file_name'> <td>File name:</td> "
        "<td>dir with space/minimal file.elf</td> </tr>"
    ) in spaced_html
    big_html = (tmp_path / "minimal_be.elf.html").read_text(encoding="utf-8")
    assert "<tr class='fileinfo_data'> <td>Data encoding:</td> <td>Big endian</td> </tr>" in big_html
    assert "<span class='e_type'>00 02</span>" in big_html
    dyn_html = (tmp_path / "dyn_aarch64.elf.html").read_text(encoding="utf-8")
    assert "<tr class='fileinfo_e_type'> <td>Type:</td> <td>Shared object file (DYN)</td> </tr>" in dyn_html
    assert "<tr class='fileinfo_e_machine'> <td>Architecture:</td> <td>ARM Aarch64</td> </tr>" in dyn_html


def test_reference_html_patch_renders_tail_bytes_without_extra_close_newline(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    (tmp_path / "note_segment.elf").write_bytes(elf64_header() + b"\x00" * 56)

    result = run_main(main_py, ["note_segment.elf"], tmp_path)

    assert result.returncode == 0
    html_text = (tmp_path / "note_segment.elf.html").read_text(encoding="utf-8")
    assert "<div id='offsets'>0\n10\n20\n30\n40\n50\n60\n70</div>" in html_text
    assert (
        "<span class='e_shstrndx'>00 00</span></span>\n"
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
    ) in html_text
    assert "........</div>\n    <table id='sticky_table'" in html_text


def test_reference_html_patch_renders_exact_tail_rows_without_close_newline(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    (tmp_path / "tiny_shentsize.elf").write_bytes(elf64_header() + b"\x00" * 64)

    result = run_main(main_py, ["tiny_shentsize.elf"], tmp_path)

    assert result.returncode == 0
    html_text = (tmp_path / "tiny_shentsize.elf.html").read_text(encoding="utf-8")
    assert (
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00</div>\n"
        "    <div id='ascii'>"
    ) in html_text
    assert (
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00\n</div>\n"
        "    <div id='ascii'>"
    ) not in html_text


def test_reference_html_patch_renders_null_section_header_tables(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    (tmp_path / "one_section.elf").write_bytes(one_null_section_elf64())

    result = run_main(main_py, ["one_section.elf"], tmp_path)

    assert result.returncode == 0
    html_text = (tmp_path / "one_section.elf.html").read_text(encoding="utf-8")
    assert "<span class='bin_shdr0 shdr'><span class='sh_name'>00 00 00 00</span>" in html_text
    assert "<table class='conceal itable' id='info_shdr0'>" in html_text
    assert "<tr> <td>Type:</td> <td>NULL</td> </tr>" in html_text
    assert "<table class='conceal itable' id='info_section0'>" in html_text
    assert "connect('.bin_shdr0 > .sh_offset', '.bin_section0');" in html_text
    assert (
        "      connect('.e_shoff', '.bin_shdr0');\n"
        "      connect('.bin_shdr0 > .sh_offset', '.bin_section0');\n"
        "      pushArrowElems();"
    ) in html_text


def test_reference_html_patch_renders_program_header_tables(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    (tmp_path / "one_phdr.elf").write_bytes(one_empty_program_header_elf64())

    result = run_main(main_py, ["one_phdr.elf"], tmp_path)

    assert result.returncode == 0
    html_text = (tmp_path / "one_phdr.elf.html").read_text(encoding="utf-8")
    assert "<span class='bin_phdr0 phdr'><span class='p_type'>01 00 00 00</span>" in html_text
    assert "<span class='p_flags'>04 00 00 00</span>" in html_text
    assert "<table class='conceal itable' id='info_phdr0'>" in html_text
    assert "<tr> <td>Type:</td> <td>LOAD</td> </tr>" in html_text
    assert "<tr> <td>Flags:</td> <td>R</td> </tr>" in html_text
    assert "<table class='conceal itable' id='info_segment0'>" in html_text
    assert "connect('.bin_phdr0 > .p_offset', '.bin_segment0');" in html_text
    assert (
        "      connect('.e_shoff', '.bin_shdr0');\n"
        "      connect('.bin_phdr0 > .p_offset', '.bin_segment0');\n"
        "      pushArrowElems();"
    ) in html_text


def test_reference_html_patch_treats_backslash_path_like_linux_literal(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "winpath.elf").write_bytes(elf64_header())

    result = run_main(main_py, ["nested\\winpath.elf"], tmp_path)

    assert result.returncode == 1
    assert result.stdout == ""
    assert (
        result.stderr
        == 'Failed to read file "nested\\winpath.elf": No such file or directory (os error 2)\n'
    )
    assert not (tmp_path / "winpath.elf.html").exists()


def test_reference_html_patch_labels_linux_abi_and_version(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    (tmp_path / "gnu_osabi.elf").write_bytes(elf64_header(osabi=3, abi_version=1))

    result = run_main(main_py, ["gnu_osabi.elf"], tmp_path)

    assert result.returncode == 0
    html_text = (tmp_path / "gnu_osabi.elf.html").read_text(encoding="utf-8")
    assert "<tr class='fileinfo_abi'> <td>Uncommon ABI(!):</td> <td>Linux</td> </tr>" in html_text
    assert "<tr class='fileinfo_abi_ver'> <td>ABI version:</td> <td>1</td> </tr>" in html_text
    assert "<div id='offsets'>0\n10\n20\n30\n</div>" in html_text
    assert "<span class='abi'>03</span> <span class='abi_ver'>01</span>" in html_text
    assert "....@...........\n</div>\n    <table id='sticky_table'" in html_text


def test_reference_html_patch_preserves_out_of_range_string_table_panic_shape(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    (tmp_path / "strings.elf").write_bytes(malformed_string_table_elf64())

    result = run_main(main_py, ["strings.elf"], tmp_path)

    assert result.returncode == 101
    assert result.stdout == ""
    assert result.stderr.startswith("\nthread 'main' (1) panicked at src/elf/parser.rs:117:18:\n")
    assert "index out of bounds: the len is 128 but the index is 4103" in result.stderr
    assert "note: run with `RUST_BACKTRACE=1` environment variable" in result.stderr
    assert not (tmp_path / "strings.elf.html").exists()


def test_reference_html_patch_preserves_shstr_exact_panic_shape(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    (tmp_path / "shstr_exact.elf").write_bytes(shstr_exact_boundary_elf64())

    result = run_main(main_py, ["shstr_exact.elf"], tmp_path)

    assert result.returncode == 101
    assert result.stdout == ""
    assert result.stderr.startswith("\nthread 'main' (1) panicked at src/elf/elfxx.rs:227:46:\n")
    assert "range end index 192 out of range for slice of length 168" in result.stderr
    assert "note: run with `RUST_BACKTRACE=1` environment variable" in result.stderr
    assert not (tmp_path / "shstr_exact.elf.html").exists()


def test_reference_html_patch_reports_directory_input_like_reference(tmp_path: Path) -> None:
    harness = load_harness()
    main_py = tmp_path / "main.py"
    main_py.write_text(
        extract_main_py(harness.implementation_artifact(PATCH_VARIANT)),
        encoding="utf-8",
    )
    directory = tmp_path / "dir"
    directory.mkdir()
    (directory / "a.txt").write_text("alpha\n", encoding="utf-8")
    nested = directory / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("bravo\n", encoding="utf-8")

    result = run_main(main_py, ["dir"], tmp_path)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == 'Failed to read file "dir": Is a directory (os error 21)\n'
