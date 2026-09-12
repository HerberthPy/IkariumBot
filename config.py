import os

# Descobre o diretório raiz do projeto de forma dinâmica
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    #Chave de segurança para assinar sessões e cookies
    SECRET_KEY = os.environ.get('SECRET_KEY') or '3c7b8876c0823e6d4d4a8dc29f76da1884a982074cca7b55acb79cc7ffaf739e'

    FERNET_KEY = os.environ.get('FERNET_KEY') or 'GeXkcjuM3OkR4MvZTGidZmqOkG7ZSjC31aXF-BdMGTY='

    # Caminho do Banco de Dados SQLite (Salvo na pasta do projeto)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(BASE_DIR, 'app.db')

    # Desativa rastreamento pesado de modificações para otimizar memória
    SQLALCHEMY_TRACK_MODIFICATIONS = False