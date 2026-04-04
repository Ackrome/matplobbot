# Use your pre-built base image
FROM ghcr.io/ackrome/matplobbot-base-python:latest

WORKDIR /

COPY shared_lib/ /shared_lib/
COPY setup.py /
# Install local shared package first to avoid dependency on PyPI publish timing.
RUN pip install --no-cache-dir /

# Scheduler-specific requirements
COPY scheduler_app/requirements.txt .
RUN grep -Ev '^[[:space:]]*matplobbot-shared==' requirements.txt > /tmp/requirements.scheduler.txt && \
    pip install --no-cache-dir -r /tmp/requirements.scheduler.txt

COPY scheduler_app/ /scheduler_app/

CMD ["python3", "-m", "scheduler_app.main"]
