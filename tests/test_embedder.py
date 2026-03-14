"""Tests for src/embedder.py.

All tests mock resemblyzer (and its native webrtcvad dependency) to avoid
loading model weights or triggering the pkg_resources import at test time.
The injectable ``encoder`` / ``preprocess_fn`` parameters on :func:`embed`
mean most tests never touch resemblyzer at all.
"""

from __future__ import annotations

import importlib.metadata as _im
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src import embedder

# -- helpers --

SAMPLE_WAV = Path(__file__).parent / "fixtures" / "sample.wav"
_EMBED_DIM = 256


def _make_encoder(embedding: np.ndarray | None = None) -> MagicMock:
    enc = MagicMock()
    enc.embed_utterance.return_value = (
        np.zeros(_EMBED_DIM, dtype=np.float32) if embedding is None else embedding
    )
    return enc


def _make_preprocess(wav: np.ndarray | None = None) -> MagicMock:
    return MagicMock(
        return_value=np.zeros(16_000, dtype=np.float32) if wav is None else wav
    )


# -- embedding_to_blob / blob_to_embedding --


def test_embedding_to_blob_returns_bytes() -> None:
    arr = np.zeros(4, dtype=np.float32)
    assert isinstance(embedder.embedding_to_blob(arr), bytes)


def test_blob_to_embedding_returns_float32_ndarray() -> None:
    arr = np.zeros(4, dtype=np.float32)
    result = embedder.blob_to_embedding(embedder.embedding_to_blob(arr))
    assert result.dtype == np.float32
    assert isinstance(result, np.ndarray)


def test_blob_roundtrip_preserves_values() -> None:
    arr = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
    roundtripped = embedder.blob_to_embedding(embedder.embedding_to_blob(arr))
    np.testing.assert_array_equal(roundtripped, arr)


# -- EmbeddingResult --


def test_embedding_result_default_model_name() -> None:
    result = embedder.EmbeddingResult(embedding=np.zeros(_EMBED_DIM, dtype=np.float32))
    assert result.model_name == "resemblyzer"


def test_embedding_result_custom_model_name() -> None:
    result = embedder.EmbeddingResult(
        embedding=np.zeros(_EMBED_DIM, dtype=np.float32),
        model_name="custom-model",
    )
    assert result.model_name == "custom-model"


def test_embedding_result_repr() -> None:
    result = embedder.EmbeddingResult(embedding=np.zeros(_EMBED_DIM, dtype=np.float32))
    r = repr(result)
    assert "EmbeddingResult" in r
    assert "resemblyzer" in r


# -- embed function --


def test_embed_returns_embedding_result() -> None:
    result = embedder.embed(
        SAMPLE_WAV, encoder=_make_encoder(), preprocess_fn=_make_preprocess()
    )
    assert isinstance(result, embedder.EmbeddingResult)


def test_embed_returns_float32_dtype() -> None:
    result = embedder.embed(
        SAMPLE_WAV, encoder=_make_encoder(), preprocess_fn=_make_preprocess()
    )
    assert result.embedding.dtype == np.float32


def test_embed_returns_correct_shape() -> None:
    embedding = np.zeros(_EMBED_DIM, dtype=np.float32)
    result = embedder.embed(
        SAMPLE_WAV,
        encoder=_make_encoder(embedding),
        preprocess_fn=_make_preprocess(),
    )
    assert result.embedding.shape == (_EMBED_DIM,)


def test_embed_calls_preprocess_fn_with_path() -> None:
    preprocess_fn = _make_preprocess()
    _ = embedder.embed(SAMPLE_WAV, encoder=_make_encoder(), preprocess_fn=preprocess_fn)
    preprocess_fn.assert_called_once_with(SAMPLE_WAV)


def test_embed_calls_encoder_with_wav() -> None:
    wav = np.ones(16_000, dtype=np.float32)
    encoder = _make_encoder()
    preprocess_fn = _make_preprocess(wav)
    _ = embedder.embed(SAMPLE_WAV, encoder=encoder, preprocess_fn=preprocess_fn)
    encoder.embed_utterance.assert_called_once_with(wav)


def test_embed_loads_encoder_when_none() -> None:
    mock_encoder = _make_encoder()
    mock_preprocess = _make_preprocess()
    with patch("src.embedder._load_encoder", return_value=mock_encoder) as mock_load:
        result = embedder.embed(SAMPLE_WAV, preprocess_fn=mock_preprocess)
        mock_load.assert_called_once()
    assert result.embedding.shape == (_EMBED_DIM,)


