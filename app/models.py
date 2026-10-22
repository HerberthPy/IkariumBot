import base64
import os
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
    has_session = db.Column(db.Boolean, default=False)  # Indica se os cookies/storage_state foram capturados
    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    # Dono do Lobby e Proxy vinculada
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    proxy_id = db.Column(db.Integer, db.ForeignKey('proxies.id'), nullable=True)

    # Relacionamento com as Contas (Servidores) capturadas no Lobby
    contas = db.relationship('Conta', backref='lobby', lazy=True, cascade='all, delete-orphan')

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

    def get_session_path(self):
        """Retorna o caminho absoluto do arquivo JSON de sessão do Playwright para este Lobby."""
        base_dir = current_app.root_path
        sessions_dir = os.path.join(os.path.dirname(base_dir), 'sessions')
        os.makedirs(sessions_dir, exist_ok=True)
        return os.path.join(sessions_dir, f'session_lobby_{self.id}.json')

    @property
    def is_session_valid(self):
        """Verifica se o ficheiro de sessão JSON realmente existe no disco."""
        session_file = self.get_session_path()
        return os.path.exists(session_file) and os.path.getsize(session_file) > 0


class Conta(db.Model):
    __tablename__ = 'contas'

    id = db.Column(db.Integer, primary_key=True)
    gameforge_account_id = db.Column(db.String(100), nullable=True, index=True)  # ID único da conta na Gameforge
    servidor = db.Column(db.String(100), nullable=False)  # Ex: Alpha, Beta, etc.
    pais = db.Column(db.String(10), nullable=False, default='pt')  # Ex: pt, br, en
    nome_usuario = db.Column(db.String(100), nullable=False)  # Nome do jogador no servidor
    email = db.Column(db.String(120), nullable=False)  # E-mail associado
    ativo = db.Column(db.Boolean, default=True)  # Status da conta na Gameforge

    # NOVOS CAMPOS PARA CONTROLE DE AUTOMAÇÃO E REGISTRO DE ACESSO
    automacao_ativa = db.Column(db.Boolean, default=True, nullable=False)  # Se a automação deve rodar nesta conta
    ultimo_login = db.Column(db.DateTime, nullable=True)  # Data e hora do último acesso pelo bot

    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    # Chave estrangeira vinculando a conta ao Lobby
    lobby_id = db.Column(db.Integer, db.ForeignKey('lobbies.id'), nullable=False)

    @property
    def dias_sem_login(self):
        """Calcula a diferença em dias entre a data do último login e a data atual."""
        if not self.ultimo_login:
            return "Nunca"

        agora = get_brasilia_time().replace(tzinfo=None)
        ultimo = self.ultimo_login.replace(tzinfo=None) if self.ultimo_login.tzinfo else self.ultimo_login

        dias = (agora.date() - ultimo.date()).days
        return max(0, dias)

    def __repr__(self):
        return f'<Conta {self.nome_usuario} @ {self.servidor} ({self.pais})>'