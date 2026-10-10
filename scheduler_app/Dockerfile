# Use your pre-built base image
ARG PYTHON_BASE_IMAGE=ghcr.io/ackrome/matplobbot-base-python:latest
FROM ${PYTHON_BASE_IMAGE}
USER root

WORKDIR /

# CPU-only OCR is confined to the scheduler image. API/bot images do not need it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY shared_lib/ /shared_lib/
COPY setup.py /
# Install local shared package first to avoid dependency on PyPI publish timing.
RUN pip install --no-cache-dir /

# Scheduler-specific requirements
COPY scheduler_app/requirements.txt .
RUN grep -Ev '^[[:space:]]*matplobbot-shared==' requirements.txt > /tmp/requirements.scheduler.txt && \
    pip install --no-cache-dir -r /tmp/requirements.scheduler.txt

# Fail the image build if packaged numeric weights or the CPU runtime are broken.
RUN python -c "from shared_lib.services.curriculum_numeric import NumericRecognizer; NumericRecognizer()"

COPY scheduler_app/ /scheduler_app/

CMD ["python3", "-m", "scheduler_app.main"]
