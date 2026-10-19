from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import VPN, Lobby
from app import db
from app.main import main_bp
from app.main.decorators import module_required

@main_bp.route('/')
@main_bp.route('/index')
@login_required
def index():
    return render_template('main/index.html', user=current_user)

# Rota da lista de Lobbies
@main_bp.route('/lobbies', methods=['GET'])
@login_required
@module_required
def lobbies_list():
    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()
    return render_template('main/lobbies_list.html', lobbies=lobbies)

# Rota de cadastro dos lobbies
@main_bp.route('/lobbies/novo', methods=['GET', 'POST'])
@login_required
@module_required
def create_lobby():
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        email = request.form.get('email')
        password = request.form.get('password')
        country = request.form.get('country')
        vpn_id = request.form.get('vpn_id')

        # 1. Validação do Limite do Plano Básico (Apenas 1 Lobby)
        if len(current_user.lobbies) >= current_user.max_allowed_lobbies:
            flash(f"O seu plano ({current_user.plan.title()}) permite no máximo {current_user.max_allowed_lobbies} lobby. Atualize para o Plano Premium!", "warning")
            return redirect(url_for('main.lobbies_list'))

        vpn = VPN.query.filter_by(id=vpn_id, user_id=current_user.id).first()
        if not vpn:
            flash("VPN selecionada não foi encontrada.", "danger")
            return redirect(url_for('main.lobbies_list'))

        # 2. Validação: A VPN precisa estar ATIVA
        if vpn.status != 'ATIVA':
            flash(f"A VPN '{vpn.nickname}' está inativa e não pode ser vinculada.", "danger")
            return redirect(url_for('main.lobbies_list'))

        # 3. Validação: Capacidade máxima da VPN
        if vpn.available <= 0:
            flash(f"A VPN '{vpn.nickname}' atingiu a capacidade máxima ({vpn.capacity} lobbies).", "danger")
            return redirect(url_for('main.lobbies_list'))

        # Criação do Lobby
        novo_lobby = Lobby(
            nickname=nickname,
            email=email,
            country=country,
            vpn_id=vpn.id,
            user_id=current_user.id,
            status='ATIVA'
        )
        novo_lobby.set_password(password)

        db.session.add(novo_lobby)
        db.session.commit()

        flash("Lobby criado e vinculado com sucesso!", "success")
        return redirect(url_for('main.lobbies_list'))

    vpns = VPN.query.filter_by(user_id=current_user.id, status='ATIVA').all()
    return render_template('main/create_lobby.html', vpns=vpns)

# Rota da lista de VPNs
@main_bp.route('/vpns', methods=['GET'])
@login_required
@module_required
def vpn_list():
    vpns = VPN.query.filter_by(user_id=current_user.id).all()
    return render_template('main/vpn_list.html', vpns=vpns)

# Rota criar VPN
@main_bp.route('/vpns/nova', methods=['GET', 'POST'])
@login_required
@module_required
def create_vpn():
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        status = request.form.get('status', 'ATIVA')

        capacity = request.form.get('capacity', type=int) or 10

        # Verifica se esta VPN já existe para o usuário logado
        existing_vpn = VPN.query.filter_by(email=email, user_id=current_user.id).first()

        if existing_vpn:
            flash('Você já cadastrou uma VPN com este e-mail. Verifique os dados.', 'warning')
            return redirect(url_for('main.vpn_list'))

        new_vpn = VPN(
            nickname=nickname,
            email=email,
            capacity=capacity,
            status=status,
            user_id=current_user.id
        )

        new_vpn.set_password(password)
        db.session.add(new_vpn)
        db.session.commit()

        flash('VPN cadastrada com sucesso!', 'success')
        return redirect(url_for('main.vpn_list'))

    return render_template('main/create_vpn.html')

@main_bp.route('/vpns/<int:vpn_id>/deletar', methods=['POST'])
@login_required
@module_required
def delete_vpn(vpn_id):
    vpn = VPN.query.filter_by(id=vpn_id, user_id=current_user.id).first_or_404()

    # Validação: Impede exclusão se houver lobbies vinculados
    if vpn.used > 0:
        flash(f'Não é possível excluir a VPN "{vpn.nickname}" pois ela possui {vpn.used} lobby(ies) vinculado(s).', 'danger')
        return redirect(url_for('main.vpn_list'))

    try:
        db.session.delete(vpn)
        db.session.commit()
        flash('VPN removida com sucesso!', 'success')
    except Exception:
        db.session.rollback()
        flash('Ocorreu um erro ao tentar excluir a VPN.', 'danger')

    return redirect(url_for('main.vpn_list'))


@main_bp.route('/vpns/<int:vpn_id>/editar', methods=['POST'])
@login_required
@module_required
def edit_vpn(vpn_id):
    vpn = VPN.query.filter_by(id=vpn_id, user_id=current_user.id).first_or_404()

    new_capacity = request.form.get('capacity', type=int)

    if new_capacity is None or new_capacity < vpn.used:
        flash(
            f'Não é possível reduzir a capacidade para {new_capacity}. '
            f'Existem {vpn.used} lobby(s) usando esta VPN.',
            'danger'
        )
        return redirect(url_for('main.vpn_list'))

    vpn.nickname = request.form.get('nickname', '').strip()

    password = request.form.get('password', '').strip()
    if password:
        vpn.set_password(password)

    vpn.capacity = new_capacity

    db.session.commit()
    flash(f'VPN "{vpn.nickname}" atualizada com sucesso!', 'success')
    return redirect(url_for('main.vpn_list'))

@main_bp.route('/vpns/<int:vpn_id>/toggle-status', methods=['POST'])
@login_required
@module_required
def toggle_vpn_status(vpn_id):
    vpn = VPN.query.filter_by(id=vpn_id, user_id=current_user.id).first_or_404()

    # Alterna o status
    if vpn.status == 'ATIVA':
        vpn.status = 'INATIVA'
        # Inativa em cascata todos os lobbies vinculados a esta VPN
        for lobby in vpn.lobbies:
            lobby.status = 'INATIVA'
        flash(f'VPN "{vpn.nickname}" inativada. {vpn.used} lobby(ies) vinculado(s) também foram inativados.', 'warning')
    else:
        vpn.status = 'ATIVA'
        flash(f'Status da VPN "{vpn.nickname}" alterado para ATIVA.', 'success')

    db.session.commit()
    return redirect(url_for('main.vpn_list'))