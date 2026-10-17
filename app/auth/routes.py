from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth_bp
from app.models import User
from app import db

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Se o usuário já estiver logado, redireciona para o painel/dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        # 1. Busca o usuário pelo e-mail
        user = User.query.filter_by(email=email).first()

        # 2. Verifica se o usuário existe e se a senha está correta
        if not user or not user.check_password(password):
            flash('E-mail ou senha incorretos. Tente novamente.', 'danger')
            return redirect(url_for('auth.login'))

        # 3. Verifica se a conta está ativa (pagamento aprovado)
        if not user.is_active:
            flash('Sua conta ainda não está ativa. Aguardando confirmação de pagamento.', 'warning')
            return redirect(url_for('auth.login'))

        # 4. Realiza o login na sessão
        login_user(user, remember=remember)

        return redirect(url_for('main.index'))

    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        print("--- FORMULÁRIO RECEBIDO ---")
        full_name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        plan = request.form.get('plan')              # 'basic' ou 'premium'
        payment_method = request.form.get('payment_method')
        terms = request.form.get('terms')
        print(full_name, email, password, confirm_password, plan, payment_method, terms)

        if password != confirm_password:
            flash("As senhas digitadas não coincidem!", "danger")
            return redirect(url_for('auth.register'))

        if not terms:
            flash('Você precisa aceitar os Termos de Uso.', 'warning')
            return redirect(url_for('auth.register'))

        user = User.query.filter_by(email=email).first()

        if user:
            if user.is_active:
                flash('Este e-mail já possui uma conta ativa. Faça login.', 'info')
                return redirect(url_for('auth.login'))
            else:
                # Atualiza dados se a conta ainda não foi ativada/paga
                user.full_name = full_name
                user.plan = plan
                user.payment_method = payment_method
                user.set_password(password)
        else:
            user = User(
                full_name=full_name,
                email=email,
                plan=plan,
                payment_method=payment_method,
                is_active=False,
                payment_status='pending'
            )
            user.set_password(password)
            db.session.add(user)

        # O try/except PRECISA estar indentado dentro do if request.method == 'POST'
        try:
            db.session.commit()
            flash('Pré-cadastro realizado! Realize o pagamento para ativar a conta.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao salvar no banco de dados.', 'danger')

    return render_template('auth/register.html')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        # LÓGICA FUTURA: VERIFICAR SE O EMAIL EXISTE  E ENVIAR O EMAIL COM TOKEN DE RECUPERAÇÃO

        flash("Se o e-mail estiver cadastrado, você receberá um link com as instruções em breve.", "info")
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('auth.login'))

