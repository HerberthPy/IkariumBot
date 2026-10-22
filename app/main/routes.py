# app/main/routes.py

import os
import json
from flask import render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Proxy, Lobby, User, Conta
from app.main import main_bp
from app.main.tasks import sync_webshare_job
from app.main.decorators import admin_required, user_active_required
from app.bot import BotManager
from app.bot.auth import AuthManager


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
            status='INATIVO',
            has_session=False
        )
        novo_lobby.set_password(password)

        db.session.add(novo_lobby)
        db.session.commit()

        flash("Lobby cadastrado com sucesso! Agora realize a autenticação inicial para vincular a sessão.", "success")
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
    """Exclusão de um lobby pertencente ao usuário, deletando contas associadas e arquivo de sessão."""
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    try:
        nickname = lobby.nickname

        # 1. Encerra a automação do Playwright se estiver rodando
        BotManager.stop_lobby(lobby.id)

        # 2. Remove o arquivo JSON de sessão do disco, se existir
        session_file = lobby.get_session_path()
        if os.path.exists(session_file):
            try:
                os.remove(session_file)
            except Exception as file_err:
                print(f"[Delete Lobby] Erro ao remover ficheiro de sessão: {file_err}")

        # 3. Exclui o lobby do banco de dados (o SQLAlchemy apaga as contas vinculadas em cascata)
        db.session.delete(lobby)
        db.session.commit()

        flash(f'Lobby "{nickname}" e todos os seus servidores vinculados foram excluídos com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao tentar excluir o lobby: {str(e)}', 'danger')

    return redirect(url_for('main.lobbies_list'))


@main_bp.route('/lobbies/<int:lobby_id>/toggle-status', methods=['POST'])
@login_required
@user_active_required
def toggle_lobby_status(lobby_id):
    """Alterna o status do lobby (ATIVO/INATIVO/ERRO) e liga/desliga o navegador imediatamente."""
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    if lobby.status in ['ATIVO', 'ERRO']:
        lobby.status = 'INATIVO'
        db.session.commit()
        # Fecha exclusivamente o navegador deste lobby
        BotManager.stop_lobby(lobby.id)
        flash(f'Lobby "{lobby.nickname}" inativado e navegador encerrado com sucesso.', 'warning')
    else:
        if not lobby.proxy or lobby.proxy.status != 'ATIVO':
            flash(f'Não é possível ativar o lobby "{lobby.nickname}" pois a Proxy vinculada está inativa.', 'danger')
            return redirect(url_for('main.lobbies_list'))

        if not lobby.is_session_valid:
            flash(f'O lobby "{lobby.nickname}" não possui uma sessão salva. Por favor, autentique-o primeiro.', 'danger')
            return redirect(url_for('main.lobbies_list'))

        lobby.status = 'ATIVO'
        db.session.commit()
        # Abre o navegador imediatamente ao ativar
        app = current_app._get_current_object()
        BotManager.start_lobby(lobby.id, app)
        flash(f'Lobby "{lobby.nickname}" ativado e automação iniciada!', 'success')

    return redirect(url_for('main.lobbies_list'))


# ==========================================
# ROTAS DE AUTENTICAÇÃO INTERATIVA DE SESSÃO
# ==========================================

@main_bp.route('/lobbies/<int:lobby_id>/autenticar-interativo', methods=['POST'])
@login_required
@user_active_required
def authenticate_lobby_interactive(lobby_id):
    """Abre uma janela Playwright visível (sem proxy) direcionada ao login com e-mail e senha preenchidos."""
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    try:
        from playwright.sync_api import sync_playwright

        session_file = lobby.get_session_path()
        lobby_password = lobby.get_password()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            page.goto("https://lobby.ikariam.gameforge.com/pt_BR/login", timeout=60000, wait_until="domcontentloaded")

            try:
                tab_login = page.locator("ul.tabs-header li:has-text('Entrar'), ul.tabs-header li:has-text('Log in')").first
                if tab_login.is_visible(timeout=3000):
                    tab_login.click()
            except Exception:
                pass

            try:
                email_input = page.locator("input[type='email'], input[name='email'], input[name='login']").first
                email_input.wait_for(state="visible", timeout=10000)
                email_input.fill(lobby.email)

                pwd_input = page.locator("input[type='password'], input[name='password']").first
                pwd_input.wait_for(state="visible", timeout=5000)
                if lobby_password:
                    pwd_input.fill(lobby_password)

                print(f"[Auth Direct] Credenciais preenchidas para {lobby.email}.")
            except Exception as fill_err:
                print(f"[Auth Direct] Aviso ao preencher formulário: {fill_err}")

            print(f"[Auth Direct] Aguardando o usuário resolver o CAPTCHA/clicar em Entrar no Lobby #{lobby.id}...")

            page.wait_for_url(lambda url: "/hub" in url or "/accounts" in url, timeout=180000)
            page.wait_for_timeout(3000)

            cookies = context.cookies()
            local_storage = page.evaluate("() => JSON.stringify(localStorage)")

            os.makedirs(os.path.dirname(session_file), exist_ok=True)

            with open(session_file, "w", encoding="utf-8") as f:
                json.dump({"cookies": cookies, "local_storage": local_storage}, f, indent=4)

            browser.close()

        lobby.has_session = True
        db.session.commit()

        return jsonify({'success': True, 'message': 'Autenticação realizada e sessão capturada com sucesso!'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Falha na autenticação: {str(e)}'}), 500


# ==========================================
# ROTAS DO DISJUNTOR GERAL (AUTOMAÇÃO EM LOTE)
# ==========================================

@main_bp.route('/bot/iniciar', methods=['POST'])
@login_required
@user_active_required
def start_bot():
    """Disjuntor Geral: Ligar Todos os Lobbies com sessão válida."""
    app = current_app._get_current_object()

    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()
    lobbies_para_rodar = [l for l in lobbies if l.proxy and l.proxy.status == 'ATIVO' and l.is_session_valid]

    if not lobbies_para_rodar:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Nenhum lobby elegível disponível.'})
        flash('Nenhum lobby com conexão proxy e sessão válida disponível para iniciar.', 'warning')
        return redirect(url_for('main.lobbies_list'))

    iniciados = 0
    for lobby in lobbies_para_rodar:
        lobby.status = 'ATIVO'
        if not BotManager.is_running(lobby.id):
            BotManager.start_lobby(lobby.id, app)
            iniciados += 1

    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': f'{iniciados} navegador(es) iniciado(s) com sucesso.'})

    if iniciados > 0:
        flash(f'{iniciados} navegador(es) iniciado(s) com sucesso.', 'success')
    else:
        flash('Todos os lobbies elegíveis já estão em execução.', 'info')

    return redirect(url_for('main.lobbies_list'))


@main_bp.route('/bot/parar-todos', methods=['POST'])
@login_required
@user_active_required
def stop_all_bots():
    """Disjuntor Geral: Desligar Todos os navegadores em execução do usuário instantaneamente."""
    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()

    encerrados = 0
    for lobby in lobbies:
        # Altera o status no banco para INATIVO para forçar o encerramento em tempo real
        lobby.status = 'INATIVO'
        if BotManager.is_running(lobby.id):
            BotManager.stop_lobby(lobby.id)
            encerrados += 1

    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': f'{encerrados} navegador(es) encerrado(s) com sucesso.'})

    if encerrados > 0:
        flash(f'{encerrados} navegador(es) encerrado(s) com sucesso.', 'success')
    else:
        flash('Nenhum navegador estava em execução no momento.', 'info')

    return redirect(url_for('main.lobbies_list'))


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