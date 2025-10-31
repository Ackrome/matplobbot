# scheduler_app/Dockerfile
FROM python:3.11-slim
WORKDIR /app

# Copy requirements.txt specific to this app from the build context root
COPY scheduler_app/requirements.txt .

# Install dependencies, including matplobbot-shared from PyPI
RUN pip install --no-cache-dir -r requirements.txt

# Copy the contents of the scheduler_app directory into /app
COPY scheduler_app/ .

CMD ["python3", "-m", "main"]