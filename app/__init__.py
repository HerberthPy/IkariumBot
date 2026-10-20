from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_apscheduler import APScheduler
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
scheduler = APScheduler()


def create_app(config_class=Config):
    # Cria a instância principal do Flask
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. Inicializando extensões na app
    db.init_app(app)
    login_manager.init_app(app)

    # Configuração do Agendador APScheduler
    scheduler.init_app(app)
    scheduler.start()

    # Define para onde redirecionar utilizadores não autenticados
    login_manager.login_view = 'auth.login'
    login_manager.login_message = ''
    login_manager.login_message_category = 'warning'

    # 2. Carregador de utilizador obrigatório para o Flask-Login
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Registro dos Blueprints (módulos de rotas)
    from app.auth.routes import auth_bp
    from app.main.routes import main_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)

    with app.app_context():
        from app.models import User, Proxy, Lobby
        db.create_all()

        # Registro do Job de Sincronização Automática (A cada 10 minutos = 600 segundos)
        from app.main.tasks import sync_webshare_job
        if not scheduler.get_job('job_sync_proxies'):
            scheduler.add_job(
                id='job_sync_proxies',
                func=sync_webshare_job,
                trigger='interval',
                seconds=600,  # 60 segundos x 10 minutos = 600 segundos
                args=[app]
            )

    # Registra handlers de erro globais
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('main/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('main/500.html'), 500

    return app