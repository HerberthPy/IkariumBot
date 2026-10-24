# app/main/routes.py

import os
import json
import base64
from flask import render_template, request, redirect, url_for, flash, current_app, jsonify, session
from flask_login import login_required, current_user
from app import db
from app.models import Proxy, Lobby, User, Conta, get_brasilia_time
from app.main import main_bp
from app.main.tasks import sync_webshare_job
from app.main.decorators import admin_required, user_active_required
from app.bot import BotManager


@main_bp.route('/')
@main_bp.route('/index')
@login_required
@user_active_required
def index():
    """Painel do Utilizador: Carrega Lobbies e Proxies unificados em abas."""
    if current_user.is_admin == 1:
        return redirect(url_for('main.admin_dashboard'))

    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()

    for lobby in lobbies:
        lobby.is_running = BotManager.is_running(lobby.id)

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
    proxies = Proxy.query.all()
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('main/dashboard.html', proxies=proxies, users=users)


@main_bp.route('/admin/proxies', methods=['GET'])
@login_required
@admin_required
def admin_proxies():
    return redirect(url_for('main.admin_dashboard'))


@main_bp.route('/admin/proxies/<int:proxy_id>/assign', methods=['POST'])
@login_required
@admin_required
def assign_proxy(proxy_id):
    proxy = Proxy.query.get_or_404(proxy_id)
    user_id = request.form.get('user_id', type=int)

    if user_id:
        user = User.query.get(user_id)
        if not user:
            flash('Utilizador selecionado não encontrado.', 'danger')
            return redirect(url_for('main.admin_dashboard'))

        proxy.user_id = user.id
        flash(f'Proxy #{proxy.id} atribuída com sucesso ao utilizador {user.full_name}!', 'success')
    else:
        proxy.user_id = None
        flash(f'Proxy #{proxy.id} devolvida ao Pool Global.', 'info')

    db.session.commit()
    return redirect(url_for('main.admin_dashboard'))


@main_bp.route('/admin/proxies/<int:proxy_id>/unassign', methods=['POST'])
@login_required
@admin_required
def unassign_proxy(proxy_id):
    proxy = Proxy.query.get_or_404(proxy_id)
    proxy.user_id = None
    db.session.commit()

    flash(f'Proxy #{proxy.id} devolvida ao Pool Global com sucesso.', 'info')
    return redirect(url_for('main.admin_dashboard'))


@main_bp.route('/admin/proxies/sincronizar', methods=['POST', 'GET'])
@login_required
@admin_required
def sync_proxies():
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
    return redirect(url_for('main.admin_dashboard'))


@main_bp.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    if user_id == current_user.id:
        flash('Você não pode desativar sua própria conta de administrador.', 'warning')
        return redirect(url_for('main.admin_dashboard'))

    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()

    status_str = "ativado" if user.is_active else "desativado"
    flash(f'Utilizador {user.full_name} foi {status_str} com sucesso!', 'success')
    return redirect(url_for('main.admin_dashboard'))


# ==========================================
# ROTAS DO UTILIZADOR - VISÃO DE PROXIES E LOBBIES
# ==========================================

@main_bp.route('/user/proxies', methods=['GET'])
@login_required
@user_active_required
def user_proxies():
    return redirect(url_for('main.index'))


@main_bp.route('/lobbies', methods=['GET'])
@login_required
@user_active_required
def lobbies_list():
    return redirect(url_for('main.index'))


@main_bp.route('/lobbies/novo', methods=['GET', 'POST'])
@login_required
@user_active_required
def create_lobby():
    user_proxies_list = Proxy.query.filter_by(user_id=current_user.id).all()
    proxies_livres = [p for p in user_proxies_list if not p.is_in_use]

    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        email = request.form.get('email', '').strip().lower()
        proxy_id = request.form.get('proxy_id', type=int)
        session_code = request.form.get('session_code', '').strip()

        if not current_user.can_create_lobby:
            flash("Atingiu o limite de Lobbies referente às suas proxies atribuídas.", "warning")
            return redirect(url_for('main.index'))

        proxy = Proxy.query.filter_by(id=proxy_id, user_id=current_user.id).first()
        if not proxy or proxy.is_in_use:
            flash("Proxy selecionada inválida ou já vinculada a outro lobby.", "danger")
            return redirect(url_for('main.index'))

        if not session_code:
            flash("O código da sessão é obrigatório para cadastrar o lobby.", "danger")
            return redirect(url_for('main.index'))

        try:
            raw_json = base64.b64decode(session_code).decode('utf-8')
            session_data = json.loads(raw_json)
        except Exception as err:
            flash(f"Código de sessão inválido ou corrompido: {str(err)}", "danger")
            return redirect(url_for('main.index'))

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

        session_file = novo_lobby.get_session_path()
        os.makedirs(os.path.dirname(session_file), exist_ok=True)
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=4)

        try:
            from app.bot.tasks.accounts_scraper import AccountsScraperTask
            db_accounts = AccountsScraperTask.run_sync_for_lobby(novo_lobby)
        except Exception as e:
            db_accounts = []

        if not db_accounts:
            flash(f'Lobby "{nickname}" cadastrado, mas nenhuma conta foi encontrada na varredura inicial.', "warning")
            return redirect(url_for('main.index'))

        session['temp_selection_data'] = {
            'lobby_id': novo_lobby.id,
            'accounts': db_accounts,
            'modo': 'cadastro'
        }
        session.modified = True

        flash(f'Lobby "{nickname}" cadastrado com sucesso! Selecione a conta desejada na aba aberta.', "success")
        return redirect(url_for('main.index'))

    return render_template('main/create_lobby.html', user_proxies=proxies_livres)


