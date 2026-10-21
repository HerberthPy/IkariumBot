import base64
from datetime import datetime
import pytz
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet, InvalidToken
from app import db


def get_brasilia_time():
    """Retorna a data e hora atual exatamente no fuso horário de Brasília (UTC-3)."""
    tz = pytz.timezone('America/Sao_Paulo')
    return datetime.now(tz)


def get_cipher():
    """Retorna o objeto Fernet usando FERNET_KEY ou derivando de SECRET_KEY."""
    fernet_key = current_app.config.get('FERNET_KEY')
    if fernet_key:
        return Fernet(fernet_key.encode('utf-8'))

    secret = current_app.config['SECRET_KEY'].encode('utf-8')
    key = base64.urlsafe_b64encode(secret.ljust(32)[:32])
    return Fernet(key)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # 0 = Usuário comum (padrão) | 1 = Administrador
    is_admin = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    # Proxies atribuídas pelo Admin a este Usuário
    assigned_proxies = db.relationship('Proxy', backref='assigned_user', lazy=True)

    # Lobbies criados por este Usuário
    lobbies = db.relationship('Lobby', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def max_allowed_lobbies(self):
        """O limite de lobbies é exatamente a quantidade de proxies atribuídas ao usuário."""
        return len(self.assigned_proxies)

    @property
    def total_lobbies(self):
        """Retorna a quantidade total de lobbies criados pelo usuário."""
        return len(self.lobbies)

    @property
    def can_create_lobby(self):
        """Retorna True se o usuário ainda possui margem para criar novos lobbies."""
        return self.total_lobbies < self.max_allowed_lobbies


class Proxy(db.Model):
    __tablename__ = 'proxies'

    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(100), nullable=False)  # Endereço IP / Host
    port = db.Column(db.Integer, nullable=False)  # Porta
    username = db.Column(db.String(100), nullable=True)  # Usuário
    password_encrypted = db.Column(db.String(255), nullable=True)  # Senha Criptografada
    country = db.Column(db.String(10), nullable=True)  # Código do país (ex: BR, US)
    status = db.Column(db.String(20), default='ATIVO')  # 'ATIVO' ou 'INATIVO' (definido pelo Admin)
    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    # FK do Usuário a quem o Admin atribuiu este Proxy (None = Disponível no Pool Geral)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relacionamento com Lobbies (Lobbies que estão utilizando esta proxy)
    lobbies = db.relationship('Lobby', backref='proxy', lazy=True)

    @property
    def is_assigned(self):
        """Retorna True se o Admin já atribuiu esta proxy a um Usuário."""
        return self.user_id is not None

    @property
    def is_in_use(self):
        """Retorna True se algum Lobby do usuário está atualmente vinculado a esta proxy."""
        return len(self.lobbies) > 0

    def set_password(self, password):
        """Criptografa a senha do proxy antes de salvar."""
        if password:
            cipher = get_cipher()
            self.password_encrypted = cipher.encrypt(password.encode('utf-8')).decode('utf-8')
        else:
            self.password_encrypted = None

    def get_password(self):
        """Descriptografa a senha do proxy."""
        if not self.password_encrypted:
            return ""
        try:
            cipher = get_cipher()
            return cipher.decrypt(self.password_encrypted.encode('utf-8')).decode('utf-8')
        except (InvalidToken, Exception):
            return self.password_encrypted

    def get_proxy_url(self):
        """Retorna a string formatada para conexões (http://user:pass@ip:port ou http://ip:port)."""
        pwd = self.get_password()
        if self.username and pwd:
            return f"http://{self.username}:{pwd}@{self.address}:{self.port}"
        return f"http://{self.address}:{self.port}"


class Lobby(db.Model):
    __tablename__ = 'lobbies'

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    password_encrypted = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='ATIVO')
    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    # Dono do Lobby e Proxy vinculada
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    proxy_id = db.Column(db.Integer, db.ForeignKey('proxies.id'), nullable=True)

    @property
    def country(self):
        """Herda dinamicamente o país a partir da Proxy vinculada."""
        if self.proxy and self.proxy.country:
            return self.proxy.country
        return "N/A"

    def set_password(self, password):
        """Criptografa a senha do lobby antes de salvar."""
        if password:
            cipher = get_cipher()
            self.password_encrypted = cipher.encrypt(password.encode('utf-8')).decode('utf-8')

    def get_password(self):
        """Descriptografa a senha para uso do bot ou exibição."""
        if not self.password_encrypted:
            return ""
        try:
            cipher = get_cipher()
            return cipher.decrypt(self.password_encrypted.encode('utf-8')).decode('utf-8')
        except (InvalidToken, Exception):
            return self.password_encrypted