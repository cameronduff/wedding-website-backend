# -------- Base image --------
FROM python:3.11-slim

# Ensure system-level installs work (no venv)
ENV UV_SYSTEM_PYTHON=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# -------- Install uv --------
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# -------- Dependencies --------
COPY pyproject.toml uv.lock* ./

# Export and install dependencies globally (no .venv ownership issues)
RUN uv export --no-dev --no-hashes > requirements.txt && \
    uv pip install --system --no-cache-dir -r requirements.txt

# -------- Copy app code --------
COPY . .

# Optional: security — create a non-root user
RUN useradd -u 10001 appuser && chown -R appuser /app
USER appuser

# -------- Environment --------
ENV HOST=0.0.0.0 \
    PORT=8080

EXPOSE 8080

# -------- Run the app --------
# Use python -m to avoid binary permission issues
CMD exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
