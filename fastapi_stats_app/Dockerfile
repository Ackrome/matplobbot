FROM python:3.11-slim

WORKDIR /app

# Копируем сначала файл зависимостей и устанавливаем их
# Это позволяет использовать кэширование слоев Docker, если код приложения меняется, а зависимости нет
COPY ./fastapi_stats_app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код приложения
COPY ./fastapi_stats_app /app

# Порт, на котором будет работать FastAPI приложение внутри контейнера
EXPOSE 9583
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9583", "--reload"]