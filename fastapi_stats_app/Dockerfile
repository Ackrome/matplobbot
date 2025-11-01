# fastapi_stats_app/Dockerfile
FROM python:3.11-slim

WORKDIR /

# Copy requirements.txt specific to this app from the build context root
COPY fastapi_stats_app/requirements.txt .

# Install dependencies, including matplobbot-shared from PyPI
RUN apt-get update && apt-get install -y curl && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

# --- CORRECTED COPY STEP ---
# Copy the application code itself.
# This copies the *contents* of fastapi_stats_app into the current WORKDIR (/app)
COPY fastapi_stats_app/ /fastapi_stats_app/

# Since the WORKDIR is /app, the entrypoint is simpler.
# We don't need the --reload flag in production.
CMD ["uvicorn", "fastapi_stats_app.main:app", "--host", "0.0.0.0", "--port", "9583"]