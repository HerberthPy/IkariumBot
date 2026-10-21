from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user


def user_active_required(f):
    """Garante que apenas usuários autenticados e com a conta ATIVA

    possam acessar módulos do sistema.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        if not current_user.is_active:
            flash("Sua conta está inativa. Entre em contato com o administrador do sistema.", "danger")
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """Garante que apenas administradores (is_admin=1) e ativos

    possam acessar painéis de gestão.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        if current_user.is_admin != 1:
            flash("Acesso negado! Você não tem permissão de administrador.", "danger")
            return redirect(url_for('main.index'))

        return f(*args, **kwargs)

    return decorated_function