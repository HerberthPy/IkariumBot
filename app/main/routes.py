from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
# from app import db
from app.main import main_bp
# from app.models import IkariamLobby, now_utc

@main_bp.route('/')
# @login_required
def index():
    return render_template('auth/login.html')

# @main_bp.route('/lobbies')
# @login_required
# def list_lobbies():
#     lobbies = current_user.lobbies
#     return render_template('main/lobbies.html', lobbies=lobbies)
#
# @main_bp.route('/lobbies/new', methods=['GET', 'POST'])
# @login_required
# def create_lobby():
#     if request.method == 'POST':
#         nickname = request.form.get('nickname')
#         email = request.form.get('email-lobby')
#         lobby_password = request.form.get('lobby_password')
#         vpn_user = request.form.get('vpn_email')
#         vpn_pass = request.form.get('vpn_password')
#         vpn_country = request.form.get('country')
#
#         # Cria a instância do novo lobby vinculada ao usuário logado
#         novo_lobby = IkariamLobby(
#             nickname=nickname,
#             email=email,
#             lobby_password=lobby_password,  # O @setter do Fernet criptografa aqui
#             vpn_user=vpn_user,
#             vpn_password=vpn_pass,  # O @setter do Fernet criptografa aqui
#             vpn_country=vpn_country,
#             user_id=current_user.id,
#             active=0,
#             is_running=0,
#             last_update=now_utc(),
#             created_at=now_utc()
#         )
#
#         db.session.add(novo_lobby)
#         db.session.commit()
#
#         flash('Lobby cadastrado com sucesso!', 'success')
#         return redirect(url_for('main.list_lobbies'))
#
#     return render_template('main/create_lobby.html')