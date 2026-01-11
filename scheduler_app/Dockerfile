# Use your pre-built base image
FROM ghcr.io/ackrome/matplobbot-base-python:latest

WORKDIR /

COPY shared_lib/ /shared_lib/
COPY setup.py /
# scheduler specific reqs might be small, or you can merge them into the base requirements.txt
COPY scheduler_app/requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir /

COPY scheduler_app/ /scheduler_app/

CMD ["python3", "-m", "scheduler_app.main"]