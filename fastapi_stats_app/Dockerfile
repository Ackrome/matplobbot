# fastapi_stats_app/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# The build context is the repository root.
# We copy only the files necessary for this service.
COPY requirements.txt .
COPY setup.py .
COPY shared_lib/ ./shared_lib/

# Install dependencies, including the shared_lib
RUN apt-get update && apt-get install -y curl && \
    pip install --no-cache-dir -e ./shared_lib && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

# --- CORRECTED COPY STEP ---
# Copy the application code itself.
# This copies the *contents* of fastapi_stats_app into the current WORKDIR (/app)
COPY fastapi_stats_app/ .

# Since the WORKDIR is /app, the entrypoint is simpler.
# We don't need the --reload flag in production.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9583"]