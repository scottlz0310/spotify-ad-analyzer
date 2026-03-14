from __future__ import annotations

import importlib
import importlib.metadata
import sys
import types
from typing import TYPE_CHECKING, Protocol, cast, final, override

import numpy as np

if TYPE_CHECKING:
    from pathlib import Path


@final
class _PkgResourcesShim(types.ModuleType):
    """Minimal pkg_resources shim backed by importlib.metadata."""

    get_distribution = staticmethod(importlib.metadata.distribution)


def _ensure_pkg_resources() -> None:
    """Shim pkg_resources for webrtcvad (resemblyzer dep).

    webrtcvad uses ``pkg_resources.get_distribution`` which was removed from
    *setuptools* in v81+.  When not present we install a minimal stub backed by
    :mod:`importlib.metadata` so that ``import webrtcvad`` succeeds.
    """
    if "pkg_resources" not in sys.modules:
        try:
            _ = importlib.import_module("pkg_resources")
        except ModuleNotFoundError:
            sys.modules["pkg_resources"] = _PkgResourcesShim("pkg_resources")


_EMBEDDING_DIM: int = 256


class _VoiceEncoderProtocol(Protocol):
    """Minimal structural type for resemblyzer's VoiceEncoder."""

    def embed_utterance(self, wav: np.ndarray) -> np.ndarray: ...


class _PreprocessFnProtocol(Protocol):
    """Minimal structural type for resemblyzer's preprocess_wav callable."""

    def __call__(self, source: Path | str) -> np.ndarray: ...


class EmbeddingResult:
    """Voice embedding result for one audio file."""

    __slots__: tuple[str, ...] = ("embedding", "model_name")
    embedding: np.ndarray
    model_name: str

    def __init__(
        self,
        *,
        embedding: np.ndarray,
        model_name: str = "resemblyzer",
    ) -> None:
        self.embedding = embedding
        self.model_name = model_name

    @override
    def __repr__(self) -> str:
        return (
            f"EmbeddingResult(shape={self.embedding.shape!r},"
            f" model_name={self.model_name!r})"
        )


def embedding_to_blob(embedding: np.ndarray) -> bytes:
    """Serialize a float32 embedding to raw bytes for SQLite BLOB storage."""
    return embedding.astype(np.float32).tobytes()


def blob_to_embedding(blob: bytes) -> np.ndarray:
    """Deserialize raw bytes back to a float32 numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


def _load_encoder() -> _VoiceEncoderProtocol:
    """Instantiate a resemblyzer VoiceEncoder (lazy import to defer native deps)."""
    _ensure_pkg_resources()
    mod = importlib.import_module("resemblyzer")
    return cast("_VoiceEncoderProtocol", mod.VoiceEncoder())


def _load_preprocess_fn() -> _PreprocessFnProtocol:
    """Return resemblyzer's preprocess_wav callable (lazy import)."""
    _ensure_pkg_resources()
    mod = importlib.import_module("resemblyzer")
    return cast("_PreprocessFnProtocol", mod.preprocess_wav)


def embed(
    audio_path: Path,
    *,
    encoder: _VoiceEncoderProtocol | None = None,
    preprocess_fn: _PreprocessFnProtocol | None = None,
) -> EmbeddingResult:
    """Encode *audio_path* into a 256-dim float32 voice embedding.

    Parameters
    ----------
    audio_path:
        Path to the WAV file to embed.
    encoder:
        Pre-loaded VoiceEncoder.  When *None* (default), loads a new one via
        :func:`_load_encoder`.
    preprocess_fn:
        Pre-loaded preprocess callable.  When *None* (default), loads via
        :func:`_load_preprocess_fn`.
    """
    if encoder is None:
        encoder = _load_encoder()
    if preprocess_fn is None:
        preprocess_fn = _load_preprocess_fn()

    wav = preprocess_fn(audio_path)
    embedding = np.asarray(encoder.embed_utterance(wav), dtype=np.float32)
    if embedding.ndim != 1 or embedding.shape[0] != _EMBEDDING_DIM:
        msg = (
            f"Expected 1-D embedding of length {_EMBEDDING_DIM},"
            f" got shape {embedding.shape!r}"
        )
        raise ValueError(msg)
    return EmbeddingResult(embedding=embedding)
