from flask import render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Proxy, Lobby, User
from app.main import main_bp
from app.main.tasks import sync_webshare_job
from app.main.decorators import admin_required, user_active_required
from app.bot import BotManager


@main_bp.route('/')
@main_bp.route('/index')
@login_required
@user_active_required
def index():
    return render_template('main/index.html', user=current_user)


# ==========================================
# ROTAS ADMINISTRATIVAS
# ==========================================

@main_bp.route('/admin/proxies', methods=['GET'])
@login_required
@admin_required
def admin_proxies():
    """Painel do Admin: Lista todas as proxies do pool (livres e atribuídas)."""
    proxies = Proxy.query.all()
    users = User.query.filter_by(is_admin=0, is_active=True).all()
    return render_template('main/admin_proxies.html', proxies=proxies, users=users)


@main_bp.route('/admin/proxies/<int:proxy_id>/assign', methods=['POST'])
@login_required
@admin_required
def assign_proxy(proxy_id):
    """Admin atribui ou altera o usuário dono da proxy."""
    proxy = Proxy.query.get_or_404(proxy_id)
    user_id = request.form.get('user_id', type=int)

    if user_id:
        user = User.query.get(user_id)
        if not user:
            flash('Usuário selecionado não encontrado.', 'danger')
            return redirect(url_for('main.admin_proxies'))

        proxy.user_id = user.id
        flash(f'Proxy #{proxy.id} atribuída com sucesso ao usuário {user.full_name}!', 'success')
    else:
        proxy.user_id = None
        flash(f'Proxy #{proxy.id} devolvida ao Pool Global.', 'info')

    db.session.commit()
    return redirect(url_for('main.admin_proxies'))


@main_bp.route('/admin/proxies/<int:proxy_id>/unassign', methods=['POST'])
@login_required
@admin_required
def unassign_proxy(proxy_id):
    """Admin desvincula a proxy do usuário e devolve ao Pool Global."""
    proxy = Proxy.query.get_or_404(proxy_id)
    proxy.user_id = None
    db.session.commit()

    flash(f'Proxy #{proxy.id} devolvida ao Pool Global com sucesso.', 'info')
    return redirect(url_for('main.admin_proxies'))


@main_bp.route('/admin/proxies/sincronizar', methods=['POST', 'GET'])
@login_required
@admin_required
def sync_proxies():
    """Sincroniza manualmente as proxies do Webshare no Pool Global."""
    try:
        app = current_app._get_current_object()
        sync_webshare_job(app)
        flash('Pool de Proxies sincronizado com sucesso via API do Webshare!', 'success')
    except Exception as e:
        flash(f'Erro ao sincronizar proxies: {str(e)}', 'danger')

    return redirect(url_for('main.admin_proxies'))


@main_bp.route('/admin/users', methods=['GET'])
@login_required
@admin_required
def admin_users():
    """Painel do Admin: Lista todos os usuários e permite alteração de status."""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('main/admin_users.html', users=users)


@main_bp.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    """Admin ativa ou desativa a conta de um usuário."""
    if user_id == current_user.id:
        flash('Você não pode desativar sua própria conta de administrador.', 'warning')
        return redirect(url_for('main.admin_users'))

    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()

    status_str = "ativado" if user.is_active else "desativado"
    flash(f'Usuário {user.full_name} foi {status_str} com sucesso!', 'success')
    return redirect(url_for('main.admin_users'))


# ==========================================
# ROTAS DO USUÁRIO - VISÃO DE PROXIES
# ==========================================

@main_bp.route('/user/proxies', methods=['GET'])
@login_required
@user_active_required
def user_proxies():
    """Visão do Usuário: Lista apenas as proxies atribuídas a ele sem expor credenciais."""
    proxies = Proxy.query.filter_by(user_id=current_user.id, status='ATIVO').all()
    return render_template('main/user_proxies.html', proxies=proxies)


# ==========================================
# ROTAS DO USUÁRIO - GERENCIAMENTO DE LOBBIES E AUTOMAÇÃO
# ==========================================

