from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

def module_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        # Se o plano estiver expirado ou pendente, bloqueia o acesso aos módulos
        if current_user.is_plan_expired or current_user.payment_status != 'pago':
            flash("O seu plano está vencido. Regularize o pagamento para aceder a este módulo.", "warning")
            return redirect(url_for('main.index'))

        return f(*args, **kwargs)

    return decorated_function