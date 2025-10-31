# scheduler_app/Dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
COPY setup.py .
COPY shared_lib/ ./shared_lib/

RUN pip install --no-cache-dir -e ./shared_lib
RUN pip install --no-cache-dir -r requirements.txt

# Copy the contents of the scheduler_app directory into /app
COPY scheduler_app/ .

CMD ["python3", "-m", "main"]