# -------- Base image --------
FROM python:3.11-slim AS base

# Install OS deps + curl (for uv install)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# Set working directory
WORKDIR /app

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# -------- Dependency layer --------
# Copy only dependency files (for Docker layer caching)
COPY pyproject.toml uv.lock* ./

# Install dependencies in a local venv (no dev deps in prod)
RUN uv sync --frozen --no-dev

# Set the PATH to use the uv-created virtualenv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# -------- Copy app code --------
COPY . .

# Optional security: run as non-root
RUN useradd -u 10001 -m appuser && chown -R appuser:appuser /app
USER appuser

# -------- Environment variables --------
ENV HOST=0.0.0.0 \
    PORT=8080

# Use tini for proper signal handling (graceful shutdown)
ENTRYPOINT ["/usr/bin/tini", "--"]

# -------- Run the FastAPI app --------
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
