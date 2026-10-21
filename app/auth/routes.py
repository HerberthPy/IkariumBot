from flask import render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth_bp
from app.models import User
from app import db


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('E-mail ou senha incorretos. Tente novamente.', 'danger')
            return redirect(url_for('auth.login'))

        if hasattr(user, 'is_active') and not user.is_active:
            flash('Sua conta está inativa. Entre em contato com o suporte.', 'warning')
            return redirect(url_for('auth.login'))

        login_user(user, remember=remember)
        return redirect(url_for('main.index'))

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        full_name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash("As senhas digitadas não coincidem!", "danger")
            return redirect(url_for('auth.register'))

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash('Este e-mail já está cadastrado. Faça login.', 'info')
            return redirect(url_for('auth.login'))

        # Criação de novo usuário padrão (is_admin = 0)
        user = User(
            full_name=full_name,
            email=email,
            is_admin=0
        )
        user.set_password(password)

        try:
            db.session.add(user)
            db.session.commit()
            flash('Cadastro realizado com sucesso! Faça login para acessar sua conta.', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            db.session.rollback()
            flash('Erro ao salvar os dados no banco de dados. Tente novamente.', 'danger')

    return render_template('auth/register.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()

        if not user:
            flash('Nenhum usuário foi encontrado com este e-mail.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        session['reset_email'] = user.email
        return render_template('auth/forgot_password.html', show_modal=True, email=user.email)

    return render_template('auth/forgot_password.html', show_modal=False)


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    email = session.get('reset_email')
    if not email:
        flash('Sessão expirada. Solicite a redefinição novamente.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')

    if not password or password != confirm_password:
        flash('As senhas não coincidem ou são inválidas!', 'danger')
        return render_template('auth/forgot_password.html', show_modal=True, email=email)

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Usuário não encontrado.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user.set_password(password)
    db.session.commit()

    session.pop('reset_email', None)

    flash('Sua senha foi redefinida com sucesso! Acesse com a nova senha.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('auth.login'))