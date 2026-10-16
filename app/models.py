from app import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app
from itsdangerous import URLSafeTimedSerializer as Serializer


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)

    # Plano e Status
    plan = db.Column(db.String(20), nullable=False, default='basic')
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(20), default='pending')  # 'pending', 'paid', 'failed'
    is_active = db.Column(db.Boolean, default=False)  # Só ativa após clicar no link do e-mail

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Geração de Token Único para Ativação de E-mail
    def generate_confirmation_token(self):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps(self.email, salt='email-confirm-salt')

    @staticmethod
    def verify_confirmation_token(token, expiration=86400):  # Token expira em 24h
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            email = s.loads(token, salt='email-confirm-salt', max_age=expiration)
        except Exception:
            return None
        return User.query.filter_by(email=email).first()