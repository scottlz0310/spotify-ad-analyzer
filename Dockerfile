# syntax=docker/dockerfile:1
# ── builder stage ────────────────────────────────────────────────────────────
FROM python:3.14-slim AS builder

# Kept in lockstep with pyproject.toml's [tool.uv] required-version by Renovate.
ARG UV_VERSION=0.11.19
COPY --from=ghcr.io/astral-sh/uv:${UV_VERSION} /uv /usr/local/bin/uv

WORKDIR /app

# Build tools are required only to compile C-extension packages (e.g. webrtcvad).
# Installing them in the builder stage keeps the final runtime image clean.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-groups --no-install-project

# ── runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.14-slim

WORKDIR /app

# ffmpeg is required by torchcodec (used by pyannote.audio for audio decoding).
# libsndfile1 is required by soundfile, which is used to bypass torchcodec for diarization.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# Copy only the pre-built virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

CMD ["python", "-m", "src.main"]
