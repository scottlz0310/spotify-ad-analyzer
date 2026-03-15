from __future__ import annotations

import os
from pathlib import Path

SHARED_DIR: Path = Path(os.environ.get("SHARED_DIR", "/app/shared"))
DATA_DIR: Path = Path(os.environ.get("DATA_DIR", "/app/data"))
WHISPER_MODEL: str = os.environ.get("WHISPER_MODEL", "small")
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "host.docker.internal:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "qwen3.5")
HF_TOKEN: str = os.environ.get("HF_TOKEN", "")
DIARIZE_MODEL: str = os.environ.get("DIARIZE_MODEL", "pyannote/speaker-diarization-3.1")
WATCHDOG_FORCE_POLLING: bool = os.environ.get("WATCHDOG_FORCE_POLLING", "0") == "1"
