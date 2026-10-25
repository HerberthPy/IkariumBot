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
from playwright.sync_api import sync_playwright
import re
import threading

ACTIVE_MANUAL_BROWSERS = {}


@main_bp.route('/')
@main_bp.route('/index')
@login_required
@user_active_required
def index():
    """Painel do Utilizador: Carrega Lobbies, Proxies e Dados Consolidados do Império."""
    if current_user.is_admin == 1:
        return redirect(url_for('main.admin_dashboard'))

    lobbies = Lobby.query.filter_by(user_id=current_user.id).all()

    for lobby in lobbies:
        lobby.is_running = BotManager.is_running(lobby.id)

    user_proxies_list = Proxy.query.filter_by(user_id=current_user.id).all()

    total_ouro_geral = 0
    total_rendimento_geral = 0
    total_madeira_geral = 0
    total_vinho_geral = 0
    total_marmore_geral = 0
    total_cristal_geral = 0
    total_enxofre_geral = 0

    empire_data = []

    # Função auxiliar para formatar o rendimento no mesmo padrão da aba individual (removendo os 2 últimos dígitos)
    def formatar_rendimento_sistema(raw_rend):
        if not raw_rend:
            return "+0/h"
        try:
            str_val = str(raw_rend).strip()
            sinal = "-" if str_val.startswith("-") else "+"
            digits = "".join(c for c in str_val if c.isdigit())
            if not digits:
                return "+0/h"

            # Remove os 2 últimos dígitos (centavos/decimais)
            int_part = int(digits[:-2]) if len(digits) > 2 else 0
            if int_part == 0:
                return "+0/h"

            formatted_num = f"{int_part:,}".replace(",", ".")
            return f"{sinal}{formatted_num}/h"
        except Exception:
            return "+0/h"

    for lobby in lobbies:
        lobby_ouro_raw = 0
        lobby_rendimento_raw = 0
        lobby_madeira = 0
        lobby_vinho = 0
        lobby_marmore = 0
        lobby_cristal = 0
        lobby_enxofre = 0

        structured_accounts = []

        for conta in lobby.contas:
            if not conta.ativo:
                continue

            # Ouro bruto da conta
            ouro_int_val = 0
            if conta.ouro:
                try:
                    str_val = str(conta.ouro).strip()
                    digits = "".join(c for c in str_val if c.isdigit())
                    if digits and len(digits) > 2:
                        ouro_int_val = int(digits[:-2])
                except:
                    ouro_int_val = 0
            lobby_ouro_raw += ouro_int_val

            # Rendimento bruto da conta (removendo os 2 últimos dígitos)
            rendimento_int_val = 0
            if conta.ouro_rendimento:
                try:
                    str_rend = str(conta.ouro_rendimento).strip()
                    digits_rend = "".join(c for c in str_rend if c.isdigit())
                    if digits_rend and len(digits_rend) > 2:
                        rendimento_int_val = int(digits_rend[:-2])
                except:
                    rendimento_int_val = 0
            lobby_rendimento_raw += rendimento_int_val

            cidades_list = []
            if conta.cidades_detalhes:
                try:
                    cidades_list = json.loads(conta.cidades_detalhes)
                except:
                    cidades_list = []

            c_madeira, c_vinho, c_marmore, c_cristal, c_enxofre = 0, 0, 0, 0, 0

            for cid in cidades_list:
                recs = cid.get('recursos', {})
                c_madeira += int(str(recs.get('madeira', '0')).replace('.', '')) if recs.get('madeira') else 0
                c_vinho += int(str(recs.get('vinho', '0')).replace('.', '')) if recs.get('vinho') else 0
                c_marmore += int(str(recs.get('marmore', '0')).replace('.', '')) if recs.get('marmore') else 0
                c_cristal += int(str(recs.get('cristal', '0')).replace('.', '')) if recs.get('cristal') else 0
                c_enxofre += int(str(recs.get('enxofre', '0')).replace('.', '')) if recs.get('enxofre') else 0

            lobby_madeira += c_madeira
            lobby_vinho += c_vinho
            lobby_marmore += c_marmore
            lobby_cristal += c_cristal
            lobby_enxofre += c_enxofre

            structured_accounts.append({
                'id': conta.id,
                'servidor': conta.servidor,
                'nome_usuario': conta.nome_usuario,
                'ouro_texto': f"{ouro_int_val:,}".replace(",", ".") if ouro_int_val > 0 else "0",
                'ouro_rendimento_texto': formatar_rendimento_sistema(conta.ouro_rendimento),
                'madeira': c_madeira,
                'vinho': c_vinho,
                'marmore': c_marmore,
                'cristal': c_cristal,
                'enxofre': c_enxofre
            })

        total_ouro_geral += lobby_ouro_raw
        total_rendimento_geral += lobby_rendimento_raw
        total_madeira_geral += lobby_madeira
        total_vinho_geral += lobby_vinho
        total_marmore_geral += lobby_marmore
        total_cristal_geral += lobby_cristal
        total_enxofre_geral += lobby_enxofre

        lobby_ouro_texto = f"{lobby_ouro_raw:,}".replace(",", ".") if lobby_ouro_raw > 0 else "0"
        lobby_rendimento_texto = f"+{lobby_rendimento_raw:,}".replace(",",
                                                                      ".") + "/h" if lobby_rendimento_raw >= 0 else f"-{abs(lobby_rendimento_raw):,}".replace(
            ",", ".") + "/h"

        empire_data.append({
            'lobby_id': lobby.id,
            'nickname': lobby.nickname,
            'email': lobby.email,
            'ouro_texto': lobby_ouro_texto,
            'ouro_rendimento_texto': lobby_rendimento_texto,
            'madeira': lobby_madeira,
            'vinho': lobby_vinho,
            'marmore': lobby_marmore,
            'cristal': lobby_cristal,
            'enxofre': lobby_enxofre,
            'contas': structured_accounts
        })

    overall_totals_ouro_texto = f"{total_ouro_geral:,}".replace(",", ".") if total_ouro_geral > 0 else "0"
    overall_totals_rendimento_texto = f"+{total_rendimento_geral:,}".replace(",",
                                                                             ".") + "/h" if total_rendimento_geral >= 0 else f"-{abs(total_rendimento_geral):,}".replace(
        ",", ".") + "/h"

    overall_totals = {
        'ouro_texto': overall_totals_ouro_texto,
        'ouro_rendimento_texto': overall_totals_rendimento_texto,
        'madeira': total_madeira_geral,
        'vinho': total_vinho_geral,
        'marmore': total_marmore_geral,
        'cristal': total_cristal_geral,
        'enxofre': total_enxofre_geral
    }

    return render_template(
        'main/index.html',
        user=current_user,
        lobbies=lobbies,
        proxies=user_proxies_list,
        user_proxies=user_proxies_list,
        imperio_data=empire_data,
        totais_gerais=overall_totals
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
    proxies_livres = [p for p in user_proxies_list if not p.lobbies]

    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        email = request.form.get('email', '').strip().lower()
        proxy_id = request.form.get('proxy_id', type=int)
        session_code = request.form.get('session_code', '').strip()

        if not current_user.can_create_lobby:
            flash("Atingiu o limite de Lobbies referente às suas proxies atribuídas.", "warning")
            return redirect(url_for('main.index'))

        proxy = Proxy.query.filter_by(id=proxy_id, user_id=current_user.id).first()
        if not proxy or proxy.lobbies:
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

        flash(f'Lobby "{nickname}" cadastrado com sucesso! Selecione as contas desejadas na aba aberta.', "success")
        return redirect(url_for('main.index'))

    return render_template('main/create_lobby.html', user_proxies=proxies_livres)


@main_bp.route('/lobbies/salvar-conta-selecionada', methods=['POST'])
@login_required
@user_active_required
def save_selected_account():
    lobby_id = request.form.get('lobby_id', type=int)
    conta_ids_selecionadas = request.form.getlist('conta_ids', type=int)

    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    Conta.query.filter_by(lobby_id=lobby.id).update({'ativo': False}, synchronize_session=False)

    if conta_ids_selecionadas:
        Conta.query.filter(
            Conta.lobby_id == lobby.id,
            Conta.id.in_(conta_ids_selecionadas)
        ).update({'ativo': True}, synchronize_session=False)

    lobby.status = 'ATIVO'
    db.session.commit()

    session.pop('temp_selection_data', None)
    session.modified = True

    flash(f'Contas configuradas com sucesso para o lobby "{lobby.nickname}"!', 'success')
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
        proxy_em_uso_por_outro = any(l.id != lobby.id for l in novo_proxy.lobbies) if novo_proxy else True

        if not novo_proxy or proxy_em_uso_por_outro:
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
    lobby = Lobby.query.filter_by(id=lobby_id, user_id=current_user.id).first_or_404()

    try:
        from app.bot.tasks.accounts_scraper import AccountsScraperTask
        db_accounts = AccountsScraperTask.run_sync_for_lobby(lobby)

        if not db_accounts:
            flash(f"Falha ao sincronizar: nenhuma conta detetada para '{lobby.nickname}'.", "warning")
            return redirect(url_for('main.index'))

        lobby.status = 'ATIVO'
        db.session.commit()

        flash(f"Lobby '{lobby.nickname}' sincronizado com sucesso!", "success")
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

        flash(f"Varredura geral realizada para '{lobby.nickname}'. Selecione as contas na aba aberta.", "info")
        return redirect(url_for('main.index'))
    except Exception as e:
        flash(f"Erro ao executar varredura geral: {str(e)}", "danger")
        return redirect(url_for('main.index'))


# ==========================================
# ROTAS DO PAINEL DA CONTA / JOGO MANUAL
# ==========================================

@main_bp.route('/contas/<int:conta_id>/jogar-manual', methods=['POST'])
@login_required
@user_active_required
def jogar_manual(conta_id):
    conta = Conta.query.join(Lobby).filter(
        Conta.id == conta_id,
        Lobby.user_id == current_user.id
    ).first_or_404()

    if conta_id in ACTIVE_MANUAL_BROWSERS:
        try:
            ACTIVE_MANUAL_BROWSERS[conta_id].quit()
        except:
            pass
        ACTIVE_MANUAL_BROWSERS.pop(conta_id, None)

    lobby = conta.lobby
    session_file = lobby.get_session_path()

    cookies_list = []
    local_storage_dict = {}

    if os.path.exists(session_file):
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data_json = json.load(f)

            raw_cookies = data_json.get("cookies", [])
            if isinstance(raw_cookies, str):
                try:
                    cookies_list = json.loads(raw_cookies)
                except:
                    cookies_list = []
            elif isinstance(raw_cookies, list):
                cookies_list = raw_cookies

            formatted_cookies = []
            for c in cookies_list:
                cookie_item = {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "domain": c.get("domain", ".gameforge.com"),
                    "path": c.get("path", "/")
                }
                if "secure" in c:
                    cookie_item["secure"] = c["secure"]
                if "httpOnly" in c:
                    cookie_item["httpOnly"] = c["httpOnly"]
                if "expires" in c and isinstance(c["expires"], (int, float)):
                    cookie_item["expires"] = c["expires"]
                formatted_cookies.append(cookie_item)
            cookies_list = formatted_cookies

            raw_ls = data_json.get("localStorage", "{}")
            if isinstance(raw_ls, str):
                try:
                    local_storage_dict = json.loads(raw_ls)
                except:
                    local_storage_dict = {}
            elif isinstance(raw_ls, dict):
                local_storage_dict = raw_ls

        except Exception as err:
            print(f"[Aviso Sessão Manual]: Erro ao processar ficheiro de sessão: {err}")

    proxy_server = None
    proxy_user = None
    proxy_pass = None

    if lobby.proxy:
        proxy_server = f"http://{lobby.proxy.address}:{lobby.proxy.port}"
        if lobby.proxy.username and lobby.proxy.get_password():
            proxy_user = lobby.proxy.username
            proxy_pass = lobby.proxy.get_password()

    app_instance = current_app._get_current_object()

    def run_manual_browser():
        with app_instance.app_context():
            p = None
            browser = None
            try:
                p = sync_playwright().start()
                browser = p.chromium.launch(headless=False, args=["--start-maximized"])

                ACTIVE_MANUAL_BROWSERS[conta_id] = browser

                proxy_config = None
                if proxy_server:
                    proxy_config = {"server": proxy_server}
                    if proxy_user and proxy_pass:
                        proxy_config["username"] = proxy_user
                        proxy_config["password"] = proxy_pass

                context_kwargs = {}
                if proxy_config:
                    context_kwargs["proxy"] = proxy_config

                context = browser.new_context(**context_kwargs)

                if cookies_list:
                    try:
                        context.add_cookies(cookies_list)
                    except Exception as cookie_err:
                        print(f"[Aviso Injeção Cookies]: {cookie_err}")

                page = context.new_page()

                if local_storage_dict:
                    try:
                        page.goto("https://lobby.ikariam.gameforge.com/", timeout=30000)
                        page.evaluate("""(storage) => {
                            for (let key in storage) {
                                localStorage.setItem(key, storage[key]);
                            }
                        }""", local_storage_dict)
                    except Exception as ls_err:
                        print(f"[Aviso LocalStorage]: {ls_err}")

                c_db = Conta.query.get(conta_id)
                if c_db:
                    c_db.is_playing_active = True
                    db.session.commit()

                page.goto("https://lobby.ikariam.gameforge.com/pt_BR/hub", timeout=45000, wait_until="domcontentloaded")

                def limpar_sessao():
                    with app_instance.app_context():
                        c_close = Conta.query.get(conta_id)
                        if c_close:
                            c_close.is_playing_active = False
                            db.session.commit()
                    ACTIVE_MANUAL_BROWSERS.pop(conta_id, None)
                    try:
                        if browser:
                            browser.close()
                        if p:
                            p.stop()
                    except:
                        pass

                page.on("close", lambda: limpar_sessao())
                context.on("close", lambda: limpar_sessao())

                while browser.is_connected():
                    import time
                    time.sleep(1)

            except Exception as e:
                print(f"[Erro Jogo Manual]: {e}")
            finally:
                with app_instance.app_context():
                    c_err = Conta.query.get(conta_id)
                    if c_err:
                        c_err.is_playing_active = False
                        db.session.commit()
                ACTIVE_MANUAL_BROWSERS.pop(conta_id, None)
                try:
                    if browser:
                        browser.close()
                    if p:
                        p.stop()
                except:
                    pass

    threading.Thread(target=run_manual_browser, daemon=True).start()

    return jsonify({'success': True, 'message': 'Janela do jogo aberta com sucesso!'})


@main_bp.route('/contas/<int:conta_id>/encerrar-manual', methods=['POST'])
@login_required
@user_active_required
def encerrar_manual(conta_id):
    conta = Conta.query.join(Lobby).filter(
        Conta.id == conta_id,
        Lobby.user_id == current_user.id
    ).first_or_404()

    if conta_id in ACTIVE_MANUAL_BROWSERS:
        try:
            ACTIVE_MANUAL_BROWSERS[conta_id].close()
        except:
            pass
        ACTIVE_MANUAL_BROWSERS.pop(conta_id, None)

    conta.is_playing_active = False
    db.session.commit()

    return jsonify({'success': True, 'message': 'Sessão manual encerrada com sucesso.'})


@main_bp.route('/contas/<int:conta_id>/status-jogo', methods=['GET'])
@login_required
@user_active_required
def status_jogo_conta(conta_id):
    conta = Conta.query.join(Lobby).filter(
        Conta.id == conta_id,
        Lobby.user_id == current_user.id
    ).first_or_404()

    return jsonify({'is_playing_active': conta.is_playing_active})


@main_bp.route('/contas/<int:conta_id>/sincronizar-painel', methods=['POST'])
@login_required
@user_active_required
def sincronizar_painel_conta(conta_id):
    conta = Conta.query.join(Lobby).filter(
        Conta.id == conta_id,
        Lobby.user_id == current_user.id
    ).first_or_404()

    lobby = conta.lobby

    try:
        from app.bot.tasks.server_login import ServerLoginTask
        sucesso, dados = ServerLoginTask.run_and_get_info(lobby.id, conta.id)

        if sucesso and dados:
            conta.ouro = dados.get('ouro', '0')
            conta.ouro_rendimento = dados.get('ouro_rendimento', '0')
            conta.barcos_totais = dados.get('barcos_totais', 0)
            conta.barcos_disponiveis = dados.get('barcos_disponiveis', 0)
            conta.recursos_imperio = json.dumps(dados.get('recursos_imperio', {}))
            conta.cidades_detalhes = json.dumps(dados.get('cidades', []))
            conta.ultima_sincronizacao = get_brasilia_time()
            db.session.commit()

            return jsonify({'success': True, 'message': 'Dados sincronizados e salvos com sucesso!'})
        else:
            return jsonify(
                {'success': False, 'message': 'O bot conectou, mas falhou ao recolher os dados da página.'}), 500

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Erro na automação: {str(e)}'}), 500


@main_bp.route('/contas/<int:conta_id>/dados-painel', methods=['GET'])
@login_required
@user_active_required
def get_dados_painel_conta(conta_id):
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
        'ultima_sincronizacao': conta.ultima_sincronizacao.strftime(
            '%d/%m/%Y %H:%M') if conta.ultima_sincronizacao else 'Nunca',
        'is_playing_active': conta.is_playing_active,
        'automacao_ativa': conta.automacao_ativa
    })


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
                    'status_jogo': conta.status_jogo,
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