@main_bp.route('/lobbies/salvar-conta-selecionada', methods=['POST'])
@login_required
@user_active_required
def save_selected_account():
    """Mantém estritamente apenas a conta escolhida e remove permanentemente as restantes."""
    lobby_id = request.form.get('lobby_id', type=int)

    conta_id_selecionada = request.form.get('conta_id', type=int)
    if not conta_id_selecionada:
        conta_id_selecionada = request.form.get('conta_index', type=int)

    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()
    contas_lobby = Conta.query.filter_by(lobby_id=lobby.id).all()

    if conta_id_selecionada and contas_lobby:
        if conta_id_selecionada < len(contas_lobby) and not any(c.id == conta_id_selecionada for c in contas_lobby):
            conta_escolhida = contas_lobby[conta_id_selecionada]
        else:
            conta_escolhida = Conta.query.filter_by(id=conta_id_selecionada, lobby_id=lobby.id).first()

        if conta_escolhida:
            Conta.query.filter(
                Conta.lobby_id == lobby.id,
                Conta.id != conta_escolhida.id
            ).delete(synchronize_session=False)

            conta_escolhida.ativo = True
            lobby.status = 'ATIVO'
            db.session.commit()

    session.pop('temp_selection_data', None)
    session.modified = True

    flash(f'Conta configurada e ativada com sucesso para o lobby "{lobby.nickname}"!', 'success')
    return redirect(url_for('main.index'))


@main_bp.route('/lobbies/<int:lobby_id>/editar', methods=['POST'])
@login_required
@user_active_required
def edit_lobby(lobby_id):
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
            flash(f'Erro ao atualizar o ficheiro de sessão: {str(e)}', 'danger')

    db.session.commit()
    flash(f'Lobby "{lobby.nickname}" atualizado com sucesso!', 'success')
    return redirect(url_for('main.index'))


@main_bp.route('/lobbies/<int:lobby_id>/deletar', methods=['POST'])
@login_required
@user_active_required
def delete_lobby(lobby_id):
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

        session.pop('temp_selection_data', None)
        session.modified = True

        flash(f'Lobby "{nickname}" e todos os seus servidores vinculados foram excluídos com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao tentar excluir o lobby: {str(e)}', 'danger')

    return redirect(url_for('main.index'))


@main_bp.route('/lobbies/<int:lobby_id>/sincronizar', methods=['POST'])
@login_required
@user_active_required
def sync_lobby(lobby_id):
    """Sincroniza automaticamente a conta existente no banco por ID ou Servidor/Nome."""
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    try:
        from app.bot.tasks.accounts_scraper import AccountsScraperTask
        db_accounts = AccountsScraperTask.run_sync_for_lobby(lobby)

        if not db_accounts:
            flash(f"Falha ao sincronizar: nenhuma conta detetada para '{lobby.nickname}'.", "warning")
            return redirect(url_for('main.index'))

        conta_atual = Conta.query.filter_by(lobby_id=lobby.id, ativo=True).first()
        if not conta_atual:
            conta_atual = Conta.query.filter_by(lobby_id=lobby.id).first()

        match_encontrado = None
        if conta_atual:
            for acc in db_accounts:
                match_id = (
                    acc.get("gameforge_account_id") and conta_atual.gameforge_account_id and
                    str(acc.get("gameforge_account_id")) == str(conta_atual.gameforge_account_id)
                )
                match_nome = (
                    acc.get("servidor", "").strip().lower() == conta_atual.servidor.strip().lower() and
                    acc.get("nome_usuario", "").strip().lower() == conta_atual.nome_usuario.strip().lower()
                )

                if match_id or match_nome:
                    match_encontrado = acc
                    break

        if match_encontrado:
            Conta.query.filter(
                Conta.lobby_id == lobby.id,
                Conta.id != match_encontrado["db_id"]
            ).delete(synchronize_session=False)

            conta_alvo = Conta.query.filter_by(id=match_encontrado["db_id"]).first()
            if conta_alvo:
                conta_alvo.ativo = True
                conta_alvo.ultimo_login = get_brasilia_time()
                if match_encontrado.get("gameforge_account_id"):
                    conta_alvo.gameforge_account_id = match_encontrado.get("gameforge_account_id")

            lobby.status = 'ATIVO'
            db.session.commit()

            flash(f"Lobby '{lobby.nickname}' sincronizado com sucesso (Conta: {match_encontrado['nome_usuario']} - {match_encontrado['servidor']})!", "success")
        else:
            session['temp_selection_data'] = {
                'lobby_id': lobby.id,
                'accounts': db_accounts,
                'modo': 'sincronizacao'
            }
            session.modified = True
            flash(f"A conta anterior não foi encontrada na varredura de '{lobby.nickname}'. Selecione a nova conta ativa.", "warning")

    except Exception as e:
        db.session.rollback()
        lobby.status = 'ERRO'
        db.session.commit()
        flash(f"Falha na sincronização do Lobby: {str(e)}", "danger")

    return redirect(url_for('main.index'))


