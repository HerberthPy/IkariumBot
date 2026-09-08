from flask import render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth_bp
from app.models import User
from app import db

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    return render_template('')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        # 1. Verifica se usuário ou e-mail já existem no banco
        user_exists = User.query.filter((User.username == username) | (User.email == email)).first()
        if user_exists:
            flash('Usuário ou E-mail já cadastrados!', 'danger')
            return redirect(url_for('auth.register'))

        # 2. Cria o novo usuário e gera o hash da senha
        new_user = User(username=username, email=email)
        new_user.set_password(password)

        # 3. Salva no banco de dados
        db.session.add(new_user)
        db.session.commit()

        flash('Conta criada com sucesso! Faça seu login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))