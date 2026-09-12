from flask import render_template
from flask_login import login_required, current_user
from app.main import main_bp
from app.models import IkariamLobby

@main_bp.route('/')
@login_required
def index():
    return render_template('main/index.html')

@main_bp.route('/lobbies')
@login_required
def list_lobbies():
    lobbies = current_user.lobbies
    return render_template('main/lobbies.html', lobbies=lobbies)
