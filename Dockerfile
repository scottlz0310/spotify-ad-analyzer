FROM python:3.12-slim

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for Docker layer caching
COPY pyproject.toml uv.lock ./

# Install all dependencies (prod + dev) without installing the project itself
RUN uv sync --frozen --all-groups --no-install-project

# Copy source code
COPY src/ ./src/

# Activate the virtual environment at runtime
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

CMD ["python", "-m", "src.main"]
