from __future__ import annotations

import os
from pathlib import Path

SHARED_DIR: Path = Path(os.environ.get("SHARED_DIR", "/app/shared"))
DATA_DIR: Path = Path(os.environ.get("DATA_DIR", "/app/data"))
WHISPER_MODEL: str = os.environ.get("WHISPER_MODEL", "small")
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "host.docker.internal:11434")
