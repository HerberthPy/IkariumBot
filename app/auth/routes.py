from flask import render_template_string, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User
from app.auth import auth_bp

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    return render_template_string("<h1>Página de Login</h1><p>Em breve configuramos o HTML completo.</p>")

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    return render_template_string("<h1>Página de Cadastro</h1>")

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))