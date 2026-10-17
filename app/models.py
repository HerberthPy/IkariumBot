from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

# Adicione o UserMixin na declaração da classe
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.String(20))
    payment_method = db.Column(db.String(20))
    payment_status = db.Column(db.String(20), default='pending')
    is_active = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)