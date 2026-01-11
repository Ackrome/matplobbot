FROM ghcr.io/ackrome/matplobbot-base-python:latest

WORKDIR /

COPY shared_lib/ /shared_lib/
COPY setup.py /
# scheduler specific reqs might be small, or you can merge them into the base requirements.txt
COPY fastapi_stats_app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir /

COPY fastapi_stats_app/ /fastapi_stats_app/

CMD ["uvicorn", "fastapi_stats_app.main:app", "--host", "0.0.0.0", "--port", "9583"]
