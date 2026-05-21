from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "output" / "file_bridge_manual" / "htmlq_patch4.py"
HARNESS_PATH = ROOT / "output" / "file_bridge_manual" / "run_htmlq_file_bridge.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_patch():
    return load_module(PATCH_PATH, "htmlq_patch4")


def load_harness():
    return load_module(HARNESS_PATH, "run_htmlq_file_bridge")


def text_for(module, html: str, selector: str) -> list[str]:
    roots = module.parse_html(html.encode("utf-8"))
    nodes = module.select_nodes(roots, [selector])
    return [module.get_text_content(node) for node in nodes]


def test_explicit_combinators_ignore_surrounding_whitespace():
    module = load_patch()
    html = (
        "<section>"
        "<div><span>nested</span></div>"
        "<span>direct</span><p>para</p><span>after</span>"
        "</section>"
    )

    assert text_for(module, html, "section > span") == ["direct", "after"]
    assert text_for(module, html, "p + span") == ["after"]
    assert text_for(module, html, "div ~ span") == ["direct", "after"]


def test_common_structural_pseudo_classes_are_generalized():
    module = load_patch()
    html = (
        "<main>"
        "<section><p>solo</p></section>"
        "<ul><li>A</li><li>B</li><p>P</p><li>C</li><li><span>D</span></li></ul>"
        "<div></div><div> </div>"
        "</main>"
    )
    roots = module.parse_html(html.encode("utf-8"))

    assert text_for(module, html, "section > p:only-child") == ["solo"]
    assert text_for(module, html, "li:nth-of-type(2)") == ["B"]
    assert text_for(module, html, "li:nth-last-of-type(2)") == ["C"]
    assert text_for(module, html, "li:first-of-type") == ["A"]
    assert text_for(module, html, "li:last-of-type") == ["D"]
    assert text_for(module, html, "p:only-of-type") == ["solo", "P"]
    assert len(module.select_nodes(roots, ["div:empty"])) == 1


def test_selector_group_split_respects_function_arguments():
    module = load_patch()
    html = "<main><p>A</p><p class='skip'>B</p><p id='keep'>C</p><span>D</span></main>"

    assert text_for(module, html, "p:not(.skip, #keep), span") == ["A", "D"]


def test_patch4_is_registered_and_config_is_file_bridge_only():
    harness = load_harness()

    assert harness.SOURCES["patch4"].name == "htmlq_patch4.py"
    config_path = ROOT / "output" / "file_bridge_manual" / "_test_htmlq_config.yaml"
    request_dir = ROOT / "output" / "file_bridge_manual" / "_test_htmlq_requests"
    try:
        harness.write_config(config_path, request_dir, "codex-file-bridge-htmlq-test")
        config_text = config_path.read_text(encoding="utf-8")
    finally:
        config_path.unlink(missing_ok=True)

    assert 'provider: "file_bridge"' in config_text
    assert "glm:" not in config_text
    assert "kimi:" not in config_text
    assert "local_openai:" not in config_text
