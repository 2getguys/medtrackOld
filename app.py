import os
import base64 # Для кодирования изображения
from flask import Flask, render_template, request, redirect, url_for, flash, abort, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
# Убедитесь, что ProfileForm импортируется
from forms import RegistrationForm, LoginForm, ProfileForm, BloodPressureForm
from dotenv import load_dotenv # Для загрузки .env файла
from openai import OpenAI # Импорт клиента OpenAI
import json # Для парсинга JSON ответа
import re # Для регулярных выражений
import decimal # Для более точной работы с числами
from PIL import Image, ImageOps # Добавляем ImageOps для grayscale
import io # Для работы с байтами изображения в памяти
import pytesseract # Добавляем pytesseract для OCR
import fitz # Для обработки PDF
from datetime import date # Для поля даты рождения
from functools import wraps # Для декоратора
from extensions import db, login_manager
# --->>> ЯВНЫЙ ИМПОРТ МОДЕЛЕЙ <<<---
import models # Просто импортируем модуль, чтобы он был загружен
# --->>> КОНЕЦ ИМПОРТА <<<---
from sqlalchemy import text

load_dotenv() # Загружаем переменные из .env (если он есть)

# --->>> Определения Промптов <<<---
PROMPT_INDICATORS = """
Уважно проаналізуй наданий медичний документ (текст або зображення). Знайди ВСІ показники аналізів.
Поверни відповідь ТІЛЬКИ у вигляді валідного JSON об'єкта наступної структури:
{
  "показники": [
    {"назва": "Повна Назва Показника (ПЕРЕКЛАДЕНА НА УКРАЇНСЬКУ)", "значення": "Вилучене Значення (тільки число або текст)", "одиниці": "Одиниці Виміру (якщо є, інакше null)", "референс": "Референсний Діапазон (якщо є, інакше null)"}
  ] // Важливо: у полі 'референс' вказуй ТІЛЬКИ числові значення, діапазони (напр., '0.5-1.5') або умови (напр., '< 100', '> 50'). НЕ ДОДАВАЙ слова типу 'Норма', 'Рекомендовано' тощо.
}
Дуже важливо: поле "назва" повинно містити назву показника, ТОЧНО перекладену на УКРАЇНСЬКУ мову. Не використовуй мову оригіналу.
НЕ ДОДАВАЙ жодних інших полів, ключів, пояснень, коментарів, ```json маркерів. ТІЛЬКИ цей JSON.
Якщо показники не знайдено, поверни: {"показники": []}.
"""

PROMPT_DESCRIPTIVE = """
Проаналізуй наданий медичний документ (текст або зображення). Витягни ключову інформацію.
Поверни відповідь ТІЛЬКИ у вигляді валідного JSON об'єкта наступної структури:
{
  "тип_документу": "Тип документа (напр., МРТ головного мозку, УЗД черевної порожнини)",
  "дата_дослідження": "Дата проведення дослідження (РРРР-ММ-ДД, якщо знайдено, інакше null)",
  "опис": "Основний текст опису дослідження.",
  "висновок": "Текст заключення або висновку лікаря (якщо є).",
  "рекомендації": "Рекомендації (якщо є)."
}
НЕ ДОДАВАЙ жодних інших полів, пояснень або ```json маркерів.
"""
# --->>> Конец Определения Промптов <<<---


app = Flask(__name__)

# --- Конфигурация ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default_fallback_secret_key_change_me') # Используем переменную окружения или запасной ключ
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'db.sqlite') # Явный путь в instance
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Отключаем ненужное отслеживание
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0 # Отключаем кэш статики

# Папка для загрузок
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'} # Расширения для обработки через Vision API
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Инициализация расширений
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' # Страница, на которую перенаправлять, если доступ запрещен
login_manager.login_message = "Будь ласка, увійдіть, щоб отримати доступ до цієї сторінки." # Сообщение для пользователя

# --- Инициализация OpenAI клиента ---
try:
    openai_client = OpenAI()
    print("OpenAI клиент успешно инициализирован.")
except Exception as e:
    print(f"ОШИБКА: Не удалось инициализировать OpenAI клиент: {e}")
    openai_client = None

# --- Модель пользователя ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    analyses = db.relationship('Analysis', backref='author', lazy=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    sex = db.Column(db.String(10), nullable=True)
    height_cm = db.Column(db.Integer, nullable=True)
    weight_kg = db.Column(db.Float, nullable=True)
    # Звичайний тиск користувача (індивідуальна норма)
    usual_systolic = db.Column(db.Integer, nullable=True)
    usual_diastolic = db.Column(db.Integer, nullable=True)
    # Статус куріння (yes | no | stopped)
    is_smoker = db.Column(db.String(10))
    chronic_conditions = db.Column(db.Text, nullable=True)
    current_medications = db.Column(db.Text, nullable=True)
    profile_complete = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        if not self.password_hash: return False
        return check_password_hash(self.password_hash, password)

# --- Модель для хранения информации об анализе ---
class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(200))
    upload_timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    document_type = db.Column(db.String(100))
    analysis_date = db.Column(db.String(50))
    raw_result_text = db.Column(db.Text)
    indicators = db.relationship('Indicator', backref='analysis', lazy=True, cascade="all, delete-orphan")

# --- Модель для хранения отдельных показателей ---
class Indicator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analysis.id'), nullable=False)
    name = db.Column(db.String(100))
    value = db.Column(db.String(50))
    units = db.Column(db.String(50))
    reference_range = db.Column(db.String(100))

# --- Модель для хранения измерений давления ---
class BloodPressureReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    systolic = db.Column(db.Integer, nullable=False)
    diastolic = db.Column(db.Integer, nullable=False)

# --- Функция загрузки пользователя ---
@login_manager.user_loader
def load_user(user_id):
    try:
        with app.app_context():
            user = db.session.get(User, int(user_id))
        return user
    except Exception as e:
        print(f"Ошибка при загрузке пользователя {user_id}: {e}")
        return None

