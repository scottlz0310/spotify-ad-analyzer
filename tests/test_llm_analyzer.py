from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Self, final
from unittest.mock import patch

import pytest

from src.llm_analyzer import (
    LlmAnalysisResult,
    OllamaError,
    _parse_response,  # pyright: ignore[reportPrivateUsage]
    analyze_transcript,
)


@final
class _MockHttpResponse:
    """Minimal urllib HTTP response mock supporting the context-manager protocol."""

    def __init__(self, data: bytes) -> None:
        self._data: bytes = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        pass


def _ollama_bytes(response_text: str) -> bytes:
    return json.dumps({"response": response_text, "done": True}).encode()


# ─── _parse_response ─────────────────────────────────────────────────────────


class TestParseResponse:
    def test_all_fields_present(self) -> None:
        raw = json.dumps(
            {
                "product_name": "BrandX",
                "ad_type": "product",
                "summary": "BrandX is great.",
                "tone": "energetic",
            }
        )
        result = _parse_response(raw)
        assert result.product_name == "BrandX"
        assert result.ad_type == "product"
        assert result.summary == "BrandX is great."
        assert result.tone == "energetic"
        assert result.raw_response == raw

    def test_null_values_become_none(self) -> None:
        raw = json.dumps(
            {"product_name": None, "ad_type": None, "summary": None, "tone": None}
        )
        result = _parse_response(raw)
        assert result.product_name is None
        assert result.ad_type is None
        assert result.summary is None
        assert result.tone is None

    def test_empty_string_becomes_none(self) -> None:
        raw = json.dumps(
            {"product_name": "", "ad_type": "  ", "summary": "Valid.", "tone": "calm"}
        )
        result = _parse_response(raw)
        assert result.product_name is None
        assert result.ad_type is None
        assert result.summary == "Valid."
        assert result.tone == "calm"

    def test_markdown_json_fence_stripped(self) -> None:
        inner = json.dumps(
            {"product_name": "Foo", "ad_type": "brand", "summary": None, "tone": None}
        )
        raw = f"```json\n{inner}\n```"
        result = _parse_response(raw)
        assert result.product_name == "Foo"
        assert result.ad_type == "brand"

    def test_plain_code_fence_stripped(self) -> None:
        inner = json.dumps(
            {"product_name": "Bar", "ad_type": None, "summary": None, "tone": None}
        )
        raw = f"```\n{inner}\n```"
        result = _parse_response(raw)
        assert result.product_name == "Bar"

    def test_invalid_json_returns_all_none_with_raw(self) -> None:
        raw = "I cannot analyze this advertisement."
        result = _parse_response(raw)
        assert result.product_name is None
        assert result.ad_type is None
        assert result.summary is None
        assert result.tone is None
        assert result.raw_response == raw

    def test_non_dict_json_returns_all_none_with_raw(self) -> None:
        raw = json.dumps(["not", "a", "dict"])
        result = _parse_response(raw)
        assert result.product_name is None
        assert result.raw_response == raw

    def test_partial_fields_filled(self) -> None:
        raw = json.dumps({"product_name": "Acme", "summary": "Acme does stuff."})
        result = _parse_response(raw)
        assert result.product_name == "Acme"
        assert result.summary == "Acme does stuff."
        assert result.ad_type is None
        assert result.tone is None


# ─── analyze_transcript ──────────────────────────────────────────────────────


class TestAnalyzeTranscript:
    def test_successful_request_returns_result(self) -> None:
        payload = json.dumps(
            {
                "product_name": "Spotify",
                "ad_type": "service",
                "summary": "Music app.",
                "tone": "calm",
            }
        )
        mock_resp = _MockHttpResponse(_ollama_bytes(payload))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = analyze_transcript("Listen to Spotify Premium.")
        assert result.product_name == "Spotify"
        assert result.ad_type == "service"

    def test_ollama_unreachable_raises_ollama_error(self) -> None:
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError("Connection refused"),
            ),
            pytest.raises(OllamaError, match="Cannot reach Ollama"),
        ):
            _ = analyze_transcript("some ad transcript")

    def test_custom_model_sent_in_request(self) -> None:
        payload = json.dumps(
            {"product_name": None, "ad_type": None, "summary": None, "tone": None}
        )
        mock_resp = _MockHttpResponse(_ollama_bytes(payload))
        captured: list[urllib.request.Request] = []

        def _fake_urlopen(
            req: urllib.request.Request,
            *,
            timeout: float,
        ) -> _MockHttpResponse:
            _ = timeout
            captured.append(req)
            return mock_resp

        with patch("urllib.request.urlopen", _fake_urlopen):
            _ = analyze_transcript("ad", model="mistral")

        assert len(captured) == 1
        req_data = captured[0].data
        assert isinstance(req_data, bytes)
        body = json.loads(req_data)
        assert body["model"] == "mistral"

    def test_empty_transcript_does_not_raise(self) -> None:
        payload = json.dumps(
            {"product_name": None, "ad_type": None, "summary": None, "tone": None}
        )
        mock_resp = _MockHttpResponse(_ollama_bytes(payload))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = analyze_transcript("")
        assert result.raw_response != ""

    def test_non_json_response_body_raises_ollama_error(self) -> None:
        mock_resp = _MockHttpResponse(b"Internal Server Error")
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            pytest.raises(OllamaError, match="non-JSON"),
        ):
            _ = analyze_transcript("some transcript")

    def test_non_dict_json_response_raises_ollama_error(self) -> None:
        mock_resp = _MockHttpResponse(json.dumps(["error", "list"]).encode())
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            pytest.raises(OllamaError, match="not a JSON object"),
        ):
            _ = analyze_transcript("some transcript")

    def test_default_model_from_config(self) -> None:
        payload = json.dumps(
            {"product_name": None, "ad_type": None, "summary": None, "tone": None}
        )
        mock_resp = _MockHttpResponse(_ollama_bytes(payload))
        captured: list[urllib.request.Request] = []

        def _fake_urlopen(
            req: urllib.request.Request,
            *,
            timeout: float,
        ) -> _MockHttpResponse:
            _ = timeout
            captured.append(req)
            return mock_resp

        with patch("urllib.request.urlopen", _fake_urlopen):
            _ = analyze_transcript("ad")

        req_data = captured[0].data
        assert isinstance(req_data, bytes)
        body = json.loads(req_data)
        assert body["model"] == "qwen3.5"


# ─── LlmAnalysisResult ───────────────────────────────────────────────────────


class TestLlmAnalysisResult:
    def test_repr_contains_all_fields(self) -> None:
        r = LlmAnalysisResult(
            product_name="TestBrand",
            ad_type="product",
            summary="A test.",
            tone="calm",
            raw_response="raw",
        )
        rep = repr(r)
        assert "product_name='TestBrand'" in rep
        assert "ad_type='product'" in rep
        assert "tone='calm'" in rep

    def test_repr_with_none_fields(self) -> None:
        r = LlmAnalysisResult(
            product_name=None,
            ad_type=None,
            summary=None,
            tone=None,
            raw_response="",
        )
        assert "product_name=None" in repr(r)
