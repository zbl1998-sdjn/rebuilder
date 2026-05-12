from core.compliance.scanner import ComplianceScanner


def test_scanner_flags_binary_wrapping_patterns():
    files = {
        "compile.sh": "cp ./executable ./solution\nchmod +x ./solution\n",
        "main.py": "import subprocess\nsubprocess.run(['./executable'])\n",
    }

    report = ComplianceScanner().scan_files(files)

    assert not report.passed
    rule_ids = {finding.rule_id for finding in report.findings}
    assert "binary_wrapping.copy_reference_binary" in rule_ids
    assert "binary_wrapping.exec_reference_binary" in rule_ids


def test_scanner_flags_source_lookup_and_binary_analysis_patterns():
    files = {
        "notes.sh": "git clone https://github.com/example/original\nobjdump -d ./executable\n",
    }

    report = ComplianceScanner().scan_files(files)

    assert not report.passed
    rule_ids = {finding.rule_id for finding in report.findings}
    assert "source_lookup.git_clone" in rule_ids
    assert "binary_analysis.disassembler" in rule_ids


def test_scanner_allows_ordinary_reimplementation_code():
    files = {
        "main.py": (
            "import argparse\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('--input')\n"
            "args = parser.parse_args()\n"
            "print(args.input or '')\n"
        )
    }

    report = ComplianceScanner().scan_files(files)

    assert report.passed
    assert report.findings == []