# --->>> ИЗМЕНЕННЫЙ ДЕКОРАТОР profile_required <<<---
def profile_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()

        # --->>> Явно перезагружаем пользователя из БД перед проверкой <<<---
        try:
            # Используем контекст приложения для доступа к сессии db
            with app.app_context():
                 user = db.session.get(User, int(current_user.get_id()))
        except Exception as e:
             print(f"Ошибка получения пользователя в декораторе profile_required: {e}")
             user = None

        if not user or not user.profile_complete:
            flash('Будь ласка, заповніть інформацію профілю, щоб продовжити.', 'info')
            return redirect(url_for('profile_setup'))

        return f(*args, **kwargs)
    return decorated_function
# --->>> КОНЕЦ ДЕКОРАТОРА <<<---


# --- Маршруты (Routes) ---
@app.route('/')
def index():
    # Головна сторінка тепер - лендінг
    if current_user.is_authenticated:
        return redirect(url_for('dashboard')) # Залогінених перекидаємо в кабінет
    return render_template('landing.html', page_title='MEDTRACK AI - Ваша цифрова медична книга')

@app.route('/dashboard')
@login_required
@profile_required
def dashboard():
    # Код здесь выполнится только если профиль заполнен
    user_analyses = Analysis.query.filter_by(user_id=current_user.id).order_by(Analysis.upload_timestamp.desc()).all()

    # --- Получаем последние ключевые показатели ---
    latest_cholesterol = (
        db.session.query(Indicator)
        .join(Analysis, Indicator.analysis_id == Analysis.id)
        .filter(Analysis.user_id == current_user.id)
        .filter(Indicator.name.ilike('%холестерин%'))
        .order_by(Analysis.upload_timestamp.desc())
        .first()
    )

    # --- Получаем последнее измерение давления ---
    latest_bp = (
        BloodPressureReading.query
        .filter_by(user_id=current_user.id)
        .order_by(BloodPressureReading.timestamp.desc())
        .first()
    )

    latest_params = {
        'cholesterol': latest_cholesterol
    }

    # возраст
    age = None
    if current_user.date_of_birth:
        import datetime
        age = (datetime.date.today() - current_user.date_of_birth).days // 365

    # --->>> Явно получаем пользователя из БД <<<---
    profile_user = db.session.get(User, int(current_user.get_id()))
    # --->>> ДОБАВЛЯЕМ ЛОГИРОВАНИЕ <<<---
    if profile_user:
        print(f"--- DEBUG dashboard ---")
        print(f"User ID: {profile_user.id}")
        print(f"User Email: {profile_user.email}")
        print(f"User Name from DB: '{profile_user.name}' (Type: {type(profile_user.name)})") # <-- Добавили вывод имени и его типа
        print(f"-----------------------")
    else:
        print(f"--- DEBUG dashboard ---")
        print(f"User with ID {current_user.get_id()} not found in DB!")
        print(f"-----------------------")
    # --->>> Конец логирования <<<---

    # Передаем profile_user в шаблон
    return render_template('dashboard.html', title='Кабінет', analyses=user_analyses,
                           latest_params=latest_params, age=age,
                           profile_user=profile_user,
                           latest_bp=latest_bp)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
         # Редирект на дашборд, декоратор сам проверит профиль
         return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Ви успішно увійшли!', 'success')
            # Не нужно проверять профиль здесь, @profile_required сделает это при доступе к dashboard
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Неправильний email або пароль.', 'danger')
    return render_template('login.html', title='Вхід', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
         # Редирект на дашборд, декоратор сам проверит профиль
         return redirect(url_for('dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash('Цей email вже зареєстровано.', 'warning')
            return render_template('register.html', title='Реєстрація', form=form)
        try:
            user = User(email=form.email.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            login_user(user) # Логиним сразу
            flash('Реєстрація пройшла успішно! Будь ласка, заповніть профіль.', 'success')
            print("Перенаправлення на сторінку налаштування профілю (/profile/setup)...")
            return redirect(url_for('profile_setup')) # <-- Редирект на анкету ПРАВИЛЬНЫЙ
        except Exception as e:
            db.session.rollback()
            flash('Виникла помилка під час реєстрації.', 'danger')
            print(f"Ошибка регистрации: {e}")
    return render_template('register.html', title='Реєстрація', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Ви успішно вийшли з системи.', 'success')
    return redirect(url_for('index')) # Редирект на главную (которая покажет логин)

# --- Вспомогательные функции ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_date_from_text(text):
    if not text: return None
    patterns = [
        r'\b(\d{2})[-.\/](\d{2})[-.\/](\d{4})\b', # DD.MM.YYYY
        r'\b(\d{4})[-.\/](\d{2})[-.\/](\d{2})\b'  # YYYY-MM-DD
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                if len(match.group(1)) == 4: year, month, day = match.groups()
                else: day, month, year = match.groups()
                if 1 <= int(month) <= 12 and 1 <= int(day) <= 31: return f"{year}-{month}-{day}"
            except ValueError: continue
    return None

# --- Маршрут загрузки файла ---
@app.route('/upload', methods=['POST'])
@login_required
@profile_required # <-- Декоратор здесь
def upload_file():
    # Декоратор уже выполнил проверку
    selected_doc_type_key = request.form.get('document_type')
    if not selected_doc_type_key:
        flash('Будь ласка, оберіть тип документу.', 'warning')
        return redirect(url_for('upload_analysis_page'))

    if 'analysis_file' not in request.files:
        flash('Файл не вибрано.', 'warning')
        return redirect(url_for('dashboard'))
    file = request.files['analysis_file']
    if file.filename == '':
        flash('Файл не вибрано.', 'warning')
        return redirect(url_for('dashboard'))

    filename = secure_filename(file.filename)
    file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

    if file and allowed_file(filename):
        unique_filename = f"{current_user.id}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        extracted_text = None
        ocr_failed_for_image = False

        try: # Основной try
            file_bytes = file.read()
            with open(filepath, "wb") as f: f.write(file_bytes)
            print(f"Файл сохранен: {filepath}")

            # Извлечение текста
            if file_extension == 'pdf':
                try:
                    print(f"Извлечение текста из PDF: {unique_filename}...")
                    full_text = ""
                    pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
                    for page_num in range(len(pdf_document)):
                        page = pdf_document.load_page(page_num)
                        full_text += page.get_text("text")
                    pdf_document.close()
                    extracted_text = full_text
                    print("--- Текст из PDF ---")
                    print(extracted_text[:500] + "..." if extracted_text else "Текст не знайдено.")
                    print("--------------------")
                    if not extracted_text: flash('Не вдалося вилучити текст з PDF.', 'warning')
                except Exception as e_pdf:
                    print(f"Помилка обробки PDF: {e_pdf}")
                    flash(f'Помилка під час обробки PDF: {e_pdf}', 'danger')
                    extracted_text = None
            elif file_extension in IMAGE_EXTENSIONS:
                try:
                    print(f"Запуск OCR Tesseract для {unique_filename}...")
                    img = Image.open(io.BytesIO(file_bytes))
                    img = ImageOps.grayscale(img)
                    config_str = '--psm 6' # Оставляем 6, можно экспериментировать
                    extracted_text = pytesseract.image_to_string(img, lang='ukr+eng', config=config_str)
                    print(f"--- OCR Результат (ukr+eng, {config_str}) ---")
                    print(extracted_text[:500] + "..." if extracted_text else "Текст не знайдено.")
                    print("------------------------------------------")
                    MIN_OCR_CHARS = 50
                    if not extracted_text or len(extracted_text) < MIN_OCR_CHARS:
                        print(f"OCR результат занадто короткий...")
                        flash(f'Якість розпізнавання тексту низька...', 'info')
                        ocr_failed_for_image = True
                        extracted_text = None
                except Exception as e_ocr:
                    print(f"Помилка OCR Tesseract: {e_ocr}")
                    flash(f'Помилка під час розпізнавання тексту: {e_ocr}', 'danger')
                    extracted_text = None
                    ocr_failed_for_image = True
                    flash('Помилка розпізнавання тексту...', 'warning')
            else:
                 flash('Цей тип файлу не підтримується для розпізнавання тексту.', 'warning')

            # Извлечение даты из текста
            an_date = extract_date_from_text(extracted_text) if extracted_text else None
            print(f"--- ИЗВЛЕЧЕННАЯ ДАТА ---")
            print(f"Дата анализа: {an_date}")
            print("-------------------------")

            # Анализ через OpenAI
            analysis_result_text = None
            is_descriptive_type = selected_doc_type_key in ['ultrasound', 'mri', 'ct', 'conclusion', 'other']
            prompt_to_use = PROMPT_DESCRIPTIVE if is_descriptive_type else PROMPT_INDICATORS

            if openai_client:
                content_items = []
                analysis_target = None
                if ocr_failed_for_image and file_extension in IMAGE_EXTENSIONS:
                    analysis_target = 'зображення'
                    try:
                        with open(filepath, "rb") as image_file: base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                        mime_type = f"image/{file_extension}" if file_extension != 'jpg' else 'image/jpeg'
                        content_items = [{"type": "text", "text": prompt_to_use}, {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}", "detail": "auto"}}]
                    except Exception as e_img: analysis_target = None
                elif extracted_text:
                    analysis_target = 'текст'
                    try:
                        messages_for_text = [{"role": "system", "content": "Ти корисний асистент..."}, {"role": "user", "content": prompt_to_use + "\n\nТекст документу:\n" + extracted_text}]
                        content_items = messages_for_text # Для一致性
                    except Exception as e_prep_text: analysis_target = None

                if analysis_target and content_items:
                    print(f"Відправка {'зображення' if analysis_target == 'зображення' else 'тексту'} в OpenAI...")
                    try:
                        response = openai_client.chat.completions.create(
                            model="gpt-4o", response_format={ "type": "json_object" },
                            messages= content_items if analysis_target == 'текст' else [{"role": "user", "content": content_items}],
                            max_tokens=4000
                        )
                        analysis_result_text = response.choices[0].message.content
                        print(f"--- Результат аналізу ({analysis_target}) від OpenAI (JSON) ---")
                        print(analysis_result_text)
                        print("----------------------------------------------------")
                    except Exception as e_openai:
                         flash(f'Помилка під час аналізу ({analysis_target}) через OpenAI: {e_openai}', 'danger')
                         print(f"Помилка OpenAI API ({analysis_target}): {e_openai}")
                         analysis_result_text = None

                # Парсинг и сохранение
                if analysis_result_text:
                    try:
                        analysis_data = json.loads(analysis_result_text)
                        print(f"--- JSON УСПЕШНО РАСПАРСЕН ---")
                        # Данные для Analysis
                        doc_type = selected_doc_type_key
                        # Дату ищем в тексте или берем из JSON для описательных
                        final_analysis_date = an_date or analysis_data.get('дата_дослідження') if is_descriptive_type else an_date
                        print(f"--- ИСПОЛЬЗУЕМЫЕ ДАННЫЕ ---")
                        print(f"Тип документа (выбран): {doc_type}")
                        print(f"Дата анализа (финал): {final_analysis_date}")
                        print("-------------------------")

                        new_analysis = Analysis(
                            user_id=current_user.id, filename=unique_filename,
                            document_type=doc_type, analysis_date=final_analysis_date,
                            raw_result_text=analysis_result_text
                        )
                        db.session.add(new_analysis)
                        db.session.flush()

                        indicators_to_save = []
                        processed_names = set()
                        # Ищем показатели ТОЛЬКО если тип не описательный
                        if not is_descriptive_type:
                            indicators_data = analysis_data.get('показники', [])
                            print(f"--- НАЙДЕННЫЕ ПОКАЗАТЕЛИ (перед сохранением, {len(indicators_data)} шт.) ---")
                            print("-----------------------------------------------")
                            saved_count = 0
                            if isinstance(indicators_data, list):
                                 for i, ind_data in enumerate(indicators_data):
                                     if isinstance(ind_data, dict):
                                         # Инициализация
                                         name=None; value_raw=None; units=None; ref_range=None; value_str=None
                                         # Извлечение ключей из промпта
                                         name = ind_data.get('назва')
                                         value_raw = ind_data.get('значення')
                                         units = ind_data.get('одиниці')
                                         ref_range = ind_data.get('референс')
                                         # Логика разделения value/units
                                         if value_raw:
                                             value_raw_str = str(value_raw).strip()
                                             if units: value_str = value_raw_str
                                             else:
                                                 common_units = ['x10⁹/l', 'x10^9/l', 'x10¹²/l', 'x10^12/l', 'g/l', 'g/dl', '%', 'fl', 'pg', 'mmol/l', 'µl', 'fL', 'pmol/L']
                                                 found_unit_in_value = None
                                                 potential_value = value_raw_str
                                                 for u in common_units:
                                                     if value_raw_str.endswith(f" {u}") or value_raw_str.endswith(u):
                                                         found_unit_in_value = u
                                                         potential_value = value_raw_str[:-len(u)].strip(); break
                                                 value_str = potential_value
                                                 if found_unit_in_value: units = found_unit_in_value
                                         else: value_str = None
                                         # Сохранение
                                         if name and value_str is not None and name not in processed_names:
                                              indicator = Indicator(analysis_id=new_analysis.id, name=name.strip(), value=value_str.strip(), units=units.strip() if units else None, reference_range=ref_range.strip() if ref_range else None)
                                              db.session.add(indicator)
                                              processed_names.add(name)
                                              saved_count += 1
                                         else: print(f"Пропуск показателя: Name={name}, Value={value_str}, Processed={name in processed_names}")
                                     else: print(f"Пропуск: элемент не словарь.")
                            else: print("Попередження: ключ 'показники' в JSON не є списком.")
                        else: # Для описательных типов
                             saved_count = 0 # Показатели не сохраняем
                             print("Описовий документ, показники не зберігаються в окрему таблицю.")

                        print("--- Попытка фиксации изменений в БД ---")
                        db.session.commit()
                        print(f"--- Фиксация изменений УСПЕШНА ({saved_count} показників збережено) ---")
                        flash('Документ успішно оброблено та збережено!', 'success')

                    except json.JSONDecodeError as e_json:
                         print(f"!!! ОШИБКА ПАРСИНГА JSON: {e_json} !!!")
                         flash('Помилка: не вдалося розпізнати структуру відповіді від AI.', 'danger')
                         db.session.rollback()
                         # Сохраняем Analysis с ошибкой
                         error_analysis = Analysis(user_id=current_user.id, filename=unique_filename, document_type=selected_doc_type_key, analysis_date=an_date, raw_result_text=f"ОШИБКА ПАРСИНГА JSON: {e_json}\n\nОРИГИНАЛЬНЫЙ ОТВЕТ:\n{analysis_result_text}")
                         db.session.add(error_analysis)
                         db.session.commit()
                    except Exception as e_db:
                         print(f"!!! ОШИБКА СОХРАНЕНИЯ В БД: {e_db} !!!")
                         db.session.rollback()
                         flash(f'Помилка збереження результатів аналізу в БД: {e_db}', 'danger')
                # Обработка случаев, когда OpenAI не вызывался или вернул ошибку
                elif extracted_text or ocr_failed_for_image: pass # Flash был установлен ранее
                else:
                     if not analysis_result_text and not ocr_failed_for_image:
                         flash(f'Файл "{filename}" збережено, але автоматичний аналіз не виконано.', 'info')
            elif not openai_client: # OpenAI клиент не инициализирован
                flash('Помилка конфігурації OpenAI API. Аналіз неможливий.', 'danger')

        except Exception as e_save: # except для основного try
             flash(f'Помилка при збереженні або обробці файлу: {e_save}', 'danger')
             print(f"Ошибка сохранения/обработки файла: {e_save}")
             try: db.session.rollback()
             except Exception as e_rollback: print(f"Доп. ошибка при откате: {e_rollback}")

        return redirect(url_for('dashboard'))
    else: # Неразрешенный тип файла
        flash('Неприпустимий тип файлу.', 'warning')
        return redirect(url_for('dashboard'))

@app.route('/upload_analysis')
@login_required
@profile_required # <-- Декоратор здесь
def upload_analysis_page():
     # Декоратор уже выполнил проверку
    return render_template('upload_analysis.html', title='Завантажити Аналіз')

@app.route('/analysis/<int:analysis_id>')
@login_required
@profile_required # <-- Декоратор здесь
def analysis_detail(analysis_id):
     # Декоратор уже выполнил проверку
    analysis = Analysis.query.get_or_404(analysis_id)
    if analysis.author != current_user: abort(403)
    return render_template('analysis_detail.html', title=f"Аналіз: {analysis.document_type or 'Деталі'}", analysis=analysis)

# --- Flask CLI Command для создания БД ---
@app.cli.command("init-db")
def init_db_command():
    """Создает таблицы базы данных."""
    try:
        with app.app_context():
             # Теперь модели точно должны быть известны SQLAlchemy
             db.create_all()
        print("База данных успешно инициализирована.")
    except Exception as e:
        print(f"Ошибка при инициализации БД: {e}")

# --- Маршрут для заполнения профиля ---
@app.route('/profile/setup', methods=['GET', 'POST'], endpoint='profile_setup')
@login_required
def profile_setup():
    # Проверка, чтобы не заполнять снова (можно оставить или убрать, т.к. декоратор не пустит на другие страницы)
    # if current_user.profile_complete:
    #     return redirect(url_for('dashboard'))

    form = ProfileForm()
    if form.validate_on_submit():
        try:
            # Получаем пользователя, чтобы обновить
            user = db.session.get(User, int(current_user.get_id()))
            if not user:
                 flash('Помилка: користувача не знайдено.', 'danger')
                 return redirect(url_for('logout')) # Выход, если пользователя нет

            # Присваиваем данные
            user.name = form.name.data
            user.date_of_birth = form.date_of_birth.data
            user.sex = form.sex.data
            user.height_cm = form.height_cm.data
            user.weight_kg = form.weight_kg.data
            user.usual_systolic = form.usual_systolic.data if form.usual_systolic.data is not None else None
            user.usual_diastolic = form.usual_diastolic.data if form.usual_diastolic.data is not None else None
            if form.is_smoker.data == 'yes': user.is_smoker = 'yes'
            elif form.is_smoker.data == 'no' or form.is_smoker.data == 'stopped': user.is_smoker = form.is_smoker.data
            else: user.is_smoker = None
            user.chronic_conditions = form.chronic_conditions.data
            user.current_medications = form.current_medications.data
            user.profile_complete = True

            # --->>> Добавляем user в сессию перед commit <<<---
            db.session.add(user)
            db.session.commit() # <-- Сохраняем
            flash('Ваш профіль успішно створено!', 'success')
            print(f"Профиль пользователя {user.email} завершен и сохранен.")
            return redirect(url_for('dashboard')) # <-- Редирект на дашборд
        except Exception as e:
             db.session.rollback()
             flash(f'Помилка при збереженні профілю: {e}', 'danger')
             print(f"Ошибка сохранения профиля для {current_user.email}: {e}")

    # Предзаполнение формы при GET
    elif request.method == 'GET':
         form.process(obj=current_user)

    return render_template('profile_setup.html', title='Заповніть Профіль', form=form)
# --->>> КОНЕЦ НОВОГО МАРШРУТА <<<---

# --- Маршрут для добавления измерения давления ---
@app.route('/add_bp', methods=['GET', 'POST'], endpoint='add_blood_pressure')
@login_required
@profile_required
def add_bp():
    form = BloodPressureForm()
    if form.validate_on_submit():
        try:
            new_reading = BloodPressureReading(
                user_id=current_user.id,
                systolic=form.systolic.data,
                diastolic=form.diastolic.data,
            )
            # Якщо користувач вказав власну дату/час – використовуємо її
            if form.timestamp.data:
                new_reading.timestamp = form.timestamp.data
            db.session.add(new_reading)
            db.session.commit()
            flash('Вимір тиску успішно збережено!', 'success')
            # DEBUG: сколько записей давления теперь
            total_bp = BloodPressureReading.query.filter_by(user_id=current_user.id).count()
            last_bp = (BloodPressureReading.query.filter_by(user_id=current_user.id)
                       .order_by(BloodPressureReading.timestamp.desc()).limit(5).all())
            print(f"[DEBUG] Всего вимірювань тиску для user {current_user.id}: {total_bp}")
            for r in last_bp:
                print(f"   {r.timestamp}: {r.systolic}/{r.diastolic}")
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Помилка при збереженні виміру тиску: {e}', 'danger')
            print(f"Ошибка сохранения BP для {current_user.email}: {e}")

    return render_template('add_bp.html', title='Додати вимір тиску', form=form)

# --- Helper: deviation status for analysis_detail template ---

def _parse_float(text):
    """Try convert number string with comma/dot to float; returns None if fails."""
    if text is None:
        return None
    # Remove non-number except , . and -
    cleaned = re.sub(r"[^0-9,.-]", "", str(text))
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def get_deviation_status(value_str, reference_str):
    """Return 'low', 'high', or 'normal' depending on value vs reference range.
    reference_str examples: '< 190', '> 40', '3.5-5.5', '18.5 - 25', None
    If cannot determine, return 'normal'."""
    value = _parse_float(value_str)
    if value is None or not reference_str:
        return 'normal'

    ref = reference_str.strip()
    # Replace commas with dots for numbers
    ref = ref.replace(",", ".")
    import re
    # Range pattern
    range_match = re.match(r"^(?P<low>-?\d+(?:\.\d+)?)\s*[-–]\s*(?P<high>-?\d+(?:\.\d+)?)", ref)
    if range_match:
        low = float(range_match.group('low'))
        high = float(range_match.group('high'))
        if value < low:
            return 'low'
        elif value > high:
            return 'high'
        else:
            return 'normal'

    # Less than pattern
    lt_match = re.match(r"^[<≤]\s*(\d+(?:\.\d+)?)", ref)
    if lt_match:
        threshold = float(lt_match.group(1))
        return 'high' if value > threshold else 'normal'

    # Greater than pattern
    gt_match = re.match(r"^[>≥]\s*(\d+(?:\.\d+)?)", ref)
    if gt_match:
        threshold = float(gt_match.group(1))
        return 'low' if value < threshold else 'normal'

    return 'normal'


# --- Статус тиску ---

def get_bp_status(systolic, diastolic, usual_sys=None, usual_dia=None):
    """Повертає словник {'label': str, 'color': str}. Якщо задано індивідуальну норму –
    порівнює з нею (допуск ±15 %). Інакше — базова класифікація WHO."""
    if systolic is None or diastolic is None:
        return {'label': '—', 'color': 'text-gray-500'}

    # Якщо користувач вказав свою норму
    if usual_sys and usual_dia and usual_sys > 0 and usual_dia > 0:
        dev_sys_pct = abs(systolic - usual_sys) / usual_sys
        dev_dia_pct = abs(diastolic - usual_dia) / usual_dia
        dev_sys_mm = abs(systolic - usual_sys)
        dev_dia_mm = abs(diastolic - usual_dia)

        within_tolerance = (dev_sys_pct <= 0.15 and dev_dia_pct <= 0.15) or (dev_sys_mm <= 10 and dev_dia_mm <= 10)

        if within_tolerance:
            return {'label': 'Норма', 'color': 'text-green-600'}
        else:
            # Якщо перевищує особисту норму, але все ще в межах загальної норми ≤130/85 – вважаємо «Норма»
            if systolic <= 130 and diastolic <= 85:
                return {'label': 'Норма', 'color': 'text-green-600'}
            elif systolic > usual_sys or diastolic > usual_dia:
                return {'label': 'Вище норми', 'color': 'text-red-600'}
            else:
                return {'label': 'Нижче норми', 'color': 'text-blue-600'}

    # Загальні межі (сучасна спрощена класифікація)
    if systolic < 90 or diastolic < 60:
        return {'label': 'Низький', 'color': 'text-blue-600'}

    # Розширена «норма»: до 130/85 включно
    if systolic <= 130 and diastolic <= 85:
        return {'label': 'Норма', 'color': 'text-green-600'}

    # Підвищений (передгіпертензія): до 139/89
    if systolic <= 139 or diastolic <= 89:
        return {'label': 'Підвищений', 'color': 'text-amber-600'}

    # Вище — гіпертонія
    return {'label': 'Високий', 'color': 'text-red-600'}

# Додаємо у Jinja
@app.context_processor
def inject_utilities():
    return dict(get_deviation_status=get_deviation_status, get_bp_status=get_bp_status)

# --- Ensure DB Columns exist when running without migrations ---
with app.app_context():
    try:
        inspector = db.inspect(db.engine)
        user_columns = [c['name'] for c in inspector.get_columns('user')]
        if 'name' not in user_columns:
            # SQLite supports simple ALTER TABLE ADD COLUMN
            print("[DB] Добавляю колонку 'name' в таблицу user...")
            db.session.execute(text("ALTER TABLE user ADD COLUMN name VARCHAR(100);"))
            db.session.commit()

        # Добавляем колонки для індивідуального тиску, якщо їх немає
        if 'usual_systolic' not in user_columns:
            print("[DB] Додаю колонку 'usual_systolic'...")
            db.session.execute(text("ALTER TABLE user ADD COLUMN usual_systolic INTEGER;"))
            db.session.commit()

        if 'usual_diastolic' not in user_columns:
            print("[DB] Додаю колонку 'usual_diastolic'...")
            db.session.execute(text("ALTER TABLE user ADD COLUMN usual_diastolic INTEGER;"))
            db.session.commit()
    except Exception as e:
        print(f"[DB] Проверка/добавление колонки name завершилась ошибкой: {e}")

# === API: профиль пользователя ===
@app.route('/api/profile')
@login_required
def api_profile():
    # считаем BMI, чтобы сразу отдать готовое число
    if current_user.height_cm and current_user.weight_kg:
        height_m = current_user.height_cm / 100
        bmi = round(current_user.weight_kg / (height_m * height_m), 1)
    else:
        bmi = None

    return {
        "name": current_user.name,
        "email": current_user.email,
        "dateOfBirth": str(current_user.date_of_birth) if current_user.date_of_birth else None,
        "height": current_user.height_cm,
        "weight": current_user.weight_kg,
        "bmi": bmi,
    }

# === API: історія вимірювань ===
@app.route('/api/measurements')
@login_required
def api_measurements():
    """
    Пока что вернём «рыбу» — шесть последних записей.
    Позже можно читать из БД (таблица, где вы будете зберігати щомісячні дані).
    """
    return {
        "weight": [
            {"date": "2024-01-01", "value": 86},
            {"date": "2024-02-01", "value": 85},
            {"date": "2024-03-01", "value": 84},
            {"date": "2024-04-01", "value": 83},
            {"date": "2024-05-01", "value": 83},
            {"date": "2024-06-01", "value": 83},
        ],
        "bmi": [
            {"date": "2024-01-01", "value": 27.5},
            {"date": "2024-02-01", "value": 27.0},
            {"date": "2024-03-01", "value": 26.8},
            {"date": "2024-04-01", "value": 26.6},
            {"date": "2024-05-01", "value": 26.5},
            {"date": "2024-06-01", "value": 26.5},
        ],
        # по аналогии можно добавить cholesterol, glucose …
    }

# --->>> НОВЫЙ МАРШРУТ РЕДАКТИРОВАНИЯ ПРОФИЛЯ <<<---
@app.route('/profile/edit', methods=['GET', 'POST'], endpoint='profile_edit')
@login_required
@profile_required # Доступ только если профиль уже был заполнен
def edit_profile():
    user = db.session.get(User, int(current_user.get_id()))
    if not user:
        flash('Користувача не знайдено.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        form = ProfileForm()
        if form.validate_on_submit():
            try:
                # Логируем данные из формы
                print(f"--- DEBUG /profile/edit POST ---")
                print(f"Form is_smoker: {form.is_smoker.data}")
                print(f"Form usual_systolic: {form.usual_systolic.data}")
                print(f"Form usual_diastolic: {form.usual_diastolic.data}")
                print(f"------------------------------")

                # Обновляем поля ТОГО ЖЕ объекта user, полученного в начале
                user.name = form.name.data
                user.date_of_birth = form.date_of_birth.data
                user.sex = form.sex.data
                user.height_cm = form.height_cm.data
                user.weight_kg = form.weight_kg.data
                user.usual_systolic = form.usual_systolic.data if form.usual_systolic.data is not None else None
                user.usual_diastolic = form.usual_diastolic.data if form.usual_diastolic.data is not None else None
                user.is_smoker = form.is_smoker.data
                user.chronic_conditions = form.chronic_conditions.data
                user.current_medications = form.current_medications.data

                # Логируем данные объекта user ПЕРЕД commit
                print(f"--- DEBUG /profile/edit POST (Before Commit) ---")
                print(f"User is_smoker: {user.is_smoker}")
                print(f"User usual_systolic: {user.usual_systolic}")
                print(f"User usual_diastolic: {user.usual_diastolic}")
                print(f"----------------------------------------------")

                # --->>> ВОЗВРАЩАЕМ ЯВНОЕ ДОБАВЛЕНИЕ В СЕССИЮ <<<---
                db.session.add(user)
                # --->>> КОНЕЦ ВОЗВРАЩЕНИЯ <<<---

                db.session.commit() # Сохраняем
                print(f"Профиль пользователя {user.email} УСПЕШНО обновлен (commit done).")

                # --->>> ЛОГИРОВАНИЕ ПОСЛЕ COMMIT (читаем снова из БД) <<<---
                try:
                    user_after_commit = db.session.get(User, int(current_user.get_id()))
                    if user_after_commit:
                        print(f"--- DEBUG /profile/edit POST (After Commit Readback) ---")
                        print(f"DB is_smoker: {user_after_commit.is_smoker}")
                        print(f"DB usual_systolic: {user_after_commit.usual_systolic}")
                        print(f"DB usual_diastolic: {user_after_commit.usual_diastolic}")
                        print(f"----------------------------------------------------")
                    else:
                        print("!!! ОШИБКА: Не удалось прочитать пользователя ПОСЛЕ commit !!!")
                except Exception as e_readback:
                    print(f"!!! ОШИБКА при чтении ПОСЛЕ commit: {e_readback} !!!")
                # --->>> КОНЕЦ ЛОГИРОВАНИЯ ПОСЛЕ COMMIT <<<---

                flash('Профіль успішно оновлено!', 'success')
                return redirect(url_for('dashboard'))
            except Exception as e:
                db.session.rollback()
                flash(f'Помилка при оновленні профілю: {e}', 'danger')
                print(f"ОШИБКА обновления профиля для {current_user.email}: {e}")
        elif request.method == 'POST': # Если validate_on_submit вернул False
            print(f"--- DEBUG /profile/edit POST - VALIDATION FAILED ---")
            print(f"Form Errors: {form.errors}")
            print(f"--------------------------------------------------")
    else: # request.method == 'GET'
        form = ProfileForm(obj=user) # Предзаполняем для GET

    return render_template('profile_edit.html', title='Редагувати профіль', form=form)
# --->>> КОНЕЦ НОВОГО МАРШРУТА <<<---

def build_latest_indicators_summary(user_id, max_items=100):
    """Формує текст з відхиленнями останнього аналізу. Повертає рядок або None."""
    # За замовчуванням беремо до 100 пунктів, щоб точно охопити усі показники.
    latest_analysis = (
        Analysis.query.filter_by(user_id=user_id)
        .order_by(Analysis.upload_timestamp.desc())
        .first()
    )
    if not latest_analysis:
        return None
    try:
        data = json.loads(latest_analysis.raw_result_text)
    except Exception:
        return None

    indicators = data.get("показники") if isinstance(data, dict) else None
    if not indicators or not isinstance(indicators, list):
        return None

    abnormal = []
    normals = 0
    for item in indicators[:max_items]:
        if not isinstance(item, dict):
            continue
        name = item.get("назва")
        value = item.get("значення")
        units = item.get("одиниці")
        ref = item.get("референс")
        if name is None or value is None:
            continue
        status = get_deviation_status(value, ref)
        if status in ("high", "low"):
            dir_word = "вище" if status == "high" else "нижче"
            val_part = f"{value} {units}".strip() if units else f"{value}"
            abnormal.append(f"{name}: {val_part} ({dir_word} норми)")
        else:
            normals += 1
    if abnormal:
        return "Відхилення у останньому аналізі: " + "; ".join(abnormal)
    else:
        return "Усі показники останнього аналізу в межах референсних значень."

@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json() or {}
    messages = data.get('messages')

    if not messages or not isinstance(messages, list):
        return {"error": "messages array required"}, 400

    # safety: обмежимо довжину діалогу
    if len(messages) > 30:
        messages = messages[-30:]

    resp = openai_client.chat.completions.create(
        model="gpt-4o", messages=messages, max_tokens=400
    )
    answer = resp.choices[0].message.content
    return {"assistant": answer}

# --- endpoint з коротким profile context ---
@app.route('/api/chat/profile_context')
@login_required
def chat_profile_context():
    profile = current_user
    bp = (BloodPressureReading.query
          .filter_by(user_id=profile.id)
          .order_by(BloodPressureReading.timestamp.desc())
          .first())

    age_val = calc_age(profile.date_of_birth)
    bmi_val = calc_bmi(profile.height_cm, profile.weight_kg)
    last_bp = f"{bp.systolic}/{bp.diastolic}" if bp else "--/--"
    usual_bp = (
        f"{profile.usual_systolic}/{profile.usual_diastolic}"
        if profile.usual_systolic and profile.usual_diastolic else "—"
    )

    indicators_summary = build_latest_indicators_summary(profile.id)

    all_indicators_summary = build_all_indicators_summary(profile.id)

    include_all = request.args.get('full') in ['1', 'true', 'yes']

    context = {
        "name": profile.name,
        "email": profile.email,
        "age": age_val,
        "sex": profile.sex,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "bmi": bmi_val,
        "is_smoker": profile.is_smoker,
        "usual_systolic": profile.usual_systolic,
        "usual_diastolic": profile.usual_diastolic,
        "last_bp": {"systolic": bp.systolic if bp else None, "diastolic": bp.diastolic if bp else None, "timestamp": bp.timestamp.isoformat() if bp else None},
        "indicators_summary": indicators_summary,
        "chronic_conditions": profile.chronic_conditions,
        "current_medications": profile.current_medications,
        "all_indicators_summary": all_indicators_summary
    }

    if include_all:
        analyses_all = (
            Analysis.query
            .filter_by(user_id=profile.id)
            .order_by(Analysis.upload_timestamp.desc())
            .all()
        )
        context["all_analyses"] = [
            {
                "id": a.id,
                "type": a.document_type,
                "analysis_date": (a.analysis_date.isoformat() if a.analysis_date and hasattr(a.analysis_date, "isoformat") else a.analysis_date),
                "uploaded": a.upload_timestamp.isoformat() if a.upload_timestamp else None,
                "filename": a.filename,
                "raw_result_text": a.raw_result_text,
            }
            for a in analyses_all
        ]

    from flask import jsonify
    return jsonify(context)

def calc_age(birth_date):
    """Повертає вік у повних роках або None, якщо дата не задана."""
    if not birth_date:
        return None
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def calc_bmi(height_cm, weight_kg):
    """Повертає ІМТ, округлений до 1 знаку, або None, якщо даних недостатньо."""
    if not height_cm or not weight_kg or height_cm <= 0:
        return None
    try:
        height_m = height_cm / 100
        return round(weight_kg / (height_m * height_m), 1)
    except Exception:
        return None

# --- Нова функція: сумарні відхилення з усіх аналізів ---
def build_all_indicators_summary(user_id, max_items_per_analysis=100):
    """Повертає текст з відхиленнями по ВСІХ аналізах користувача."""
    analyses = (
        Analysis.query.filter_by(user_id=user_id)
        .order_by(Analysis.upload_timestamp.desc())
        .all()
    )
    if not analyses:
        return None

    abnormal = []
    for an in analyses:
        try:
            data = json.loads(an.raw_result_text)
        except Exception:
            continue
        indicators = data.get("показники") if isinstance(data, dict) else None
        if not indicators or not isinstance(indicators, list):
            continue
        for item in indicators[:max_items_per_analysis]:
            if not isinstance(item, dict):
                continue
            name = item.get("назва")
            value = item.get("значення")
            units = item.get("одиниці")
            ref = item.get("референс")
            if name is None or value is None:
                continue
            status = get_deviation_status(value, ref)
            if status in ("high", "low"):
                dir_word = "вище" if status == "high" else "нижче"
                val_part = f"{value} {units}".strip() if units else f"{value}"
                abnormal.append(f"{name}: {val_part} ({dir_word} норми)")

    if abnormal:
        # Уникализуем щоб не дублювати
        seen = set()
        uniq = []
        for item in abnormal:
            if item not in seen:
                uniq.append(item)
                seen.add(item)
        return "Відхилення у ваших аналізах: " + "; ".join(uniq)
    return "Всі показники у наявних аналізах у межах референсних значень."

# === NEW ROUTE: History page ===

@app.route('/history')
@login_required
@profile_required
def history_page():
    return render_template('history.html', title='Історія аналізів')

# === API: list of available indicators ===

from flask import jsonify

@app.route('/api/available_indicators')
@login_required
def api_available_indicators():
    names = (
        db.session.query(Indicator.name)
        .join(Analysis, Indicator.analysis_id == Analysis.id)
        .filter(Analysis.user_id == current_user.id)
        .distinct()
        .order_by(Indicator.name)
        .all()
    )
    bp_exists = db.session.query(BloodPressureReading.id).filter_by(user_id=current_user.id).first() is not None

    indicators_list = [n[0] for n in names]
    if bp_exists:
        indicators_list.extend(["Систолічний тиск", "Діастолічний тиск"])

    indicators_list = sorted(set(indicators_list))
    print("--- DEBUG available_indicators ---", indicators_list)
    return jsonify(indicators_list)

# === API: timeline for chosen indicator ===

@app.route('/api/indicator_timeline')
@login_required
def api_indicator_timeline():
    ind_name = request.args.get('name', '').strip()
    if not ind_name:
        return {"error": "name parameter required"}, 400

    print(f"[DEBUG] indicator_timeline '{ind_name}' user={current_user.id}")

    rows = (
        db.session.query(
            Analysis.analysis_date,
            Analysis.upload_timestamp,
            Indicator.value,
            Indicator.units,
            Indicator.reference_range,
        )
        .join(Analysis, Indicator.analysis_id == Analysis.id)
        .filter(Analysis.user_id == current_user.id, Indicator.name == ind_name)
        .order_by(Analysis.analysis_date.desc().nullslast(), Analysis.upload_timestamp.desc())
        .all()
    )

    timeline = []
    for an_date, uploaded, value, units, ref in rows:
        date_val = an_date or (uploaded.date() if uploaded else None)
        date_str = date_val.isoformat() if date_val and hasattr(date_val, "isoformat") else str(date_val)
        status = get_deviation_status(value, ref)
        timeline.append({
            "date": date_str,
            "value": str(value),
            "units": units,
            "ref": ref,
            "status": status,
        })

    # --- Якщо запитують тиск ---
    if 'тиск' in ind_name.lower():
        bp_rows = (
            BloodPressureReading.query
            .filter_by(user_id=current_user.id)
            .order_by(BloodPressureReading.timestamp.desc())
            .all()
        )
        timeline = []
        for r in bp_rows:
            date_str = r.timestamp.date().isoformat()
            value = r.systolic if 'систолічний' in ind_name.lower() else r.diastolic
            status_dict = get_bp_status(r.systolic, r.diastolic, current_user.usual_systolic, current_user.usual_diastolic)
            label_l = status_dict['label'].lower()
            if 'вище' in label_l:
                st='high'
            elif 'низь' in label_l or 'нижче' in label_l:
                st='low'
            else:
                st='normal'
            timeline.append({
                "date": date_str,
                "value": value,
                "units": "мм рт.ст.",
                "ref": "≤130" if 'систолічний' in ind_name.lower() else "≤85",
                "status": st,
            })
        print(f"BP timeline len={len(timeline)} data={timeline[:3]}")
        return jsonify(timeline)

    print(f"Indicator timeline len={len(timeline)}")
    return jsonify(timeline)

if __name__ == '__main__':
    # ... (Создание папок uploads и instance) ...
    app.run(debug=True)