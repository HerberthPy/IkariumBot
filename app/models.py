from flask import current_app
from cryptography.fernet import Fernet
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
from datetime import datetime, timezone

def now_utc():
    return datetime.now(timezone.utc)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    # Relacionamento para acessar os lobbies a partir do objeto User (user.lobbies) 1 usuário para N lobbies
    lobbies = db.relationship("IkariamLobby", backref="user", lazy=True)

    def set_password(self, password):
        """Gera o hash seguro a partir da senha em texto puro."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica se a senha informada bate com o hash salvo."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class IkariamLobby(db.Model):
    __tablename__ = 'ikariamlobby'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nickname = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column('lobby_password', db.String(256), nullable=False)

    vpn_user = db.Column(db.String(120), nullable=False)
    vpn_pass = db.Column('vpn_password', db.String(256), nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    active = db.Column(db.Boolean, default=False, nullable=False)
    is_running = db.Column(db.Boolean, default=False, nullable=False)
    last_update = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)

    # Função auxiliar para pegar a instância do Fernet
    @staticmethod
    def _get_cipher():
        key = current_app.config['FERNET_KEY']
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)

    @property
    def lobby_password(self):
        if not self.password:
            return ""
        cipher = self._get_cipher()
        return cipher.decrypt(self.password.encode()).decode()

    @lobby_password.setter
    def lobby_password(self, raw_password):
        cipher = self._get_cipher()
        self.password = cipher.encrypt(raw_password.encode()).decode()

    @property
    def vpn_password(self):
        if not self.vpn_pass:
            return ""
        cipher = self._get_cipher()
        return cipher.decrypt(self.vpn_pass.encode()).decode()

    @vpn_password.setter
    def vpn_password(self, raw_password):
        cipher = self._get_cipher()
        self.vpn_pass = cipher.encrypt(raw_password.encode()).decode()

    def __repr__(self):
        return f'<IkariamLobby {self.nickname}>'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))