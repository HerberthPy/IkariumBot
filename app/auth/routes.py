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
        email = request.form.get('email', '').strip().lower()
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
        full_name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        plan = request.form.get('plan', 'basico')  # 'basico' ou 'premium'
        plan_cycle = request.form.get('plan_cycle', 'mensal')  # 'mensal' ou 'anual'
        payment_method = request.form.get('payment_method')
        terms = request.form.get('terms')

        # Validações dos campos
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
                # Atualiza os dados da conta pendente
                user.full_name = full_name
                user.payment_method = payment_method
                user.set_password(password)
                # Recalcula a data de expiração e o ciclo do plano no fuso de Brasília
                user.activate_plan(plan_type=plan, plan_cycle=plan_cycle)
        else:
            # Cria a nova instância do Usuário
            user = User(
                full_name=full_name,
                email=email,
                payment_method=payment_method,
                is_active=True,  # Permite acesso inicial / controle por status
                payment_status='pago'  # Marca como pago para liberar os módulos
            )
            user.set_password(password)
            # Define o plano, ciclo e calcula a expiração de 30 ou 365 dias
            user.activate_plan(plan_type=plan, plan_cycle=plan_cycle)

            db.session.add(user)

        try:
            db.session.commit()
            flash('Cadastro realizado com sucesso! Faça login para acessar sua conta.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao salvar os dados no banco de dados. Tente novamente.', 'danger')

    return render_template('auth/register.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        # LÓGICA FUTURA: VERIFICAR SE O EMAIL EXISTE E ENVIAR O EMAIL COM TOKEN DE RECUPERAÇÃO

        flash("Se o e-mail estiver cadastrado, você receberá um link com as instruções em breve.", "info")
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('auth.login'))