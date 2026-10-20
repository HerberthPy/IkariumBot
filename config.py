import os

# Descobre o diretório raiz do projeto de forma dinâmica
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Chave de segurança para assinar sessões e cookies do Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or '3c7b8876c0823e6d4d4a8dc29f76da1884a982074cca7b55acb79cc7ffaf739e'

    # Chave Fernet para criptografia de senhas
    FERNET_KEY = os.environ.get('FERNET_KEY') or 'GeXkcjuM3OkR4MvZTGidZmqOkG7ZSjC31aXF-BdMGTY='

    # Token da API REST v2 do Webshare
    WEBSHARE_API_KEY = os.environ.get('WEBSHARE_API_KEY') or 'vggxva3hcmbksvuqv78dkce99r4d62ra11sytxo4'

    # Caminho do Banco de Dados SQLite
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f"sqlite:///{os.path.join(BASE_DIR, 'app.db').replace('\\', '/')}"

    # Desativa rastreamento pesado de modificações para otimizar memória
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Configuração do Flask-APScheduler (Desativa a API REST do scheduler por segurança)
    SCHEDULER_API_ENABLED = False