FROM python:3.12-slim

# Install system dependencies including git, curl, and docker CLI
# (Docker CLI is needed so veritas can manage sandbox containers via the mounted docker socket)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    docker.io \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv from official binary image
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    WORKDIR=/app

WORKDIR /app

# Copy dependency specifications first to leverage Docker layer caching
COPY pyproject.toml uv.lock README.md ./

# Install python dependencies using uv
RUN uv sync --frozen --extra dev

# Copy the rest of the application codebase
COPY src/ ./src/
COPY configs/ ./configs/
COPY docs/ ./docs/
COPY scripts/ ./scripts/
COPY tests/ ./tests/
COPY Dockerfile.sandbox ./

# Sync project package
RUN uv sync --frozen --extra dev

# Set PATH to use the virtual environment binaries by default
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["veritas"]
CMD ["--help"]
