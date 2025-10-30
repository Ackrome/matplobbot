# scheduler_app/Dockerfile
FROM python:3.11-slim
WORKDIR /app

# Copy requirements first for layer caching
COPY shared_lib/ /app/shared_lib/
COPY setup.py /app/
COPY requirements.txt .

# Install Python dependencies
# This now installs your shared_lib in editable mode
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir -r requirements.txt

# This line is now removed, as its contents are in the shared_lib
# COPY bot/ /app/bot/ 

# Copy the scheduler application code
COPY scheduler_app/ /app/scheduler_app/

CMD ["python3", "-m", "scheduler_app.main"]