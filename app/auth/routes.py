from flask import render_template, request, redirect, url_for, flash
from app.auth import auth_bp

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
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        plan = request.form.get('plan')              # 'basic' ou 'premium'
        payment_method = request.form.get('payment_method')

        if password != confirm_password:
            flash("As senhas digitadas não coincidem!", "error")
            return redirect(url_for('auth.register'))

        # Exemplo de lógica futura:
        # 1. Salvar usuário no BD com o plano escolhido
        # 2. Redirecionar para o gateway de pagamento (Mercado Pago, Stripe, Asaas, etc.)

        flash(f"Conta criada com sucesso no plano {plan.capitalize()}! Faça login para continuar.", "success")
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        # LÓGICA FUTURA: VERIFICAR SE O EMAIL EXISTE  E ENVIAR O EMAIL COM TOKEN DE RECUPERAÇÃO

        flash("Se o e-mail estiver cadastrado, você receberá um link com as instruções em breve.", "info")
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')