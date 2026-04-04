FROM ghcr.io/ackrome/matplobbot-base-python:latest

WORKDIR /

COPY shared_lib/ /shared_lib/
COPY setup.py /
# Install local shared package first to avoid dependency on PyPI publish timing.
RUN pip install --no-cache-dir /

# FastAPI-specific requirements
COPY fastapi_stats_app/requirements.txt .
RUN grep -Ev '^[[:space:]]*matplobbot-shared==' requirements.txt > /tmp/requirements.api.txt && \
    pip install --no-cache-dir -r /tmp/requirements.api.txt

COPY fastapi_stats_app/ /fastapi_stats_app/

CMD ["uvicorn", "fastapi_stats_app.main:app", "--host", "0.0.0.0", "--port", "9583"]
