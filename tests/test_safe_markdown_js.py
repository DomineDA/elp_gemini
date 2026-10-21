"""Shared safe-markdown renderer: one script, tag allowlist, pinned marked."""

import re
from pathlib import Path

import pytest

SAFE_MARKDOWN_JS = Path("app/static/js/safe_markdown.js")
TEMPLATES = [
    Path("app/templates/user/dashboard.html"),
    Path("app/templates/user/report_viewer.html"),
    Path("app/templates/admin/admin_report_viewer.html"),
]


def _allowed_tags() -> set[str]:
    source = SAFE_MARKDOWN_JS.read_text(encoding="utf-8")
    match = re.search(
        r"SAFE_MARKDOWN_TAGS = new Set\(\[(.*?)\]\)", source, re.S
    )
    assert match, "SAFE_MARKDOWN_TAGS allowlist not found"
    return set(re.findall(r"'([a-z0-9]+)'", match.group(1)))


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_templates_load_shared_renderer(template):
    source = template.read_text(encoding="utf-8")

    assert '<script src="/static/js/safe_markdown.js"></script>' in source
    assert "function renderSafeMarkdown(" not in source
    assert "function sanitizeRenderedMarkdown(" not in source


def test_allowlist_keeps_markdown_tags_and_drops_active_content():
    tags = _allowed_tags()

    assert {"blockquote", "br", "p", "a", "img", "input"} <= tags
    for dangerous in (
        "script",
        "iframe",
        "object",
        "embed",
        "svg",
        "math",
        "form",
        "style",
        "link",
        "meta",
        "base",
    ):
        assert dangerous not in tags


def test_sanitizer_removes_disallowed_tags_and_limits_inputs():
    source = SAFE_MARKDOWN_JS.read_text(encoding="utf-8")

    assert "SAFE_MARKDOWN_TAGS.has(" in source
    assert "element.remove()" in source
    assert "'checkbox'" in source


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_templates_pin_marked_version(template):
    source = template.read_text(encoding="utf-8")

    assert re.search(r"cdn\.jsdelivr\.net/npm/marked@\d+\.\d+\.\d+/", source)
    assert "npm/marked/marked.min.js" not in source
