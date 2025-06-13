# Использовать официальный образ Python в качестве базового
FROM python:3.11-slim

# Установить переменные окружения для Python, чтобы .pyc файлы не создавались и вывод был небуферизованным
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Установить рабочую директорию в контейнере
WORKDIR /app

# Скопировать файл зависимостей
COPY requirements.txt .

# Установить зависимости
# --no-cache-dir используется для уменьшения размера образа
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Скопировать код приложения в рабочую директорию
# Копируем сначала директорию app, затем отдельные файлы для лучшего использования кэша Docker
COPY app ./app
COPY main.py .


# Команда для запуска приложения
# Предполагается, что main.py запускает и бота, и Flask-сервер (если соответствующий код раскомментирован).
CMD ["python", "main.py"]