"""Pytest configuration."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture
def clear_gemini_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove Gemini / GCP auth env vars so tests control configuration."""
    keys = [
        "GOOGLE_GENAI_USE_VERTEXAI",
        "USE_ADC",
        "GEMINI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_CLOUD_QUOTA_PROJECT",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def clear_bigdata_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove server-side Bigdata key so web-app tests cannot fall back to env."""
    monkeypatch.delenv("BIGDATA_API_KEY", raising=False)
    yield
