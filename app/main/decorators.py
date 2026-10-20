from functools import wraps
from flask import flash, redirect, url_for, session
from flask_login import current_user


def module_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        # 1. Bloqueia o acesso se os módulos do plano não estiverem ativos
        if not current_user.is_modules_active:
            flash("O seu plano está vencido ou pendente. Regularize o pagamento para aceder a este módulo.", "warning")
            return redirect(url_for('main.index'))

        # 2. Alerta o usuário se o plano estiver prestes a vencer (sem duplicar alertas)
        if current_user.show_expiration_alert:
            dias = current_user.days_remaining
            mensagem_dias = "hoje" if dias == 0 else f"em {dias} dia(s)"
            mensagem = f"Atenção: O seu plano expira {mensagem_dias}. Renove a sua assinatura para continuar com acesso."

            # Obtém as mensagens gravadas na sessão atual de forma segura
            flashes_atuais = [msg for _, msg in session.get('_flashes', [])] if '_flashes' in session else []

            # Só dispara o flash se essa mensagem ainda não estiver na fila
            if mensagem not in flashes_atuais:
                flash(mensagem, "warning")

        return f(*args, **kwargs)

    return decorated_function