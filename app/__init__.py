from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_apscheduler import APScheduler
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
scheduler = APScheduler()


def restore_active_bots(app):
    """Verifica e restaura as instâncias do Playwright para os Lobbies

    que estavam marcados como ATIVOS antes do servidor cair/reiniciar.
    """
    with app.app_context():
        from app.models import Lobby
        from app.bot.runner import BotManager

        # Busca todos os lobbies que estavam salvos como ATIVO no banco
        lobbies_ativos = Lobby.query.filter_by(status='ATIVO').all()

        if lobbies_ativos:
            print(f"[Automação Auto-Start] Restaurando {len(lobbies_ativos)} lobby(ies) ativo(s)...")
            for lobby in lobbies_ativos:
                if lobby.proxy and lobby.proxy.status == 'ATIVO':
                    if not BotManager.is_running(lobby.id):
                        BotManager.start_lobby(lobby.id, app)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    scheduler.init_app(app)
    scheduler.start()

    login_manager.login_view = 'auth.login'
    login_manager.login_message = ''
    login_manager.login_message_category = 'warning'

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.auth.routes import auth_bp
    from app.main.routes import main_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)

    with app.app_context():
        from app.models import User, Proxy, Lobby
        db.create_all()

        # Job do APScheduler (a cada 30 min)
        from app.main.tasks import sync_webshare_job
        if not scheduler.get_job('job_sync_proxies'):
            scheduler.add_job(
                id='job_sync_proxies',
                func=sync_webshare_job,
                trigger='interval',
                seconds=1800,
                args=[app],
                replace_existing=True
            )

        # RESTAURAÇÃO AUTOMÁTICA DAS AUTOMAÇÕES AO INICIAR O SERVIDOR
        restore_active_bots(app)

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('main/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('main/500.html'), 500

    return app