@main_bp.route('/lobbies', methods=['GET'])
@login_required
@user_active_required
def lobbies_list():
    """Lista todos os lobbies pertencentes ao usuário logado."""
    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()

    for lobby in lobbies:
        if hasattr(lobby, 'get_password'):
            lobby.decrypted_password = lobby.get_password()
        # Marca dinamicamente no objeto se a instância Playwright do lobby está rodando
        lobby.is_running = BotManager.is_running(lobby.id)

    user_proxies_list = Proxy.query.filter_by(user_id=current_user.id, status='ATIVO').all()

    return render_template('main/lobbies_list.html', lobbies=lobbies, user_proxies=user_proxies_list)


@main_bp.route('/lobbies/novo', methods=['GET', 'POST'])
@login_required
@user_active_required
def create_lobby():
    """Cadastro de um novo lobby com validação de limite de proxies."""
    user_proxies_list = Proxy.query.filter_by(user_id=current_user.id, status='ATIVO').all()
    proxies_livres = [p for p in user_proxies_list if not p.is_in_use]

    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        proxy_id = request.form.get('proxy_id', type=int)

        if not current_user.can_create_lobby:
            flash(
                "Você atingiu o limite de Lobbies referente às suas proxies atribuídas.",
                "warning"
            )
            return redirect(url_for('main.lobbies_list'))

        proxy = Proxy.query.filter_by(id=proxy_id, user_id=current_user.id, status='ATIVO').first()
        if not proxy:
            flash("Proxy selecionada inválida ou não pertence à sua conta.", "danger")
            return redirect(url_for('main.lobbies_list'))

        if proxy.is_in_use:
            flash("A Proxy selecionada já está vinculada a outro lobby.", "danger")
            return redirect(url_for('main.lobbies_list'))

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

        # Inicia a navegação imediatamente para o lobby recém-criado
        app = current_app._get_current_object()
        BotManager.start_lobby(novo_lobby.id, app)

        flash("Lobby cadastrado e automação iniciada com sucesso!", "success")
        return redirect(url_for('main.lobbies_list'))

    return render_template('main/create_lobby.html', user_proxies=proxies_livres)


