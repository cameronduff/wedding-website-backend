# -------- Base image --------
FROM python:3.11-slim AS base

# Install OS deps + curl + tini
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv (https://docs.astral.sh/uv/)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Ensure uv is on PATH (new installer puts it in /root/.local/bin)
ENV PATH="/root/.local/bin:${PATH}"

# Working directory
WORKDIR /app

# Prevent Python from writing pyc files / buffering output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# -------- Dependency layer (cached) --------
# Copy dependency descriptors
COPY pyproject.toml uv.lock* ./

# Install project dependencies (without dev deps)
RUN uv sync --frozen --no-dev

# Activate uv’s venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# -------- Copy application code --------
COPY . .

# Security best practice: drop root
RUN useradd -u 10001 -m appuser && chown -R appuser:appuser /app
USER appuser

# -------- Environment --------
ENV HOST=0.0.0.0 \
    PORT=8080

# Cloud Run will inject the PORT env var automatically
# Mount your service account secret at /secrets/rsvp/service_account_rsvp.json
# and set GOOGLE_APPLICATION_CREDENTIALS accordingly in the Cloud Run UI

# Use tini for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# -------- Start the app --------
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
