# scheduler_app/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if any (none needed for this simple scheduler)
# RUN apt-get update && apt-get install -y ...

# Copy requirements first for layer caching
COPY shared_lib/ /app/shared_lib/
COPY setup.py /app/
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot's shared code (services, i18n, etc.)
# This is now handled by installing the shared_lib
COPY bot/ /app/bot/

# Copy the scheduler application code
COPY scheduler_app/ /app/scheduler_app/

CMD ["python3", "-m", "scheduler_app.main"]