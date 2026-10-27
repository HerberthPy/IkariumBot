# app/models.py

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

    assigned_proxies = db.relationship('Proxy', backref='assigned_user', lazy=True)
    lobbies = db.relationship('Lobby', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def max_allowed_lobbies(self):
        return len(self.assigned_proxies)

    @property
    def total_lobbies(self):
        return len(self.lobbies)

    @property
    def can_create_lobby(self):
        return self.total_lobbies < self.max_allowed_lobbies


class Proxy(db.Model):
    __tablename__ = 'proxies'

    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(100), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(100), nullable=True)
    password_encrypted = db.Column(db.String(255), nullable=True)
    country = db.Column(db.String(10), nullable=True)
    status = db.Column(db.String(20), default='ATIVO')
    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    lobbies = db.relationship('Lobby', backref='proxy', lazy=True)

    @property
    def is_assigned(self):
        return self.user_id is not None

    @property
    def is_in_use(self):
        return len(self.lobbies) > 0

    def set_password(self, password):
        if password:
            cipher = get_cipher()
            self.password_encrypted = cipher.encrypt(password.encode('utf-8')).decode('utf-8')
        else:
            self.password_encrypted = None

    def get_password(self):
        if not self.password_encrypted:
            return ""
        try:
            cipher = get_cipher()
            return cipher.decrypt(self.password_encrypted.encode('utf-8')).decode('utf-8')
        except (InvalidToken, Exception):
            return self.password_encrypted

    def get_proxy_url(self):
        pwd = self.get_password()
        if self.username and pwd:
            return f"http://{self.username}:{pwd}@{self.address}:{self.port}"
        return f"http://{self.address}:{self.port}"


class Lobby(db.Model):
    __tablename__ = 'lobbies'

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(20), default='ATIVO')
    has_session = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    proxy_id = db.Column(db.Integer, db.ForeignKey('proxies.id'), nullable=True)

    contas = db.relationship('Conta', backref='lobby', lazy=True, cascade='all, delete-orphan')

    @property
    def country(self):
        if self.proxy and self.proxy.country:
            return self.proxy.country
        return "N/A"

    def get_session_path(self):
        base_dir = current_app.root_path
        sessions_dir = os.path.join(os.path.dirname(base_dir), 'sessions')
        os.makedirs(sessions_dir, exist_ok=True)
        return os.path.join(sessions_dir, f'session_lobby_{self.id}.json')

    @property
    def is_session_valid(self):
        session_file = self.get_session_path()
        return os.path.exists(session_file) and os.path.getsize(session_file) > 0

    @property
    def tropas_totais_lobby(self):
        totais = {}
        for conta in self.contas:
            for tipo, qtd in conta.tropas_totais_conta.items():
                totais[tipo] = totais.get(tipo, 0) + qtd
        return totais

    @property
    def frotas_totais_lobby(self):
        totais = {}
        for conta in self.contas:
            for tipo, qtd in conta.frotas_totais_conta.items():
                totais[tipo] = totais.get(tipo, 0) + qtd
        return totais


