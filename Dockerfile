# ── builder stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /usr/local/bin/uv

WORKDIR /app

# Build tools are required only to compile C-extension packages (e.g. webrtcvad).
# Installing them in the builder stage keeps the final runtime image clean.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --all-groups --no-install-project

# ── runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy only the pre-built virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

CMD ["python", "-m", "src.main"]
