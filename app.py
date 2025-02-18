import os
import subprocess
import tempfile
from flask import Flask, render_template, request, redirect, url_for, session, flash
from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error
from datetime import datetime, timedelta

# Загрузка переменных окружения из файла .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersecretkey")

# Чтение конфигурации Minio из .env
MINIO_HOST = os.getenv("MINIO_HOST")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Задел для LDAP (реальную логику можно доработать)
LDAP_SERVER = os.getenv("LDAP_SERVER")
LDAP_BASE_DN = os.getenv("LDAP_BASE_DN")

# Инициализация клиента Minio
minio_client = Minio(
    MINIO_HOST,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

def ldap_authenticate(username, password):
    """
    Функция аутентификации через LDAP.
    В этом примере тестовая логика: любой пользователь, у которого пароль равен "password" успешно аутентифицируется.
    """
    if password == "password":
        return True
    return False

@app.route("/", methods=["GET", "POST"])
def login():
    """
    Страница аутентификации.
    При POST-запросе происходит проверка введённых данных.
    """
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if ldap_authenticate(username, password):
            session["username"] = username
            return redirect(url_for("files"))
        else:
            flash("Ошибка аутентификации. Проверьте логин или пароль.")
            return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/files", methods=["GET", "POST"])
def files():
    """
    Страница работы с файлами.
    При загрузке видео:
      - Если bucket с именем пользователя (до символа "@") не существует, он создаётся;
      - Если формат видео не mp4, оно конвертируется с помощью ffmpeg;
      - Видео загружается в соответствующий bucket Minio.
    """
    if "username" not in session:
        return redirect(url_for("login"))
    
    username = session["username"]
    bucket_name = username.split("@")[0].lower()

    # Проверка существования bucket, создание при отсутствии
    if not minio_client.bucket_exists(bucket_name):
        try:
            minio_client.make_bucket(bucket_name)
        except S3Error as e:
            flash(f"Ошибка создания bucket: {e}")
            return redirect(url_for("files"))
    
    if request.method == "POST":
        if "file" not in request.files:
            flash("Файл не найден")
            return redirect(request.url)
        
        file = request.files["file"]
        if file.filename == "":
            flash("Имя файла не определено")
            return redirect(request.url)

        # Сохраняем загруженный файл во временную директорию
        temp_dir = tempfile.gettempdir()
        input_file_path = os.path.join(temp_dir, file.filename)
        file.save(input_file_path)

        # Определяем расширение файла
        _, ext = os.path.splitext(file.filename)
        ext = ext.lower()
        output_file_path = input_file_path

        # Если формат не mp4, выполняется конвертация с помощью ffmpeg
        if ext != ".mp4":
            output_file_path = input_file_path + ".mp4"
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", input_file_path,
                "-c:v", "libx264",
                "-c:a", "aac",
                output_file_path
            ]
            result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                flash("Ошибка конвертации видео")
                os.remove(input_file_path)
                return redirect(request.url)
        
        # Загрузка (физический файл) в Minio
        object_name = os.path.basename(output_file_path)
        try:
            minio_client.fput_object(bucket_name, object_name, output_file_path)
            flash("Файл загружен успешно")
        except S3Error as e:
            flash(f"Ошибка загрузки файла: {e}")
        
        # Удаление временных файлов
        if os.path.exists(input_file_path):
            os.remove(input_file_path)
        if ext != ".mp4" and os.path.exists(output_file_path):
            os.remove(output_file_path)
        
        return redirect(url_for("files"))

    # Получаем список объектов из bucket
    files_list = []
    try:
        for obj in minio_client.list_objects(bucket_name):
            files_list.append(obj)
    except Exception as e:
        flash(f"Ошибка при получении списка файлов: {e}")
    
    return render_template("files.html", files=files_list)

@app.route("/download/<bucket>/<path:object_name>")
def download_file(bucket, object_name):
    """
    Генерация предварительно подписанного URL для получения объекта из Minio.
    """
    try:
        # Увеличиваем время жизни URL до 24 часов для видео
        url = minio_client.presigned_get_object(
            bucket, 
            object_name,
            expires=timedelta(hours=24)
        )
        return redirect(url)
    except Exception as e:
        return f"Ошибка при получении файла: {e}", 500

@app.route("/logout")
def logout():
    """
    Завершение сессии пользователя.
    """
    session.pop("username", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    print("WARNING: This is a development server. Do not use it in a production deployment.")
    print("Use a production WSGI server (like Gunicorn) instead.")
    app.run(debug=True, host='0.0.0.0') 