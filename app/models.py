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
    vpns = db.relationship('VPN', backref='owner', lazy=True, cascade='all, delete-orphan')
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

    @property
    def free_vpns_included(self):
        """Plano Básico = 0 VPNs grátis | Premium = 1 VPN grátis inclusa."""
        if self.plan == 'premium':
            return 1
        return 0


def get_cipher():
    # Cria uma chave determinística de 32 bytes a partir da SECRET_KEY do Flask
    secret = current_app.config['SECRET_KEY'].encode('utf-8')
    key = base64.urlsafe_b64encode(secret.ljust(32)[:32])
    return Fernet(key)


class VPN(db.Model):
    __tablename__ = 'vpns'

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    password_encrypted = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='INATIVA')
    capacity = db.Column(db.Integer, default=10, nullable=False)
    created_at = db.Column(db.DateTime, default=get_brasilia_time)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Relacionamento com Lobbies
    lobbies = db.relationship('Lobby', backref='vpn', lazy=True)

    @property
    def used(self):
        """Retorna a quantidade de lobbies atualmente usando esta VPN."""
        return len(self.lobbies)

    @property
    def available(self):
        """Calcula dinamicamente as vagas restantes na VPN."""
        return max(0, self.capacity - self.used)

    def set_password(self, password):
        """Criptografa a senha antes de salvar."""
        if password:
            cipher = get_cipher()
            self.password_encrypted = cipher.encrypt(password.encode('utf-8')).decode('utf-8')

    def get_password(self):
        """Descriptografa a senha para exibir na tela."""
        if not self.password_encrypted:
            return ""
        try:
            cipher = get_cipher()
            return cipher.decrypt(self.password_encrypted.encode('utf-8')).decode('utf-8')
        except (InvalidToken, Exception):
            return self.password_encrypted

class Lobby(db.Model):
    __tablename__ = 'lobbies'

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(100), nullable=False)  # APELIDO
    email = db.Column(db.String(120), nullable=False)  # E-MAIL
    password_encrypted = db.Column(db.String(255), nullable=False)  # SENHA CRIPTOGRAFADA
    country = db.Column(db.String(100), nullable=False)  # PAÍS DE CONEXÃO
    accounts_count = db.Column(db.Integer, default=0, nullable=False)  # CONTAS VINCULADAS
    status = db.Column(db.String(20), default='ATIVA')  # 'ATIVA' ou 'INATIVA'
    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    # Chaves Estrangeiras (FK)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    vpn_id = db.Column(db.Integer, db.ForeignKey('vpns.id'), nullable=False)

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