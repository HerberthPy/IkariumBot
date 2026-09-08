from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

# Instancia as extensões sem vinculá-las diretamente a um app ainda
db = SQLAlchemy()
login_manager = LoginManager()

def create_app(config_class=Config):
    # Cria a instância principal do Flask
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicializa as extensões associando-as ao app
    db.init_app(app)
    login_manager.init_app(app)

    # Configurações do Flask-login
    login_manager.login_view = 'auth.login' # Rota para onde redireciona usuários não logados
    login_manager.login_message = 'Por favor, faça login para acessar a página.'
    login_manager.login_message_category = 'Warning'

    # Registro dos Blueprints (módulos de rotas)
    from app.auth.routes import auth_bp
    from app.main.routes import main_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)

    # Importa os modelos para o SQLAlchemy reconhecer a estrutura das tabelas
    from app import models

    # Cria as tabelas do banco de dados automaticamente se não existirem
    with app.app_context():
        db.create_all()

    # Registra handlers de erro globais
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('main/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('main/500.html'), 500

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models import User  # Import local evita problemas de importação circular
    return User.query.get(int(user_id))