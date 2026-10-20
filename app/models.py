import base64
from datetime import datetime, timedelta
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


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # Plano e Pagamento
    plan = db.Column(db.String(20), default='basico')  # 'basico' ou 'premium'
    plan_cycle = db.Column(db.String(20), default='mensal')  # 'mensal' ou 'anual'
    payment_method = db.Column(db.String(20))
    payment_status = db.Column(db.String(20), default='pago')  # 'pago', 'pending', 'vencido'
    is_active = db.Column(db.Boolean, default=True)

    # Datas de Controle de Assinatura (Fuso de Brasília)
    created_at = db.Column(db.DateTime, default=get_brasilia_time)
    expires_at = db.Column(db.DateTime, nullable=True)

    # Relacionamentos
    proxies = db.relationship('Proxy', backref='owner', lazy=True, cascade='all, delete-orphan')
    lobbies = db.relationship('Lobby', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def activate_plan(self, plan_type='basico', plan_cycle='mensal'):
        """Define/renova o plano e calcula a nova data de expiração no fuso de Brasília."""
        now_bsb = get_brasilia_time()
        self.plan = plan_type
        self.plan_cycle = plan_cycle
        self.payment_status = 'pago'

        if plan_cycle == 'anual':
            self.expires_at = now_bsb + timedelta(days=365)
        else:
            self.expires_at = now_bsb + timedelta(days=30)

    @property
    def days_remaining(self):
        """Calcula os dias restantes (D-1) até o plano expirar."""
        if not self.expires_at:
            return 0
        now_bsb = get_brasilia_time().replace(tzinfo=None)
        expires = self.expires_at.replace(tzinfo=None)
        delta = expires - now_bsb
        return max(0, delta.days)

    @property
    def is_plan_expired(self):
        """Retorna True se a data atual ultrapassou a expiração."""
        if not self.expires_at:
            return True
        now_bsb = get_brasilia_time().replace(tzinfo=None)
        return now_bsb >= self.expires_at.replace(tzinfo=None)

    @property
    def is_modules_active(self):
        """Retorna True se o plano estiver em dia, mantendo os módulos ativos."""
        return not self.is_plan_expired and self.payment_status == 'pago'

    @property
    def show_expiration_alert(self):
        """Alerta de 10 dias ou menos para o vencimento."""
        return 0 < self.days_remaining <= 10 and not self.is_plan_expired

    @property
    def max_allowed_lobbies(self):
        """Plano Básico permite apenas 1 Lobby; Premium é ilimitado."""
        if self.plan == 'basico':
            return 1
        return 9999


def get_cipher():
    """Retorna o objeto Fernet usando FERNET_KEY ou derivando de SECRET_KEY."""
    fernet_key = current_app.config.get('FERNET_KEY')
    if fernet_key:
        return Fernet(fernet_key.encode('utf-8'))

    secret = current_app.config['SECRET_KEY'].encode('utf-8')
    key = base64.urlsafe_b64encode(secret.ljust(32)[:32])
    return Fernet(key)


class Proxy(db.Model):
    __tablename__ = 'proxies'

    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(100), nullable=False)  # Endereço IP / Host
    port = db.Column(db.Integer, nullable=False)  # Porta HTTP/SOCKS5
    username = db.Column(db.String(100), nullable=False)  # Usuário do Webshare
    password_encrypted = db.Column(db.String(255), nullable=False)  # Senha Criptografada
    country = db.Column(db.String(10), nullable=True)  # Código do país (ex: BR, US)
    status = db.Column(db.String(20), default='ATIVO')  # 'ATIVO' ou 'INATIVO'
    capacity = db.Column(db.Integer, default=1, nullable=False)  # Qtd de Lobbies permitidos por proxy
    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    # Chave Estrangeira (FK do Usuário Dono)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Relacionamento com Lobbies
    lobbies = db.relationship('Lobby', backref='proxy', lazy=True)

    @property
    def used(self):
        """Retorna a quantidade de lobbies atualmente usando este Proxy."""
        return len(self.lobbies)

    @property
    def available(self):
        """Calcula dinamicamente as vagas restantes no Proxy."""
        return max(0, self.capacity - self.used)

    def set_password(self, password):
        """Criptografa a senha do proxy antes de salvar."""
        if password:
            cipher = get_cipher()
            self.password_encrypted = cipher.encrypt(password.encode('utf-8')).decode('utf-8')

    def get_password(self):
        """Descriptografa a senha do proxy para uso nas chamadas do bot ou exibição."""
        if not self.password_encrypted:
            return ""
        try:
            cipher = get_cipher()
            return cipher.decrypt(self.password_encrypted.encode('utf-8')).decode('utf-8')
        except (InvalidToken, Exception):
            return self.password_encrypted

    def get_proxy_url(self):
        """Retorna a string completa formatada para Playwright/Requests (ex: http://user:pass@ip:port)."""
        return f"http://{self.username}:{self.get_password()}@{self.address}:{self.port}"


class Lobby(db.Model):
    __tablename__ = 'lobbies'

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(100), nullable=False)  # APELIDO
    email = db.Column(db.String(120), nullable=False)  # E-MAIL
    password_encrypted = db.Column(db.String(255), nullable=False)  # SENHA CRIPTOGRAFADA
    status = db.Column(db.String(20), default='ATIVO')  # 'ATIVO' ou 'INATIVO'
    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    # Chaves Estrangeiras (FK)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    proxy_id = db.Column(db.Integer, db.ForeignKey('proxies.id'), nullable=True)

    @property
    def country(self):
        """Herda dinamicamente o código do país a partir do Proxy vinculado."""
        if self.proxy and self.proxy.country:
            return self.proxy.country
        return "N/A"

    def set_password(self, password):
        """Criptografa a senha do lobby antes de salvar."""
        if password:
            cipher = get_cipher()
            self.password_encrypted = cipher.encrypt(password.encode('utf-8')).decode('utf-8')

    def get_password(self):
        """Descriptografa a senha para exibição no frontend."""
        if not self.password_encrypted:
            return ""
        try:
            cipher = get_cipher()
            return cipher.decrypt(self.password_encrypted.encode('utf-8')).decode('utf-8')
        except (InvalidToken, Exception):
            return self.password_encrypted