@main_bp.route('/lobbies/<int:lobby_id>/editar', methods=['POST'])
@login_required
@user_active_required
def edit_lobby(lobby_id):
    """Edição de credenciais ou alteração de proxy de um lobby existente."""
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    nickname = request.form.get('nickname', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    proxy_id = request.form.get('proxy_id', type=int)

    if not nickname or not email:
        flash('Apelido e E-mail são obrigatórios.', 'danger')
        return redirect(url_for('main.lobbies_list'))

    if proxy_id and proxy_id != lobby.proxy_id:
        novo_proxy = Proxy.query.filter_by(id=proxy_id, user_id=current_user.id, status='ATIVO').first()
        if not novo_proxy:
            flash('Proxy selecionada não encontrada ou indisponível.', 'danger')
            return redirect(url_for('main.lobbies_list'))

        if novo_proxy.is_in_use:
            flash('A nova Proxy selecionada já está em uso por outro lobby.', 'danger')
            return redirect(url_for('main.lobbies_list'))

        # Se alterou o proxy de um lobby que rodava, encerra a instância antiga
        BotManager.stop_lobby(lobby.id)
        lobby.proxy_id = novo_proxy.id

    lobby.nickname = nickname
    lobby.email = email

    if password:
        lobby.set_password(password)

    db.session.commit()

    # Se o lobby estiver ativo, reinicia a instância com as novas configurações
    if lobby.status == 'ATIVO':
        app = current_app._get_current_object()
        BotManager.start_lobby(lobby.id, app)

    flash(f'Lobby "{lobby.nickname}" atualizado com sucesso!', 'success')
    return redirect(url_for('main.lobbies_list'))


@main_bp.route('/lobbies/<int:lobby_id>/deletar', methods=['POST'])
@login_required
@user_active_required
def delete_lobby(lobby_id):
    """Exclusão de um lobby pertencente ao usuário com encerramento de automação se ativo."""
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    if hasattr(lobby, 'contas') and len(lobby.contas) > 0:
        flash(
            f'Não é possível excluir o lobby "{lobby.nickname}" pois ele possui {len(lobby.contas)} servidor(es) vinculado(s).',
            'danger'
        )
        return redirect(url_for('main.lobbies_list'))

    try:
        nickname = lobby.nickname
        # Fecha a janela do Playwright se estivesse rodando
        BotManager.stop_lobby(lobby.id)

        db.session.delete(lobby)
        db.session.commit()
        flash(f'Lobby "{nickname}" removido com sucesso!', 'success')
    except Exception:
        db.session.rollback()
        flash('Ocorreu um erro ao tentar excluir o lobby.', 'danger')

    return redirect(url_for('main.lobbies_list'))


@main_bp.route('/lobbies/<int:lobby_id>/toggle-status', methods=['POST'])
@login_required
@user_active_required
def toggle_lobby_status(lobby_id):
    """Alterna o status do lobby (ATIVO/INATIVO/ERRO) e liga/desliga o navegador imediatamente."""
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    if lobby.status in ['ATIVO', 'ERRO']:
        lobby.status = 'INATIVO'
        # Fecha exclusivamente o navegador deste lobby
        BotManager.stop_lobby(lobby.id)
        flash(f'Lobby "{lobby.nickname}" inativado e navegador encerrado com sucesso.', 'warning')
    else:
        if not lobby.proxy or lobby.proxy.status != 'ATIVO':
            flash(f'Não é possível ativar o lobby "{lobby.nickname}" pois a Proxy vinculada está inativa.', 'danger')
            return redirect(url_for('main.lobbies_list'))

        lobby.status = 'ATIVO'
        # Abre o navegador imediatamente ao ativar
        app = current_app._get_current_object()
        BotManager.start_lobby(lobby.id, app)
        flash(f'Lobby "{lobby.nickname}" ativado e automação iniciada!', 'success')

    db.session.commit()
    return redirect(url_for('main.lobbies_list'))


# ==========================================
# ROTAS DO DISJUNTOR GERAL (AUTOMAÇÃO EM LOTE)
# ==========================================

@main_bp.route('/bot/iniciar', methods=['POST'])
@login_required
@user_active_required
def start_bot():
    """Disjuntor Geral: Ligar Todos os Lobbies ATIVOS do usuário."""
    app = current_app._get_current_object()

    lobbies = Lobby.query.filter_by(user_id=current_user.id, status='ATIVO').all()
    lobbies_para_rodar = [l for l in lobbies if l.proxy and l.proxy.status == 'ATIVO']

    if not lobbies_para_rodar:
        flash('Nenhum lobby ativo com conexão proxy disponível para iniciar.', 'warning')
        return redirect(url_for('main.lobbies_list'))

    iniciados = 0
    for lobby in lobbies_para_rodar:
        if not BotManager.is_running(lobby.id):
            BotManager.start_lobby(lobby.id, app)
            iniciados += 1

    if iniciados > 0:
        flash(f'{iniciados} navegador(es) iniciado(s) com sucesso.', 'success')
    else:
        flash('Todos os lobbies ativos já possuem navegadores em execução.', 'info')

    return redirect(url_for('main.lobbies_list'))


@main_bp.route('/bot/parar-todos', methods=['POST'])
@login_required
@user_active_required
def stop_all_bots():
    """Disjuntor Geral: Desligar Todos os navegadores em execução do usuário."""
    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()

    encerrados = 0
    for lobby in lobbies:
        if BotManager.is_running(lobby.id):
            BotManager.stop_lobby(lobby.id)
            encerrados += 1

    if encerrados > 0:
        flash(f'{encerrados} navegador(es) encerrado(s) com sucesso.', 'success')
    else:
        flash('Nenhum navegador estava em execução no momento.', 'info')

    return redirect(url_for('main.lobbies_list'))


@main_bp.route('/api/lobbies/status', methods=['GET'])
@login_required
@user_active_required
def get_lobbies_status():
    """Retorna o status atualizado em JSON de todos os lobbies do usuário."""
    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()

    status_data = {}
    for lobby in lobbies:
        status_data[lobby.id] = {
            'status': lobby.status,
            'is_running': BotManager.is_running(lobby.id)
        }

    return jsonify(status_data)