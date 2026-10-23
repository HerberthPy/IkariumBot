# app/main/routes.py

import os
import json
import base64
from flask import render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Proxy, Lobby, User, Conta
from app.main import main_bp
from app.main.tasks import sync_webshare_job
from app.main.decorators import admin_required, user_active_required
from app.bot import BotManager


@main_bp.route('/')
@main_bp.route('/index')
@login_required
@user_active_required
def index():
    """Painel do Usuário: Carrega Lobbies e Proxies unificados em abas."""
    if current_user.is_admin == 1:
        return redirect(url_for('main.admin_dashboard'))

    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()

    for lobby in lobbies:
        lobby.is_running = BotManager.is_running(lobby.id)

    # Carrega todas as proxies atribuídas ao usuário
    user_proxies_list = Proxy.query.filter_by(user_id=current_user.id).all()

    return render_template(
        'main/index.html',
        user=current_user,
        lobbies=lobbies,
        proxies=user_proxies_list,
        user_proxies=user_proxies_list
    )


# ==========================================
# ROTAS ADMINISTRATIVAS
# ==========================================

@main_bp.route('/admin/dashboard', methods=['GET'])
@login_required
@admin_required
def admin_dashboard():
    """Painel Único do Admin: Carrega proxies e usuários em abas."""
    proxies = Proxy.query.all()
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('main/dashboard.html', proxies=proxies, users=users)


@main_bp.route('/admin/proxies', methods=['GET'])
@login_required
@admin_required
def admin_proxies():
    """Redireciona para o dashboard unificado por abas do admin."""
    return redirect(url_for('main.admin_dashboard'))


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
            return redirect(url_for('main.admin_dashboard'))

        proxy.user_id = user.id
        flash(f'Proxy #{proxy.id} atribuída com sucesso ao usuário {user.full_name}!', 'success')
    else:
        proxy.user_id = None
        flash(f'Proxy #{proxy.id} devolvida ao Pool Global.', 'info')

    db.session.commit()
    return redirect(url_for('main.admin_dashboard'))


@main_bp.route('/admin/proxies/<int:proxy_id>/unassign', methods=['POST'])
@login_required
@admin_required
def unassign_proxy(proxy_id):
    """Admin desvincula a proxy do usuário e devolve ao Pool Global."""
    proxy = Proxy.query.get_or_404(proxy_id)
    proxy.user_id = None
    db.session.commit()

    flash(f'Proxy #{proxy.id} devolvida ao Pool Global com sucesso.', 'info')
    return redirect(url_for('main.admin_dashboard'))


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

    return redirect(url_for('main.admin_dashboard'))


@main_bp.route('/admin/users', methods=['GET'])
@login_required
@admin_required
def admin_users():
    """Redireciona para o dashboard unificado por abas do admin."""
    return redirect(url_for('main.admin_dashboard'))


@main_bp.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    """Admin ativa ou desativa a conta de um usuário."""
    if user_id == current_user.id:
        flash('Você não pode desativar sua própria conta de administrador.', 'warning')
        return redirect(url_for('main.admin_dashboard'))

    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()

    status_str = "ativado" if user.is_active else "desativado"
    flash(f'Usuário {user.full_name} foi {status_str} com sucesso!', 'success')
    return redirect(url_for('main.admin_dashboard'))


# ==========================================
# ROTAS DO USUÁRIO - VISÃO DE PROXIES E LOBBIES
# ==========================================

@main_bp.route('/user/proxies', methods=['GET'])
@login_required
@user_active_required
def user_proxies():
    """Redireciona para a página principal unificada do usuário."""
    return redirect(url_for('main.index'))


@main_bp.route('/lobbies', methods=['GET'])
@login_required
@user_active_required
def lobbies_list():
    """Redireciona para a página principal unificada do usuário."""
    return redirect(url_for('main.index'))


