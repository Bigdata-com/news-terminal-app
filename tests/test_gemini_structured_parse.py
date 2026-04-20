"""Tests for structured Gemini response parsing helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from google.genai import types
from pydantic import BaseModel

from services.gemini_service import (
    _concatenate_candidate_text,
    _consume_structured_response,
    _decode_structured_json,
    _merge_structured_generation_config,
)


class _SampleModel(BaseModel):
    """Minimal schema for JSON decode tests."""

    field_a: str


def test_decode_structured_json_object() -> None:
    raw = '{"field_a": "ok"}'
    out = _decode_structured_json(raw, _SampleModel, expect_list=False)
    assert out is not None
    assert out.field_a == "ok"


def test_decode_structured_json_list() -> None:
    raw = '[{"field_a": "x"}, {"field_a": "y"}]'
    out = _decode_structured_json(raw, _SampleModel, expect_list=True)
    assert out is not None
    assert len(out) == 2
    assert [m.field_a for m in out] == ["x", "y"]


def test_concatenate_candidate_text_skips_thought_when_configured() -> None:
    response = types.GenerateContentResponse.model_validate(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": '{"field_a": "z"}', "thought": True}],
                    },
                    "finish_reason": "STOP",
                }
            ],
        }
    )
    assert _concatenate_candidate_text(response, include_thoughts=False) is None
    assert _concatenate_candidate_text(response, include_thoughts=True) == '{"field_a": "z"}'


def test_consume_structured_response_parses_thought_only_json() -> None:
    response = types.GenerateContentResponse.model_validate(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": '{"field_a": "from_thought"}', "thought": True}],
                    },
                    "finish_reason": "STOP",
                }
            ],
        }
    )
    model = _consume_structured_response(response, _SampleModel, expect_list=False)
    assert model.field_a == "from_thought"


def test_merge_structured_generation_config_adds_thinking_disable() -> None:
    cfg = _merge_structured_generation_config(_SampleModel, {})
    assert cfg["response_mime_type"] == "application/json"
    assert cfg["response_schema"] is _SampleModel
    assert cfg["thinking_config"] == types.ThinkingConfig(thinking_budget=0)


def test_merge_structured_generation_config_respects_explicit_thinking() -> None:
    custom = types.ThinkingConfig(thinking_budget=-1)
    cfg = _merge_structured_generation_config(_SampleModel, {"thinking_config": custom})
    assert cfg["thinking_config"] is custom


def test_consume_structured_response_returns_parsed_when_set() -> None:
    instance = _SampleModel(field_a="preset")
    response = MagicMock(spec=types.GenerateContentResponse)
    response.parsed = instance
    response.text = None
    response.candidates = None
    out = _consume_structured_response(
        response, _SampleModel, expect_list=False
    )
    assert out is instance
