from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import TypedDict, cast, final, override

from src import config

_logger = logging.getLogger(__name__)

_ANALYZE_PROMPT = """\
You are an advertising analyst. Analyze the Spotify advertisement transcript below.

Respond with ONLY a valid JSON object containing exactly these fields:
- "product_name": name of the product or service advertised (string, or null)
- "ad_type": one of "product", "service", "brand", "promotion", "event", "other" \
(string, or null)
- "summary": one to two sentences describing what the ad is about (string, or null)
- "tone": one of "energetic", "calm", "humorous", "serious", "inspirational", \
"urgent", "other" (string, or null)

Do not include any text outside the JSON object.

Transcript:
{transcript}
"""


class _OllamaResponse(TypedDict, total=False):
    response: str
    model: str
    done: bool


class OllamaError(RuntimeError):
    """Raised when the Ollama API is unreachable or returns an unexpected response."""


@final
class LlmAnalysisResult:
    """Structured analysis result extracted from an ad transcript by the LLM."""

    __slots__ = ("ad_type", "product_name", "raw_response", "summary", "tone")

    def __init__(
        self,
        *,
        product_name: str | None,
        ad_type: str | None,
        summary: str | None,
        tone: str | None,
        raw_response: str,
    ) -> None:
        self.product_name = product_name
        self.ad_type = ad_type
        self.summary = summary
        self.tone = tone
        self.raw_response = raw_response

    @override
    def __repr__(self) -> str:
        return (
            f"LlmAnalysisResult("
            f"product_name={self.product_name!r}, "
            f"ad_type={self.ad_type!r}, "
            f"summary={self.summary!r}, "
            f"tone={self.tone!r})"
        )


def analyze_transcript(
    transcript: str,
    *,
    model: str | None = None,
) -> LlmAnalysisResult:
    """Send *transcript* to Ollama and return a structured :class:`LlmAnalysisResult`.

    Args:
        transcript: Full ad transcript text from the transcription stage.
        model: Ollama model name override. Defaults to :data:`config.OLLAMA_MODEL`.

    Raises:
        OllamaError: If the Ollama endpoint is unreachable or returns a network error.

    """
    effective_model = model if model is not None else config.OLLAMA_MODEL
    prompt = _ANALYZE_PROMPT.format(transcript=transcript)

    url = f"http://{config.OLLAMA_HOST}/api/generate"
    payload = json.dumps(
        {"model": effective_model, "prompt": prompt, "stream": False}
    ).encode()

    req = urllib.request.Request(  # noqa: S310
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
            raw_data = resp.read()
    except urllib.error.URLError as exc:
        msg = f"Cannot reach Ollama at {config.OLLAMA_HOST}: {exc}"
        raise OllamaError(msg) from exc

    try:
        parsed = json.loads(raw_data)
    except (json.JSONDecodeError, TypeError) as exc:
        msg = f"Ollama returned non-JSON response: {exc}"
        raise OllamaError(msg) from exc

    if not isinstance(parsed, dict):
        msg = f"Ollama response is not a JSON object (got {type(parsed).__name__})"
        raise OllamaError(msg)

    body = cast("_OllamaResponse", cast("object", parsed))
    raw_response = body.get("response", "")
    _logger.debug("Ollama raw_response length=%d", len(raw_response))
    return _parse_response(raw_response)


def _parse_response(raw: str) -> LlmAnalysisResult:
    """Extract structured fields from a raw LLM response string.

    Handles Markdown code fences (```json ... ```) and falls back gracefully
    when the response is not valid JSON.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.startswith("```")]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        _logger.warning("LLM response is not valid JSON; storing raw_response only")
        return LlmAnalysisResult(
            product_name=None,
            ad_type=None,
            summary=None,
            tone=None,
            raw_response=raw,
        )

    if not isinstance(parsed, dict):
        _logger.warning(
            "LLM response JSON is not an object (got %s); storing raw_response only",
            type(parsed).__name__,
        )
        return LlmAnalysisResult(
            product_name=None,
            ad_type=None,
            summary=None,
            tone=None,
            raw_response=raw,
        )

    data = cast("dict[str, object]", parsed)

    def _str_or_none(key: str) -> str | None:
        val = data.get(key)
        if not isinstance(val, str):
            return None
        stripped = val.strip()
        return stripped or None

    return LlmAnalysisResult(
        product_name=_str_or_none("product_name"),
        ad_type=_str_or_none("ad_type"),
        summary=_str_or_none("summary"),
        tone=_str_or_none("tone"),
        raw_response=raw,
    )
