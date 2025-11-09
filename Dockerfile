# ---------- Base image ----------
FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ---------- System dependencies ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ---------- Install dependencies ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Copy application code ----------
COPY . .

# ---------- Environment variables ----------
# Cloud Run provides PORT automatically
ENV PORT=8080
ENV HOST=0.0.0.0

# ---------- Run the app with uvicorn ----------
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
