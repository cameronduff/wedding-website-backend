# -------- Base image --------
FROM python:3.11-slim AS base

# Minimal OS deps + curl for installing uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# Install uv (https://docs.astral.sh/uv/)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# App directory
WORKDIR /app

# Python runtime tweaks
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# -------- Dependency layer (cached) --------
# Copy only files needed to resolve dependencies
# If you have extras (e.g. uv.lock.toml), copy them too.
COPY pyproject.toml uv.lock* ./

# Create a local venv and install deps (no dev deps in prod)
# This keeps deps cached unless pyproject/lock changes.
RUN uv sync --frozen --no-dev

# Make uv-created venv the default Python
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# -------- App layer --------
# Now copy the rest of your app
COPY . .

# (Optional) security: drop root
RUN useradd -u 10001 -m appuser && chown -R appuser:appuser /app
USER appuser

# -------- Runtime env --------
# Cloud Run injects $PORT; we default to 8080 if missing
ENV HOST=0.0.0.0 \
    PORT=8080

# If you mount your Secret Manager file as a volume, set this env at deploy time:
# GOOGLE_APPLICATION_CREDENTIALS=/secrets/rsvp/service_account_rsvp.json

# Use tini for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# -------- Launch --------
# Use sh -c so we can expand ${PORT}
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
