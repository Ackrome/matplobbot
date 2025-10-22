FROM python:3.13-slim

WORKDIR /app/fastapi_stats_app

# Копируем сначала файл зависимостей и устанавливаем их
# Это позволяет использовать кэширование слоев Docker, если код приложения меняется, а зависимости нет
COPY requirements.txt .
RUN apt-get update && apt-get install -y curl && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

# Копируем остальной код приложения
# Копируем код приложения в поддиректорию, которая будет нашим Python пакетом
COPY . .

# Устанавливаем WORKDIR в родительский каталог нашего пакета
WORKDIR /app

# Порт, на котором будет работать FastAPI приложение внутри контейнера
EXPOSE 9583
CMD ["uvicorn", "fastapi_stats_app.main:app", "--host", "0.0.0.0", "--port", "9583"]