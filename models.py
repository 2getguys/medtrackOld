# models.py
from extensions import db # Импортируем db из extensions.py
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
# Убедимся, что импортируем datetime здесь, если он нужен для default
from datetime import datetime

# --- Модель пользователя ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    # Связь должна использовать строку 'Analysis'
    analyses = db.relationship('Analysis', backref='author', lazy=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    sex = db.Column(db.String(10), nullable=True)
    height_cm = db.Column(db.Integer, nullable=True)
    weight_kg = db.Column(db.Float, nullable=True)
    is_smoker = db.Column(db.Boolean, nullable=True)
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
    # ForeignKey должен ссылаться на 'user.id' (имя таблицы маленькими буквами)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(200))
    # db.func.current_timestamp требует db, который уже импортирован
    upload_timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    document_type = db.Column(db.String(100))
    analysis_date = db.Column(db.String(50))
    raw_result_text = db.Column(db.Text)
    # Связь должна использовать строку 'Indicator'
    indicators = db.relationship('Indicator', backref='analysis', lazy=True, cascade="all, delete-orphan")

# --- Модель для хранения отдельных показателей ---
class Indicator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # ForeignKey должен ссылаться на 'analysis.id'
    analysis_id = db.Column(db.Integer, db.ForeignKey('analysis.id'), nullable=False)
    name = db.Column(db.String(100))
    value = db.Column(db.String(50))
    units = db.Column(db.String(50))
    reference_range = db.Column(db.String(100))
