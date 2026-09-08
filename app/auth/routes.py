from flask import render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from app.auth import auth_bp
from app.models import User
from app import db

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Se o usuário já estiver logado, manda direto para a página principal
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    # Verifica se recebeu formulário da página e realiza autenticação do usuario/senha hash
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Busca o usuário pelo nome cadastrado
        user = User.query.filter_by(username=username).first()

        # Valida a existência do usuário e verifica a senha cryptografada (hash)
        if user and user.check_password(password):
            login_user(user)  # Inicia a sessão com Flask-Login
            flash('Login realizado com sucesso!', 'success')

            # Captura a URL original solicitada
            next_page = request.args.get('next')

            # Validação de segurança: garante que o redirecionamento é relativo ao seu dominio
            if not next_page or urlparse(next_page).netloc != '':
                next_page = url_for('main.index')

            return redirect(next_page)
        else:
            flash('Usuário ou senha incorretos.', 'danger')

    # Se nenhuma das verificações forem válidas, direciona para a página de login
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Se o usuário já estiver logado, manda direto para a página principal
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    # Se receber fomulário da página, realiza o cadastro e direciona para página de login
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

    # Se nenhuma das verificações for válida, direciona para página de cadastro.
    return render_template('auth/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'infor')
    return redirect(url_for('auth.login'))