@main_bp.route('/lobbies/novo', methods=['GET', 'POST'])
@login_required
@user_active_required
def create_lobby():
    """Cadastro de um novo lobby recebendo o Código de Sessão importado."""
    user_proxies_list = Proxy.query.filter_by(user_id=current_user.id).all()
    proxies_livres = [p for p in user_proxies_list if not p.is_in_use]

    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        email = request.form.get('email', '').strip().lower()
        proxy_id = request.form.get('proxy_id', type=int)
        session_code = request.form.get('session_code', '').strip()

        if not current_user.can_create_lobby:
            flash("Você atingiu o limite de Lobbies referente às suas proxies atribuídas.", "warning")
            return redirect(url_for('main.index'))

        proxy = Proxy.query.filter_by(id=proxy_id, user_id=current_user.id).first()
        if not proxy or proxy.is_in_use:
            flash("Proxy selecionada inválida ou já vinculada a outro lobby.", "danger")
            return redirect(url_for('main.index'))

        if not session_code:
            flash("O código da sessão é obrigatório para cadastrar o lobby.", "danger")
            return redirect(url_for('main.index'))

        # Processa e decodifica a sessão Base64 extraída do Bookmarklet
        try:
            raw_json = base64.b64decode(session_code).decode('utf-8')
            session_data = json.loads(raw_json)
        except Exception as err:
            flash(f"Código de sessão inválido ou corrompido: {str(err)}", "danger")
            return redirect(url_for('main.index'))

        # Todo lobby cadastrado nasce ATIVO por padrão
        novo_lobby = Lobby(
            nickname=nickname,
            email=email,
            proxy_id=proxy.id,
            user_id=current_user.id,
            status='ATIVO',
            has_session=True
        )

        db.session.add(novo_lobby)
        db.session.commit()

        # Salva o arquivo de sessão do Playwright
        session_file = novo_lobby.get_session_path()
        os.makedirs(os.path.dirname(session_file), exist_ok=True)
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=4)

        flash(f'Lobby "{nickname}" cadastrado com sucesso!', "success")
        return redirect(url_for('main.index'))

    return render_template('main/create_lobby.html', user_proxies=proxies_livres)


@main_bp.route('/lobbies/<int:lobby_id>/editar', methods=['POST'])
@login_required
@user_active_required
def edit_lobby(lobby_id):
    """Edição de credenciais e atualização do Código de Sessão."""
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    nickname = request.form.get('nickname', '').strip()
    email = request.form.get('email', '').strip().lower()
    proxy_id = request.form.get('proxy_id', type=int)
    session_code = request.form.get('session_code', '').strip()

    if not nickname or not email:
        flash('Apelido e E-mail são obrigatórios.', 'danger')
        return redirect(url_for('main.index'))

    if proxy_id and proxy_id != lobby.proxy_id:
        novo_proxy = Proxy.query.filter_by(id=proxy_id, user_id=current_user.id).first()
        if not novo_proxy or novo_proxy.is_in_use:
            flash('Proxy selecionada inválida ou em uso por outro lobby.', 'danger')
            return redirect(url_for('main.index'))

        BotManager.stop_lobby(lobby.id)
        lobby.proxy_id = novo_proxy.id

    lobby.nickname = nickname
    lobby.email = email

    # Atualiza a sessão caso um novo código tenha sido colado
    if session_code:
        try:
            raw_json = base64.b64decode(session_code).decode('utf-8')
            session_data = json.loads(raw_json)
            session_file = lobby.get_session_path()
            os.makedirs(os.path.dirname(session_file), exist_ok=True)
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=4)
            lobby.has_session = True
            lobby.status = 'ATIVO'
            flash('Sessão do Lobby atualizada com sucesso!', 'info')
        except Exception as e:
            flash(f'Erro ao atualizar o arquivo de sessão: {str(e)}', 'danger')

    db.session.commit()
    flash(f'Lobby "{lobby.nickname}" atualizado com sucesso!', 'success')
    return redirect(url_for('main.index'))


