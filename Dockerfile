# Используем базовый образ Python (например, 3.9-slim)
FROM python:3.9-slim

# Устанавливаем системные зависимости и ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы проекта (app.py, .env, папку templates и пр.)
COPY . .

# Открываем порт 5000 для приложения
EXPOSE 5000

# Устанавливаем переменные окружения для Flask
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Запускаем через gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]  