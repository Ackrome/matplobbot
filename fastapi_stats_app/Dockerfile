FROM python:3.11-slim

WORKDIR /app

# Копируем сначала файл зависимостей и устанавливаем их
# Это позволяет использовать кэширование слоев Docker, если код приложения меняется, а зависимости нет
COPY shared_lib/ /app/shared_lib/
COPY setup.py /app/
COPY requirements.txt .

RUN apt-get update && apt-get install -y curl && \
    pip install --no-cache-dir -e . && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

# Копируем остальной код приложения
# Копируем код приложения в поддиректорию, которая будет нашим Python пакетом
COPY fastapi_stats_app/ /app/fastapi_stats_app/

# Устанавливаем WORKDIR в родительский каталог нашего пакета
WORKDIR /app

# Порт, на котором будет работать FastAPI приложение внутри контейнера
EXPOSE 9583
CMD ["uvicorn", "fastapi_stats_app.main:app", "--host", "0.0.0.0", "--port", "9583"]