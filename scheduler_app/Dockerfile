# scheduler_app/Dockerfile

FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .

# 1. Create a virtual environment
RUN python3 -m venv /opt/venv

# 2. Activate the venv by adding it to the PATH
ENV PATH="/opt/venv/bin:$PATH"

# 3. Install dependencies into the venv
RUN pip install --no-cache-dir -r requirements.txt

# Copy the scheduler application code
COPY scheduler_app/ /app/scheduler_app/

CMD ["python3", "-m", "scheduler_app.main"]