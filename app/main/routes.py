from flask import render_template_string
from app.main import main_bp

@main_bp.route('/')
def index():
    return render_template_string("<h1>Servidor Flask Funcionado!</h1><p>Acesse <a href='/auth/login'>/auth/login</a></p>")