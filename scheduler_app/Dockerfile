# scheduler_app/Dockerfile
FROM python:3.11-slim
WORKDIR /

# --- START: CORRECTED INSTALLATION BLOCK ---
# Copy shared library source code FIRST, as it's a dependency
COPY shared_lib/ /shared_lib/
COPY setup.py /

# Copy requirements.txt specific to this app from the build context root
COPY scheduler_app/requirements.txt .

# Install dependencies from requirements.txt FIRST, then install the local shared_lib package.
# This ensures that the local, up-to-date version of shared_lib overwrites any version from PyPI.
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir /
# --- END: CORRECTED INSTALLATION BLOCK ---

# Copy the contents of the scheduler_app directory into /app
COPY scheduler_app/ /scheduler_app/

CMD ["python3", "-m", "scheduler_app.main"]