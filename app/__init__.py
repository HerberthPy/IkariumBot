from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

# Instâncias dos plugins (precisam ficar no topo para evitar import circular)
db = SQLAlchemy()
login_manager = LoginManager()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # IMPORT LOCAL: evita import circular com o pacote app.bot
    from app.bot.utils.worlds import get_world_name
    app.jinja_env.filters['nome_mundo'] = get_world_name

    # --- FILTRO PARA FORMATAR O OURO TOTAL (REMOVE OS 2 ÚLTIMOS DÍGITOS E COLOCA PONTO) ---
    def formatar_ouro_filtro(raw_gold):
        if raw_gold is None:
            return '0'

        try:
            str_val = str(raw_gold).strip()
            digits = "".join(c for c in str_val if c.isdigit())
            if not digits:
                return '0'

            # Remove os 2 últimos dígitos (centavos/decimais)
            int_part = int(digits[:-2]) if len(digits) > 2 else 0
            if int_part == 0:
                return '0'

            return f"{int_part:,}".replace(",", ".")
        except (ValueError, TypeError):
            return str(raw_gold)

    app.jinja_env.filters['format_ouro'] = formatar_ouro_filtro

    # ---------------------------------------------------------------------------------------

    # --- FILTRO PARA FORMATAR O RENDIMENTO (REMOVE OS 2 ÚLTIMOS DÍGITOS E /H) ---
    def formatar_rendimento_filtro(raw_rendimento):
        if not raw_rendimento:
            return "+0/h"

        try:
            str_val = str(raw_rendimento).strip()
            sinal = "-" if str_val.startswith("-") else "+"
            digits = "".join(c for c in str_val if c.isdigit())
            if not digits:
                return "+0/h"

            # Remove os 2 últimos dígitos (centavos/decimais)
            int_part = int(digits[:-2]) if len(digits) > 2 else 0
            if int_part == 0:
                return "+0/h"

            formatted_num = f"{int_part:,}".replace(",", ".")
            return f"{sinal}{formatted_num}/h"
        except (ValueError, TypeError):
            return "+0/h"

    app.jinja_env.filters['format_rendimento'] = formatar_rendimento_filtro

    # ---------------------------------------------------------------------------------------

    # --- FILTRO SEGURO PARA O IMPÉRIO ---
    def formatar_ouro_sistema_seguro(raw_val):
        if raw_val is None:
            return '0'
        try:
            str_val = str(raw_val).strip()
            digits = "".join(c for c in str_val if c.isdigit())
            if not digits:
                return '0'
            int_val = int(digits[:-2]) if len(digits) > 2 else int(digits)
            if int_val == 0:
                return '0'
            return f"{int_val:,}".replace(",", ".")
        except Exception:
            return '0'

    app.jinja_env.filters['format_ouro_sistema'] = formatar_ouro_sistema_seguro
    # ---------------------------------------------------------------------------------------

    db.init_app(app)
    login_manager.init_app(app)

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

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('main/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('main/500.html'), 500

    return app