def test_embed_loads_preprocess_fn_when_none() -> None:
    mock_encoder = _make_encoder()
    mock_preprocess = _make_preprocess()
    with patch(
        "src.embedder._load_preprocess_fn", return_value=mock_preprocess
    ) as mock_load:
        result = embedder.embed(SAMPLE_WAV, encoder=mock_encoder)
        mock_load.assert_called_once()
    assert result.embedding.shape == (_EMBED_DIM,)


# -- _load_encoder / _load_preprocess_fn --


def test_load_encoder_calls_voice_encoder() -> None:
    mock_mod = MagicMock()
    mock_instance = MagicMock()
    mock_instance.embed_utterance.return_value = np.zeros(_EMBED_DIM)
    mock_mod.VoiceEncoder.return_value = mock_instance
    with patch.dict(sys.modules, {"resemblyzer": mock_mod}):
        # embed() with encoder=None → triggers _load_encoder internally
        result = embedder.embed(SAMPLE_WAV, preprocess_fn=_make_preprocess())
    mock_mod.VoiceEncoder.assert_called_once_with()
    assert result.embedding.shape == (_EMBED_DIM,)


def test_load_preprocess_fn_returns_preprocess_wav() -> None:
    mock_mod = MagicMock()
    mock_wav = np.zeros(16_000, dtype=np.float32)
    mock_mod.preprocess_wav.return_value = mock_wav
    with patch.dict(sys.modules, {"resemblyzer": mock_mod}):
        # embed() with preprocess_fn=None → triggers _load_preprocess_fn internally
        _ = embedder.embed(SAMPLE_WAV, encoder=_make_encoder())
    mock_mod.preprocess_wav.assert_called_once_with(SAMPLE_WAV)


# -- embed default model name --


def test_embed_default_model_name() -> None:
    result = embedder.embed(
        SAMPLE_WAV, encoder=_make_encoder(), preprocess_fn=_make_preprocess()
    )
    assert result.model_name == "resemblyzer"


def test_embed_coerces_embedding_to_float32() -> None:
    float64_encoder = MagicMock()
    float64_encoder.embed_utterance.return_value = np.ones(_EMBED_DIM, dtype=np.float64)
    result = embedder.embed(
        SAMPLE_WAV, encoder=float64_encoder, preprocess_fn=_make_preprocess()
    )
    assert result.embedding.dtype == np.float32


# -- shape validation --


def test_embed_raises_on_wrong_dim_length() -> None:
    bad_encoder = MagicMock()
    bad_encoder.embed_utterance.return_value = np.zeros(128, dtype=np.float32)
    with pytest.raises(ValueError, match="256"):
        _ = embedder.embed(
            SAMPLE_WAV, encoder=bad_encoder, preprocess_fn=_make_preprocess()
        )


def test_embed_raises_on_2d_embedding() -> None:
    bad_encoder = MagicMock()
    bad_encoder.embed_utterance.return_value = np.zeros(
        (_EMBED_DIM, 1), dtype=np.float32
    )
    with pytest.raises(ValueError, match=r"shape"):
        _ = embedder.embed(
            SAMPLE_WAV, encoder=bad_encoder, preprocess_fn=_make_preprocess()
        )


# -- _ensure_pkg_resources / _PkgResourcesShim --


def test_ensure_pkg_resources_noop_when_already_present() -> None:
    """pkg_resources が sys.modules にある場合は何もしない。"""
    sentinel = embedder._PkgResourcesShim("pkg_resources")  # noqa: SLF001
    sys.modules["pkg_resources"] = sentinel
    try:
        embedder._ensure_pkg_resources()  # noqa: SLF001
        assert sys.modules["pkg_resources"] is sentinel
    finally:
        sys.modules.pop("pkg_resources", None)


def test_ensure_pkg_resources_installs_shim_when_missing() -> None:
    """pkg_resources が import できないときシムを sys.modules に挿入する。"""
    saved = sys.modules.pop("pkg_resources", None)
    try:
        with patch(
            "src.embedder.importlib.import_module",
            side_effect=ModuleNotFoundError("pkg_resources"),
        ):
            embedder._ensure_pkg_resources()  # noqa: SLF001
        shim = sys.modules.get("pkg_resources")
        assert isinstance(shim, embedder._PkgResourcesShim)  # noqa: SLF001
        assert shim.get_distribution is _im.distribution
    finally:
        sys.modules.pop("pkg_resources", None)
        if saved is not None:
            sys.modules["pkg_resources"] = saved
