FROM python:3.13-slim

ENV APP_PACKAGE_DIR_NAME=fastapi_stats_module
ENV APP_HOME=/app_root

WORKDIR ${APP_HOME}

# Копируем сначала файл зависимостей и устанавливаем их
# Это позволяет использовать кэширование слоев Docker, если код приложения меняется, а зависимости нет
COPY ./fastapi_stats_app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код приложения
# Копируем код приложения в поддиректорию, которая будет нашим Python пакетом
COPY ./fastapi_stats_app ${APP_HOME}/${APP_PACKAGE_DIR_NAME}

# Устанавливаем WORKDIR в родительский каталог нашего пакета
WORKDIR ${APP_HOME}

# Порт, на котором будет работать FastAPI приложение внутри контейнера
EXPOSE 9583
CMD ["uvicorn", "fastapi_stats_module.main:app", "--host", "0.0.0.0", "--port", "9583", "--reload"]