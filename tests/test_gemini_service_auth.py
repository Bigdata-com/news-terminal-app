"""Tests for GeminiService authentication resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.gemini_service import GeminiService


def test_api_key_auth_when_vertex_disabled(monkeypatch: pytest.MonkeyPatch, clear_gemini_env: None) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    with patch("services.gemini_service.genai.Client") as mock_client:
        svc = GeminiService(api_key="test-api-key")
    assert svc.auth_method == "api_key"
    mock_client.assert_called_once()
    kwargs = mock_client.call_args.kwargs
    assert kwargs.get("api_key") == "test-api-key"
    assert kwargs.get("vertexai") is not True


def test_vertex_requires_project(monkeypatch: pytest.MonkeyPatch, clear_gemini_env: None) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        GeminiService()


@patch("services.gemini_service.genai.Client")
@patch("services.gemini_service.service_account.Credentials.from_service_account_file")
@patch("services.gemini_service.os.path.exists", return_value=True)
def test_vertex_service_account_when_file_exists(
    _mock_exists: MagicMock,
    mock_from_sa: MagicMock,
    mock_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clear_gemini_env: None,
) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-sa")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/fake/sa.json")
    creds = MagicMock()
    mock_from_sa.return_value = creds
    svc = GeminiService()
    assert svc.auth_method == "vertex_ai"
    kwargs = mock_client.call_args.kwargs
    assert kwargs["vertexai"] is True
    assert kwargs["project"] == "proj-sa"
    assert kwargs["credentials"] is creds


@patch("services.gemini_service.genai.Client")
@patch("services.gemini_service.google.auth.default")
@patch("services.gemini_service.logger")
def test_vertex_missing_sa_path_logs_and_uses_adc(
    mock_log: MagicMock,
    mock_default: MagicMock,
    mock_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clear_gemini_env: None,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "nonexistent_sa.json"
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-adc")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(missing))
    creds = MagicMock()
    mock_default.return_value = (creds, None)
    svc = GeminiService()
    assert svc.auth_method == "vertex_ai_adc"
    mock_log.warning.assert_called()
    kwargs = mock_client.call_args.kwargs
    assert kwargs["vertexai"] is True
    assert kwargs["project"] == "proj-adc"
    assert kwargs["credentials"] is creds


@patch("services.gemini_service.genai.Client")
@patch("services.gemini_service.google.auth.default")
def test_vertex_adc_when_no_credentials_path(
    mock_default: MagicMock,
    mock_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clear_gemini_env: None,
) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-only-adc")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "europe-west1")
    creds = MagicMock()
    mock_default.return_value = (creds, None)
    svc = GeminiService(location="us-central1")
    assert svc.auth_method == "vertex_ai_adc"
    assert svc.location == "europe-west1"
    kwargs = mock_client.call_args.kwargs
    assert kwargs["vertexai"] is True
    assert kwargs["project"] == "proj-only-adc"
    assert kwargs["credentials"] is creds


@patch("services.gemini_service.genai.Client")
def test_service_account_file_without_vertex_flag_still_uses_vertex_client(
    mock_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    clear_gemini_env: None,
) -> None:
    """Non-Vertex env: existing JSON path uses Vertex-style client (unchanged behavior)."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-path")
    with patch("services.gemini_service.os.path.exists", return_value=True):
        with patch(
            "services.gemini_service.service_account.Credentials.from_service_account_file"
        ) as mock_from_sa:
            mock_from_sa.return_value = MagicMock()
            GeminiService(service_account_path="/fake/creds.json")
    kwargs = mock_client.call_args.kwargs
    assert kwargs["vertexai"] is True
