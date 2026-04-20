"""Tests for CLI topic display helpers (scripts/cli_topic_search.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_cli_topic_search():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "cli_topic_search.py"
    spec = importlib.util.spec_from_file_location("cli_topic_search", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_format_default_topic_for_display_dict() -> None:
    mod = _load_cli_topic_search()
    row = {"topic_name": "Financial Metrics", "topic_text": "Hello {company} end"}
    assert mod.format_default_topic_for_display(row, "Acme") == "Hello Acme end"


def test_format_default_topic_for_display_legacy_string() -> None:
    mod = _load_cli_topic_search()
    assert mod.format_default_topic_for_display("Hi {company}", "Beta") == "Hi Beta"