@main_bp.route('/lobbies/<int:lobby_id>/varredura-geral', methods=['POST', 'GET'])
@login_required
@user_active_required
def varredura_geral_lobby(lobby_id):
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    try:
        from app.bot.tasks.accounts_scraper import AccountsScraperTask
        db_accounts = AccountsScraperTask.run_sync_for_lobby(lobby)

        session['temp_selection_data'] = {
            'lobby_id': lobby.id,
            'accounts': db_accounts,
            'modo': 'troca_geral'
        }
        session.modified = True

        flash(f"Varredura geral realizada para '{lobby.nickname}'. Selecione a nova conta na aba aberta.", "info")
        return redirect(url_for('main.index'))
    except Exception as e:
        flash(f"Erro ao executar varredura geral: {str(e)}", "danger")
        return redirect(url_for('main.index'))


# ==========================================
# NOVAS ROTAS DO PAINEL DA CONTA / SINCRONIZAÇÃO
# ==========================================

@main_bp.route('/contas/<int:conta_id>/sincronizar-painel', methods=['POST'])
@login_required
@user_active_required
def sincronizar_painel_conta(conta_id):
    """Executa o login via bot, extrai os dados do império e atualiza a conta no banco."""
    conta = Conta.query.join(Lobby).filter(
        Conta.id == conta_id,
        Lobby.user_id == current_user.id
    ).first_or_404()

    lobby = conta.lobby

    try:
        from app.bot.tasks.server_login import ServerLoginTask
        sucesso, dados = ServerLoginTask.run_and_get_info(lobby.id, conta.id)

        if sucesso and dados:
            conta.ouro = dados.get('ouro_texto', '0')
            conta.ouro_rendimento = dados.get('ouro_rendimento', '+0/h')
            conta.barcos_totais = dados.get('barcos_totais', 0)
            conta.barcos_disponiveis = dados.get('barcos_disponiveis', 0)
            conta.recursos_imperio = json.dumps(dados.get('recursos_imperio', {}))
            conta.cidades_detalhes = json.dumps(dados.get('cidades', []))
            conta.ultima_sincronizacao = get_brasilia_time()
            db.session.commit()

            return jsonify({'success': True, 'message': 'Dados sincronizados com sucesso!'})
        else:
            return jsonify({'success': False, 'message': 'O bot conectou, mas falhou ao recolher os dados da página.'}), 500

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro na automação: {str(e)}'}), 500


@main_bp.route('/contas/<int:conta_id>/dados-painel', methods=['GET'])
@login_required
@user_active_required
def get_dados_painel_conta(conta_id):
    """Retorna os dados salvos no banco para renderizar o painel instantaneamente."""
    conta = Conta.query.join(Lobby).filter(
        Conta.id == conta_id,
        Lobby.user_id == current_user.id
    ).first_or_404()

    return jsonify({
        'servidor': conta.servidor,
        'nome_usuario': conta.nome_usuario,
        'ouro': conta.ouro,
        'ouro_rendimento': conta.ouro_rendimento,
        'barcos_totais': conta.barcos_totais,
        'barcos_disponiveis': conta.barcos_disponiveis,
        'recursos_imperio': json.loads(conta.recursos_imperio or '{}'),
        'cidades': json.loads(conta.cidades_detalhes or '[]'),
        'ultima_sincronizacao': conta.ultima_sincronizacao.strftime('%d/%m/%Y %H:%M') if conta.ultima_sincronizacao else 'Nunca'
    })


# ==========================================
# ROTAS DE POLLING E CONTROLE INDIVIDUAL
# ==========================================

@main_bp.route('/api/lobbies/status', methods=['GET'])
@login_required
@user_active_required
def get_lobbies_status():
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