class LobbyIPHistory(db.Model):
    __tablename__ = 'lobby_ip_history'

    id = db.Column(db.Integer, primary_key=True)
    lobby_id = db.Column(db.Integer, db.ForeignKey('lobbies.id'), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    recorded_at = db.Column(db.DateTime, default=get_brasilia_time)

    lobby = db.relationship('Lobby', backref=db.backref('ip_history', lazy=True, cascade='all, delete-orphan'))


class Ilha(db.Model):
    __tablename__ = 'ilhas'

    id = db.Column(db.Integer, primary_key=True)
    coordenada_x = db.Column(db.Integer, nullable=False)
    coordenada_y = db.Column(db.Integer, nullable=False)
    tipo_recurso_luxo = db.Column(db.String(30), default='marmore')
    nivel_serraria = db.Column(db.Integer, default=0)
    nivel_mina_luxo = db.Column(db.Integer, default=0)

    milagre_nome = db.Column(db.String(50), nullable=True)
    milagre_nivel = db.Column(db.Integer, default=0)

    cidades = db.relationship('Cidade', backref='ilha', lazy=True)

    def __repr__(self):
        return f'<Ilha [{self.coordenada_x}:{self.coordenada_y}] Luxo: {self.tipo_recurso_luxo} | Milagre: {self.milagre_nome} Nv.{self.milagre_nivel}>'


class Cidade(db.Model):
    __tablename__ = 'cidades'

    id = db.Column(db.Integer, primary_key=True)
    conta_id = db.Column(db.Integer, db.ForeignKey('contas.id'), nullable=False)
    ilha_id = db.Column(db.Integer, db.ForeignKey('ilhas.id'), nullable=False)

    nome = db.Column(db.String(100), nullable=False)
    posicao_na_ilha = db.Column(db.Integer, nullable=True)

    populacao_atual = db.Column(db.Integer, default=0)
    populacao_maxima = db.Column(db.Integer, default=0)
    populacao_livre = db.Column(db.Integer, default=0)

    trabalhadores_serraria = db.Column(db.Integer, default=0)
    trabalhadores_luxo = db.Column(db.Integer, default=0)
    cientistas = db.Column(db.Integer, default=0)
    sacerdotes = db.Column(db.Integer, default=0)

    madeira = db.Column(db.Float, default=0.0)
    vinho = db.Column(db.Float, default=0.0)
    marmore = db.Column(db.Float, default=0.0)
    cristal = db.Column(db.Float, default=0.0)
    enxofre = db.Column(db.Float, default=0.0)

    construcoes = db.relationship('Construcao', backref='cidade', lazy=True, cascade='all, delete-orphan')
    tropas = db.relationship('Tropa', backref='cidade', lazy=True, cascade='all, delete-orphan')
    frotas = db.relationship('Frota', backref='cidade', lazy=True, cascade='all, delete-orphan')

    def atualizar_estado_jogo(self, dados_raspados):
        campos_permitidos = [
            'populacao_atual', 'populacao_maxima', 'populacao_livre',
            'trabalhadores_serraria', 'trabalhadores_luxo', 'cientistas', 'sacerdotes',
            'madeira', 'vinho', 'marmore', 'cristal', 'enxofre'
        ]

        for campo, valor in dados_raspados.items():
            if campo in campos_permitidos and valor is not None:
                setattr(self, campo, type(getattr(self, campo))(valor))

        db.session.commit()
        return True

    def __repr__(self):
        return f'<Cidade {self.nome} (Ilha ID: {self.ilha_id})>'


class Tropa(db.Model):
    __tablename__ = 'tropas'

    id = db.Column(db.Integer, primary_key=True)
    cidade_id = db.Column(db.Integer, db.ForeignKey('cidades.id'), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Integer, default=0)
    localizacao = db.Column(db.String(30), default='na_cidade')

    def __repr__(self):
        return f'<Tropa {self.tipo}: {self.quantidade}>'


class Frota(db.Model):
    __tablename__ = 'frotas'

    id = db.Column(db.Integer, primary_key=True)
    cidade_id = db.Column(db.Integer, db.ForeignKey('cidades.id'), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<Frota {self.tipo}: {self.quantidade}>'


class Construcao(db.Model):
    __tablename__ = 'construcoes'

    id = db.Column(db.Integer, primary_key=True)
    cidade_id = db.Column(db.Integer, db.ForeignKey('cidades.id'), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    nivel = db.Column(db.Integer, default=1)
    posicao_slot = db.Column(db.Integer, nullable=False)
    em_construcao = db.Column(db.Boolean, default=False)
    termino_construcao = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<Construcao {self.tipo} Nv.{self.nivel} [Slot {self.posicao_slot}]>'


class Modulo(db.Model):
    __tablename__ = 'modulos'

    id = db.Column(db.Integer, primary_key=True)
    nome_tecnico = db.Column(db.String(50), unique=True, nullable=False) # Ex: 'coleta_info', 'doacao'
    nome_exibicao = db.Column(db.String(100), nullable=False) # Ex: 'Coleta de Informações'
    descricao = db.Column(db.String(255), nullable=True)

    contas_habilitadas = db.relationship('ContaModulo', backref='modulo', lazy=True, cascade='all, delete-orphan')


class ContaModulo(db.Model):
    __tablename__ = 'conta_modulos'

    id = db.Column(db.Integer, primary_key=True)
    conta_id = db.Column(db.Integer, db.ForeignKey('contas.id'), nullable=False)
    modulo_id = db.Column(db.Integer, db.ForeignKey('modulos.id'), nullable=False)
    ativo = db.Column(db.Boolean, default=True)


class Conta(db.Model):
    __tablename__ = 'contas'

    id = db.Column(db.Integer, primary_key=True)
    gameforge_account_id = db.Column(db.String(100), nullable=True, index=True)
    servidor = db.Column(db.String(100), nullable=False)
    pais = db.Column(db.String(10), nullable=False, default='pt')
    nome_usuario = db.Column(db.String(100), nullable=False)

    ativo = db.Column(db.Boolean, default=True)
    status_jogo = db.Column(db.String(50), default='Ativa')

    automacao_ativa = db.Column(db.Boolean, default=False, nullable=False)
    ultimo_login = db.Column(db.DateTime, nullable=True)
    is_playing_active = db.Column(db.Boolean, default=False)

    ouro = db.Column(db.String(50), default="0")
    ouro_rendimento = db.Column(db.String(50), default="+0/h")
    barcos_totais = db.Column(db.Integer, default=0)
    barcos_disponiveis = db.Column(db.Integer, default=0)
    cargueiros_totais = db.Column(db.Integer, default=0)
    cargueiross_disponiveis = db.Column(db.Integer, default=0)

    ultima_sincronizacao = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=get_brasilia_time)

    lobby_id = db.Column(db.Integer, db.ForeignKey('lobbies.id'), nullable=False)
    cidades = db.relationship('Cidade', backref='conta', lazy=True, cascade='all, delete-orphan')
    modulos_habilitados = db.relationship('ContaModulo', backref='conta', lazy=True, cascade='all, delete-orphan')

    @property
    def recursos_totais_imperio(self):
        totais = {"madeira": 0.0, "vinho": 0.0, "marmore": 0.0, "cristal": 0.0, "enxofre": 0.0}
        for cidade in self.cidades:
            totais["madeira"] += cidade.madeira or 0.0
            totais["vinho"] += cidade.vinho or 0.0
            totais["marmore"] += cidade.marmore or 0.0
            totais["cristal"] += cidade.cristal or 0.0
            totais["enxofre"] += cidade.enxofre or 0.0
        return totais

    @property
    def tropas_totais_conta(self):
        totais = {}
        for cidade in self.cidades:
            for tropa in cidade.tropas:
                totais[tropa.tipo] = totais.get(tropa.tipo, 0) + tropa.quantidade
        return totais

    @property
    def frotas_totais_conta(self):
        totais = {}
        for cidade in self.cidades:
            for frota in cidade.frotas:
                totais[frota.tipo] = totais.get(frota.tipo, 0) + frota.quantidade
        return totais

    @property
    def dias_sem_login(self):
        if not self.ultimo_login:
            return "Nunca"

        agora = get_brasilia_time().replace(tzinfo=None)
        ultimo = self.ultimo_login.replace(tzinfo=None) if self.ultimo_login.tzinfo else self.ultimo_login

        dias = (agora.date() - ultimo.date()).days
        return max(0, dias)

    def __repr__(self):
        return f'<Conta {self.nome_usuario} @ {self.servidor} ({self.pais})>'