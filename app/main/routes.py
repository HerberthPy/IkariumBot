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
        {"id": 1, "apelido": "Principal Premium", "email": "herberthdesign@gmail.com", "senha": "Isabelly22@", "status": "ATIVA", "capacidade": "10", "disponivel": "5"},
        {"id": 2, "apelido": "Secundaria", "email": "secundaria@gmail.com", "senha": "isa123", "status": "INATIVA", "capacidade": "10", "disponivel": "5"}
    ]
    return render_template('main/vpn_list.html', vpns=vpns)

# Rota da lista de Lobbies
@main_bp.route('/lobbies', methods=['GET'])
def lobbies_list():
    # Exemplo mock de Lobbies cadastrados (depois virá do BD)
    lobbies = [
        {"id": 1, "apelido": "Principal", "email": "herberthdesign@gmail.com", "senha": "Isabelly22@", "vpn": "Principal Premium", "contas": "5", "status": "ATIVO"},
        {"id": 2, "apelido": "Produtor", "email": "herberthdesign@gmail.com", "senha": "Isabelly22@", "vpn": "Principal Premium", "contas": "5", "status": "INATIVO"}
    ]
    return render_template('main/lobbies_list.html', lobbies=lobbies)