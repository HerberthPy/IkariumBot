from flask import Flask, render_template
from config import Config

def create_app(config_class=Config):
    # Cria a instância principal do Flask
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Registro dos Blueprints (módulos de rotas)
    from app.auth.routes import auth_bp
    from app.main.routes import main_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)

    # Registra handlers de erro globais
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('main/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('main/500.html'), 500

    return app