import os
import json
import base64
from flask import render_template, request, redirect, url_for, flash, current_app, jsonify, session
from flask_login import login_required, current_user
from app import db
from app.models import Proxy, Lobby, User, Conta, Cidade, Ilha, get_brasilia_time
from app.main import main_bp
from app.main.tasks import sync_webshare_job
from app.main.decorators import admin_required, user_active_required
from app.bot import BotManager


@main_bp.route('/')
@main_bp.route('/index')
@login_required
@user_active_required
def index():
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

    def formatar_rendimento_sistema(raw_rend):
        if not raw_rend:
            return "+0/h"
        try:
            str_val = str(raw_rend).strip()
            sinal = "-" if str_val.startswith("-") else "+"
            digits = "".join(c for c in str_val if c.isdigit())
            if not digits:
                return "+0/h"
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

            recs_totais_conta = conta.recursos_totais_imperio
            c_madeira = recs_totais_conta["madeira"]
            c_vinho = recs_totais_conta["vinho"]
            c_marmore = recs_totais_conta["marmore"]
            c_cristal = recs_totais_conta["cristal"]
            c_enxofre = recs_totais_conta["enxofre"]

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
                'madeira': int(c_madeira),
                'vinho': int(c_vinho),
                'marmore': int(c_marmore),
                'cristal': int(c_cristal),
                'enxofre': int(c_enxofre)
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
            'madeira': int(lobby_madeira),
            'vinho': int(lobby_vinho),
            'marmore': int(lobby_marmore),
            'cristal': int(lobby_cristal),
            'enxofre': int(lobby_enxofre),
            'contas': structured_accounts
        })

    overall_totals_ouro_texto = f"{total_ouro_geral:,}".replace(",", ".") if total_ouro_geral > 0 else "0"
    overall_totals_rendimento_texto = f"+{total_rendimento_geral:,}".replace(",",
                                                                             ".") + "/h" if total_rendimento_geral >= 0 else f"-{abs(total_rendimento_geral):,}".replace(
        ",", ".") + "/h"

    overall_totals = {
        'ouro_texto': overall_totals_ouro_texto,
        'ouro_rendimento_texto': overall_totals_rendimento_texto,
        'madeira': int(total_madeira_geral),
        'vinho': int(total_vinho_geral),
        'marmore': int(total_marmore_geral),
        'cristal': int(total_cristal_geral),
        'enxofre': int(total_enxofre_geral)
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

@main_bp.route('/admin/dashboard', methods=['GET'])
@login_required
@admin_required
def admin_dashboard():
    proxies = Proxy.query.all()
    users = User.query.filter(User.id != current_user.id).order_by(User.created_at.desc()).all()
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
        if not user or user.id == current_user.id:
            flash('Utilizador selecionado inválido.', 'danger')
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
        flash('Você não pode alterar o status da sua própria conta.', 'warning')
        return redirect(url_for('main.admin_dashboard'))

    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()

    status_str = "ativado" if user.is_active else "desativado"
    flash(f'Utilizador {user.full_name} foi {status_str} com sucesso!', 'success')
    return redirect(url_for('main.admin_dashboard'))

@main_bp.route('/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@admin_required
def toggle_user_admin(user_id):
    if user_id == current_user.id:
        flash('Você não pode alterar seu próprio nível de privilégio.', 'warning')
        return redirect(url_for('main.admin_dashboard'))

    user = User.query.get_or_404(user_id)
    user.is_admin = 0 if user.is_admin == 1 else 1
    db.session.commit()

    cargo_str = "promovido a Administrador" if user.is_admin == 1 else "rebaixado a Usuário comum"
    flash(f'O utilizador {user.full_name} foi {cargo_str} com sucesso!', 'success')
    return redirect(url_for('main.admin_dashboard'))

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
            current_app.logger.error(f"[Cadastro] Erro ao varrer contas no novo lobby: {e}")
            db_accounts = []

        session['temp_selection_data'] = {
            'lobby_id': novo_lobby.id,
            'accounts': db_accounts,
            'modo': 'cadastro'
        }
        session.modified = True

        if not db_accounts:
            flash(
                f'Lobby "{nickname}" cadastrado, mas nenhuma conta foi encontrada na varredura inicial. Pode sincronizar novamente.',
                "warning")
        else:
            flash(f'Lobby "{nickname}" cadastrado com sucesso! Selecione as contas desejadas.', "success")

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

@main_bp.route('/contas/<int:conta_id>/dados-painel', methods=['GET'])
@login_required
@user_active_required
def get_dados_painel_conta(conta_id):
    conta = Conta.query.join(Lobby).filter(
        Conta.id == conta_id,
        Lobby.user_id == current_user.id
    ).first_or_404()

    cidades_serializadas = []
    tot_madeira = 0
    tot_vinho = 0
    tot_marmore = 0
    tot_cristal = 0
    tot_enxofre = 0

    # Ouro e Rendimento
    ouro_val = int(conta.ouro or 0)
    rendimento_val = int(conta.ouro_rendimento or 0)

    ouro_formatado = f"{ouro_val:,.0f}".replace(',', '.') if ouro_val > 0 else "0"

    if rendimento_val >= 0:
        rendimento_formatado = f"+{rendimento_val:,.0f}/h".replace(',', '.')
    else:
        rendimento_formatado = f"-{abs(rendimento_val):,.0f}/h".replace(',', '.')

    for cid in conta.cidades:
        ilha = cid.ilha

        # Como já está limpo no BD, apenas lemos como int
        m_val = int(cid.madeira or 0)
        v_val = int(cid.vinho or 0)
        mar_val = int(cid.marmore or 0)
        c_val = int(cid.cristal or 0)
        e_val = int(cid.enxofre or 0)

        tot_madeira += m_val
        tot_vinho += v_val
        tot_marmore += mar_val
        tot_cristal += c_val
        tot_enxofre += e_val

        # Formatação de população livre e máxima com pontos
        p_livre = int(cid.populacao_livre or 0)
        p_max = int(cid.populacao_maxima or 0)
        p_livre_fmt = f"{p_livre:,.0f}".replace(',', '.')
        p_max_fmt = f"{p_max:,.0f}".replace(',', '.')

        if p_livre > 0 or p_max > 0:
            pop_display = f"{p_livre_fmt} ({p_max_fmt})"
        else:
            pop_display = "—"

        cidades_serializadas.append({
            'nome': cid.nome,
            'posicao_na_ilha': cid.posicao_na_ilha,
            'populacao_display': pop_display,
            'ilha': {
                'coordenada_x': ilha.coordenada_x if ilha else 0,
                'coordenada_y': ilha.coordenada_y if ilha else 0,
                'tipo_recurso_luxo': ilha.tipo_recurso_luxo if ilha else '',
                'nivel_serraria': ilha.nivel_serraria if ilha else 0,
                'nivel_mina_luxo': ilha.nivel_mina_luxo if ilha else 0,
                'milagre_nome': ilha.milagre_nome if ilha else '',
                'milagre_nivel': ilha.milagre_nivel if ilha else 0
            },
            'recursos': {
                'madeira': f"{m_val:,.0f}".replace(',', '.') if m_val > 0 else "0",
                'vinho': f"{v_val:,.0f}".replace(',', '.') if v_val > 0 else "0",
                'marmore': f"{mar_val:,.0f}".replace(',', '.') if mar_val > 0 else "0",
                'cristal': f"{c_val:,.0f}".replace(',', '.') if c_val > 0 else "0",
                'enxofre': f"{e_val:,.0f}".replace(',', '.') if e_val > 0 else "0"
            }
        })

    # Totais do império formatados com pontos separadores de milhar
    recursos_imperio_calculado = {
        'madeira_formatada': f"{tot_madeira:,.0f}".replace(',', '.'),
        'vinho_formatado': f"{tot_vinho:,.0f}".replace(',', '.'),
        'marmore_formatado': f"{tot_marmore:,.0f}".replace(',', '.'),
        'cristal_formatado': f"{tot_cristal:,.0f}".replace(',', '.'),
        'enxofre_formatado': f"{tot_enxofre:,.0f}".replace(',', '.')
    }

    return jsonify({
        'servidor': conta.servidor,
        'nome_usuario': conta.nome_usuario,
        'ouro_formatado': ouro_formatado,
        'ouro_rendimento_formatado': rendimento_formatado,
        'barcos_totais': conta.barcos_totais,
        'barcos_disponiveis': conta.barcos_disponiveis,
        'recursos_imperio': recursos_imperio_calculado,
        'cidades': cidades_serializadas,
        'ultima_sincronizacao': conta.ultima_sincronizacao.strftime(
            '%d/%m/%Y %H:%M') if conta.ultima_sincronizacao else 'Nunca',
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