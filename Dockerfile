# -------- Base image --------
FROM python:3.11-slim AS base

# Install OS deps + curl + tini
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv (https://docs.astral.sh/uv/)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Working directory
WORKDIR /app

# Prevent Python from writing pyc files / buffering output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# -------- Dependency layer --------
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Activate uv’s venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# -------- Copy application code --------
COPY . .

# ✅ FIX: ensure the app and venv are owned by the appuser
RUN useradd -u 10001 -m appuser && \
    chown -R appuser:appuser /app && \
    chmod +x /app/.venv/bin/uvicorn

USER appuser

# -------- Environment --------
ENV HOST=0.0.0.0 \
    PORT=8080

# Use tini for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# -------- Start the app --------
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
