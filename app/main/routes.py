from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models import Proxy, Lobby
from app.main import main_bp
from app.main.decorators import module_required
from app.main.tasks import sync_webshare_job


@main_bp.route('/')
@main_bp.route('/index')
@login_required
def index():
    return render_template('main/index.html', user=current_user)


# ==========================================
# ROTAS DE LOBBIES
# ==========================================

@main_bp.route('/lobbies', methods=['GET'])
@login_required
@module_required
def lobbies_list():
    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()

    for lobby in lobbies:
        if hasattr(lobby, 'get_password'):
            lobby.decrypted_password = lobby.get_password()

    # Busca APENAS os proxies ativos do usuário para os modais de edição
    proxies_ativos = Proxy.query.filter_by(user_id=current_user.id, status='ATIVO').all()

    return render_template('main/lobbies_list.html', lobbies=lobbies, proxies_ativas=proxies_ativos)


@main_bp.route('/lobbies/novo', methods=['GET', 'POST'])
@login_required
@module_required
def create_lobby():
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        proxy_id = request.form.get('proxy_id', type=int)

        # 1. Validação do Limite do Plano Básico
        if len(current_user.lobbies) >= current_user.max_allowed_lobbies:
            flash(
                f"O seu plano ({current_user.plan.title()}) permite no máximo {current_user.max_allowed_lobbies} lobby. Atualize para o Plano Premium!",
                "warning"
            )
            return redirect(url_for('main.lobbies_list'))

        proxy = Proxy.query.filter_by(id=proxy_id, user_id=current_user.id).first()
        if not proxy:
            flash("Proxy selecionado não foi encontrado.", "danger")
            return redirect(url_for('main.lobbies_list'))

        # 2. Validação: O Proxy precisa estar ATIVO
        if proxy.status != 'ATIVO':
            flash("O Proxy selecionado está inativo.", "danger")
            return redirect(url_for('main.lobbies_list'))

        # 3. Validação: Vagas disponíveis no Proxy
        if proxy.available <= 0:
            flash(f"O Proxy '{proxy.address}:{proxy.port}' já está em uso.", "danger")
            return redirect(url_for('main.lobbies_list'))

        # Criação do Lobby vinculado ao Proxy
        novo_lobby = Lobby(
            nickname=nickname,
            email=email,
            proxy_id=proxy.id,
            user_id=current_user.id,
            status='ATIVO'
        )
        novo_lobby.set_password(password)

        db.session.add(novo_lobby)
        db.session.commit()

        flash("Lobby criado e vinculado ao Proxy com sucesso!", "success")
        return redirect(url_for('main.lobbies_list'))

    # GET: Filtra proxies ativos do usuário que possuem vagas disponíveis
    proxies_ativos = Proxy.query.filter_by(user_id=current_user.id, status='ATIVO').all()
    proxies_disponiveis = [p for p in proxies_ativos if p.available > 0]

    return render_template('main/create_lobby.html', vpns_disponiveis=proxies_disponiveis)


@main_bp.route('/lobbies/<int:lobby_id>/editar', methods=['POST'])
@login_required
@module_required
def edit_lobby(lobby_id):
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    nickname = request.form.get('nickname', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    proxy_id = request.form.get('proxy_id', type=int)

    if not nickname or not email:
        flash('Apelido e E-mail são obrigatórios.', 'danger')
        return redirect(url_for('main.lobbies_list'))

    # Se o Proxy foi alterado, valida a disponibilidade do novo proxy
    if proxy_id and proxy_id != lobby.proxy_id:
        novo_proxy = Proxy.query.filter_by(id=proxy_id, user_id=current_user.id).first()
        if not novo_proxy:
            flash('Proxy selecionado não foi encontrado.', 'danger')
            return redirect(url_for('main.lobbies_list'))

        if novo_proxy.status != 'ATIVO':
            flash('O Proxy selecionado está inativo.', 'danger')
            return redirect(url_for('main.lobbies_list'))

        if novo_proxy.available <= 0:
            flash('O Proxy selecionado já atingiu a capacidade máxima.', 'danger')
            return redirect(url_for('main.lobbies_list'))

        lobby.proxy_id = novo_proxy.id

    lobby.nickname = nickname
    lobby.email = email

    if password:
        lobby.set_password(password)

    db.session.commit()
    flash(f'Lobby "{lobby.nickname}" atualizado com sucesso!', 'success')
    return redirect(url_for('main.lobbies_list'))


@main_bp.route('/lobbies/<int:lobby_id>/deletar', methods=['POST'])
@login_required
@module_required
def delete_lobby(lobby_id):
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    if hasattr(lobby, 'contas') and len(lobby.contas) > 0:
        flash(f'Não é possível excluir o lobby "{lobby.nickname}" pois ele possui {len(lobby.contas)} conta(s) vinculada(s).', 'danger')
        return redirect(url_for('main.lobbies_list'))

    try:
        nickname = lobby.nickname
        db.session.delete(lobby)
        db.session.commit()
        flash(f'Lobby "{nickname}" removido com sucesso!', 'success')
    except Exception:
        db.session.rollback()
        flash('Ocorreu um erro ao tentar excluir o lobby.', 'danger')

    return redirect(url_for('main.lobbies_list'))


@main_bp.route('/lobbies/<int:lobby_id>/toggle-status', methods=['POST'])
@login_required
@module_required
def toggle_lobby_status(lobby_id):
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    if lobby.status == 'ATIVO':
        lobby.status = 'INATIVO'
        flash(f'Lobby "{lobby.nickname}" alterado para INATIVO.', 'warning')
    else:
        # Trava: Não permite ativar se o proxy estiver Inativo ou se não existir proxy
        if not lobby.proxy or lobby.proxy.status != 'ATIVO':
            flash(f'Não é possível ativar o lobby "{lobby.nickname}" pois o Proxy vinculado está inativo.', 'danger')
            return redirect(url_for('main.lobbies_list'))

        lobby.status = 'ATIVO'
        flash(f'Lobby "{lobby.nickname}" alterado para ATIVO.', 'success')

    db.session.commit()
    return redirect(url_for('main.lobbies_list'))


# ==========================================
# ROTAS DE PROXIES (WEBSHARE)
# ==========================================

@main_bp.route('/proxies', methods=['GET'])
@login_required
@module_required
def proxy_list():
    """Lista apenas os proxies ATIVOS sincronizados do usuário."""
    # ANTES: proxies = Proxy.query.filter_by(user_id=current_user.id).all()
    proxies = Proxy.query.filter_by(user_id=current_user.id, status='ATIVO').all()
    return render_template('main/proxy_list.html', proxies=proxies)


# Alias para retrocompatibilidade caso alguma rota antiga chame proxies_list
@main_bp.route('/proxies-list', methods=['GET'])
@login_required
@module_required
def proxies_list():
    return redirect(url_for('main.proxy_list'))


@main_bp.route('/proxies/sincronizar', methods=['POST', 'GET'])
@login_required
@module_required
def sync_proxies():
    """Executa a sincronização manual acionando a mesma rotina (job) do APScheduler."""
    try:
        app = current_app._get_current_object()
        sync_webshare_job(app)
        flash('Proxies sincronizados com sucesso via API do Webshare!', 'success')
    except Exception as e:
        flash(f'Erro ao sincronizar proxies: {str(e)}', 'danger')

    return redirect(url_for('main.proxy_list'))