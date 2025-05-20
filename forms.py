from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, HiddenField, SelectField, IntegerField, FloatField, TextAreaField, DateField, DateTimeLocalField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, NumberRange

class RegistrationForm(FlaskForm):
    email = StringField('Email',
                           validators=[DataRequired(message="Email є обов'язковим полем."),
                                       Email(message='Неправильний формат email.')])
    password = PasswordField('Пароль',
                             validators=[DataRequired(message="Пароль є обов'язковим полем."),
                                         Length(min=6, message='Пароль повинен містити щонайменше 6 символів.')])
    confirm_password = PasswordField('Підтвердіть Пароль',
                                     validators=[DataRequired(message="Підтвердження пароля є обов'язковим."),
                                                 EqualTo('password', message='Паролі повинні співпадати.')])
    submit = SubmitField('Зареєструватися')


class LoginForm(FlaskForm):
    email = StringField('Email',
                        validators=[DataRequired(message="Email є обов'язковим полем."),
                                    Email(message='Неправильний формат email.')])
    password = PasswordField('Пароль',
                             validators=[DataRequired(message="Пароль є обов'язковим полем.")])
    submit = SubmitField('Увійти')


class ProfileForm(FlaskForm):
    name = StringField('ПІБ (імʼя та прізвище)',
                       validators=[DataRequired(message="Вкажіть ваше імʼя."),
                                   Length(min=2, max=100)])
    date_of_birth = DateField('Дата народження',
                              format='%Y-%m-%d',
                              validators=[DataRequired(message="Вкажіть дату народження.")],
                              description="Формат: РРРР-ММ-ДД")
    sex = SelectField('Стать (при народженні)',
                      choices=[('', '-- Оберіть --'), ('male', 'Чоловіча'), ('female', 'Жіноча')],
                      validators=[DataRequired(message="Вкажіть стать.")])
    height_cm = IntegerField('Зріст (см)',
                             validators=[DataRequired(message="Вкажіть зріст."),
                                         NumberRange(min=50, max=300, message="Зріст повинен бути між 50 та 300 см.")])
    weight_kg = FloatField('Вага (кг)',
                           validators=[DataRequired(message="Вкажіть вагу."),
                                       NumberRange(min=10, max=500, message="Вага повинна бути між 10 та 500 кг.")],
                           description="Використовуйте крапку як десятковий роздільник (напр., 70.5)")
    is_smoker = SelectField('Статус куріння',
                           choices=[('', '-- Оберіть --'), ('yes', 'Так, курю зараз'), ('no', 'Ні, не курю'), ('stopped', 'Курив(ла), але кинув(ла)')],
                           validators=[Optional()])
    usual_systolic = IntegerField('Ваш звичайний систолічний тиск (верхнє)',
                                    validators=[Optional(),
                                                NumberRange(min=70, max=250, message="...")])
    usual_diastolic = IntegerField('Ваш звичайний діастолічний тиск (нижнє)',
                                     validators=[Optional(),
                                                 NumberRange(min=40, max=150, message="...")])
    chronic_conditions = TextAreaField('Хронічні захворювання (перелічіть через кому)',
                                       validators=[Optional()],
                                       render_kw={"rows": 3})
    current_medications = TextAreaField('Ліки, які приймаєте постійно (перелічіть через кому)',
                                        validators=[Optional()],
                                        render_kw={"rows": 3})
    submit = SubmitField('Зберегти профіль і продовжити')

# --- Форма добавления давления ---
class BloodPressureForm(FlaskForm):
    systolic = IntegerField('Систолічний тиск (верхнє)',
                            validators=[DataRequired(message="Вкажіть систолічний тиск."),
                                        NumberRange(min=50, max=300, message="Тиск повинен бути між 50 та 300.")])
    diastolic = IntegerField('Діастолічний тиск (нижнє)',
                             validators=[DataRequired(message="Вкажіть діастолічний тиск."),
                                         NumberRange(min=30, max=200, message="Тиск повинен бути між 30 та 200.")])
    timestamp = DateTimeLocalField('Дата і час виміру (якщо відрізняється від поточного)',
                                 format='%Y-%m-%dT%H:%M',
                                 validators=[Optional()])
    submit = SubmitField('Зберегти вимір')

# --- УДАЛЕНЫ IndicatorEditForm и AnalysisEditForm --- 