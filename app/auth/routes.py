from flask import render_template, request, redirect, url_for, flash
from app.auth import auth_bp
from app.models import User
from app import db

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember_me') else False

        # Exemplo simples de validação (Substitua depois pela consulta ao BD em models.py)
        if email == "admin@admin.com" and password == "123456":
            flash("Login realizado com sucesso!", "success")
            return redirect(url_for('main.index'))  # Redireciona para a página principal
        else:
            flash("E-mail ou senha incorretos. Tente novamente.", "error")
            return redirect(url_for('auth.login'))

    # Se for requisição GET, apenas exibe a página de login
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        plan = request.form.get('plan')              # 'basic' ou 'premium'
        payment_method = request.form.get('payment_method')
        terms = request.form.get('terms')

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

        try:
            db.session.commit()
            flash('Pré-cadastro realizado! Realize o pagamento para ativar a conta.', 'success')
            # return redirect(url_for('auth.payment_checkout', user_id=user.id))
            return redirect(url_for('auth.login'))  # ou para a tela de checkout
        except Exception as e:
            db.session.rollback()
            flash('Erro ao salvar no banco de dados.', 'danger')

        # TODO: Gerar a cobrança/PIX no Gateway de Pagamento
        # Exemplo: checkout_url = gateway.create_payment(user.id, plan, payment_method)

    return render_template('auth/register.html')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        # LÓGICA FUTURA: VERIFICAR SE O EMAIL EXISTE  E ENVIAR O EMAIL COM TOKEN DE RECUPERAÇÃO

        flash("Se o e-mail estiver cadastrado, você receberá um link com as instruções em breve.", "info")
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')