@main_bp.route('/lobbies/<int:lobby_id>/deletar', methods=['POST'])
@login_required
@user_active_required
def delete_lobby(lobby_id):
    """Exclusão de um lobby pertencente ao usuário, deletando contas associadas e arquivo de sessão."""
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    try:
        nickname = lobby.nickname

        BotManager.stop_lobby(lobby.id)

        session_file = lobby.get_session_path()
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
            except Exception as file_err:
                print(f"[Delete Lobby] Erro ao remover ficheiro de sessão: {file_err}")

        db.session.delete(lobby)
        db.session.commit()

        flash(f'Lobby "{nickname}" e todos os seus servidores vinculados foram excluídos com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao tentar excluir o lobby: {str(e)}', 'danger')

    return redirect(url_for('main.index'))


@main_bp.route('/lobbies/<int:lobby_id>/sincronizar', methods=['POST'])
@login_required
@user_active_required
def sync_lobby(lobby_id):
    """Sincroniza os servidores/contas do lobby conectando diretamente ao Ikariam."""
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    try:
        from app.bot.tasks.accounts_scraper import AccountsScraperTask

        # Executa a raspagem direta das contas do lobby via Playwright
        accounts_data = AccountsScraperTask.run_sync_for_lobby(lobby)

        if accounts_data:
            # Sincronização concluída com sucesso: marca lobby como ATIVO
            lobby.status = 'ATIVO'
            db.session.commit()
            flash(f"Lobby '{lobby.nickname}' sincronizado! {len(accounts_data)} conta(s) encontrada(s).", "success")
        else:
            flash(f"Nenhuma conta encontrada na sincronização do Lobby '{lobby.nickname}'.", "warning")

    except Exception as e:
        db.session.rollback()
        # Se ocorrer falha de conexão com a proxy ou sessão expirada, marca como INATIVO
        lobby.status = 'INATIVO'
        db.session.commit()
        print(f"[Sync ERRO] Falha ao sincronizar lobby #{lobby.id}: {e}")
        flash(f"Falha na conexão do Lobby/Proxy: {str(e)}", "danger")

    return redirect(url_for('main.index'))


# ==========================================
# ROTAS DE POLLING E CONTROLE INDIVIDUAL DE SERVIDORES
# ==========================================

@main_bp.route('/api/lobbies/status', methods=['GET'])
@login_required
@user_active_required
def get_lobbies_status():
    """Retorna o status atualizado, contagem e detalhes de contas com dias sem login e automação."""
    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()

    status_data = {}
    for lobby in lobbies:
        contas_list = []
        if lobby.contas:
            for conta in lobby.contas:
                nome_mundo = conta.servidor
                try:
                    from app.bot.utils.worlds import WORLD_NAMES
                    nome_mundo = WORLD_NAMES.get(conta.servidor, conta.servidor)
                except ImportError:
                    pass

                contas_list.append({
                    'id': conta.id,
                    'servidor': conta.servidor,
                    'nome_mundo': nome_mundo,
                    'pais': conta.pais.upper() if conta.pais else '',
                    'nome_usuario': conta.nome_usuario,
                    'ativo': conta.ativo,
                    'automacao_ativa': conta.automacao_ativa,
                    'dias_sem_login': conta.dias_sem_login,
                    'ultimo_login': conta.ultimo_login.strftime('%d/%m/%Y %H:%M') if conta.ultimo_login else None
                })

        status_data[lobby.id] = {
            'status': lobby.status,
            'has_session': lobby.is_session_valid,
            'is_running': BotManager.is_running(lobby.id),
            'accounts_count': len(contas_list),
            'accounts': contas_list
        }

    return jsonify(status_data)


@main_bp.route('/contas/<int:conta_id>/toggle-automacao', methods=['POST'])
@login_required
@user_active_required
def toggle_conta_automacao(conta_id):
    """Alterna o estado de automacao_ativa (True/False) de um servidor específico do usuário."""
    conta = Conta.query.join(Lobby).filter(
        Conta.id == conta_id,
        Lobby.user_id == current_user.id
    ).first_or_404()

    conta.automacao_ativa = not conta.automacao_ativa
    db.session.commit()

    estado_str = "ativada" if conta.automacao_ativa else "desativada"
    return jsonify({
        'success': True,
        'automacao_ativa': conta.automacao_ativa,
        'message': f'Automação {estado_str} para o mundo {conta.servidor} ({conta.nome_usuario}).'
    })