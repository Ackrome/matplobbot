# scheduler_app/Dockerfile
FROM python:3.11-slim
WORKDIR /app

# The COPY and editable install steps are no longer needed
# COPY shared_lib/ /app/shared_lib/
# COPY setup.py /app/
# RUN pip install --no-cache-dir -e .

COPY requirements.txt .

# The scheduler will now install matplobbot-shared directly from PyPI
RUN pip install --no-cache-dir -r requirements.txt

# Copy the scheduler application code
COPY scheduler_app/ /app/scheduler_app/

CMD ["python3", "-m", "scheduler_app.main"]