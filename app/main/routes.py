from flask import render_template
from app.main import main_bp

@main_bp.route('/')
@main_bp.route('/index')
def index():
    return render_template('main/index.html')

# Rota da lista de VPNs
@main_bp.route('/vpns', methods=['GET'])
def vpn_list():
    # Exemplo mock de VPNs cadastradas (depois virá do BD)
    vpns = [
        # {"id": 1, "apelido": "VPN Brasil", "email": "177.12.34.56", "senha": "Conectado", "status": "ATIVA"},
        # {"id": 2, "apelido": "VPN EUA - Miami", "email": "104.28.19.82", "senha": "Conectado", "status": "INATIVA"}
    ]
    return render_template('main/vpn_list.html', vpns=vpns)

# Rota da lista de Lobbies
@main_bp.route('/lobbies', methods=['GET'])
def lobbies():
    # Exemplo mock de Lobbies cadastrados (depois virá do BD)
    lobbies_list = [
        {"id": 1, "nome": "Lobby Principal - Conta 1", "servidor": "s150-br", "status": "Rodando"},
        {"id": 2, "nome": "Lobby Farm - Conta 2", "servidor": "s151-br", "status": "Pausado"}
    ]
    return render_template('main/lobbies.html', lobbies=lobbies_list)