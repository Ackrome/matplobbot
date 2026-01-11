# build with  requirements changes:

```
# 1. Build Base Python
docker build -t matplobbot-base-python:latest -f Dockerfile.base-python .

# 2. Build Base Worker (This will take a long time ONCE, but never again unless you update system deps)
docker build -t matplobbot-base-worker:latest -f Dockerfile.base-worker .

# 3. Now build your services (This will be super fast)
docker compose up --build -d
```

# build with no requirements changes:

```
docker compose up --build -d
```