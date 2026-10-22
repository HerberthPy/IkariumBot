# app/bot/tasks/server_login.py

import time
from flask import current_app
from app import db
from app.models import Conta, Lobby, get_brasilia_time
from app.bot.tasks.account_info import AccountInfoTask


class ServerLoginTask:
    @staticmethod
    def run(lobby, page):
        """
        Itera sobre os servidores do lobby respeitando as flags de ativação do Lobby e de cada Conta em tempo real.
        Executa os módulos na conta e fecha a aba do jogo ao concluir.
        """
        app = current_app._get_current_object()

        with app.app_context():
            def is_lobby_active():
                """Verifica em tempo real no BD se o lobby ainda deve continuar rodando."""
                if page.is_closed():
                    return False
                l_db = db.session.get(Lobby, lobby.id)
                return l_db is not None and l_db.status == 'ATIVO'

            def is_conta_active(c_id):
                """Verifica em tempo real no BD se a conta/servidor ainda tem permissão de automação."""
                if not is_lobby_active():
                    return False
                c_db = db.session.get(Conta, c_id)
                return c_db is not None and c_db.automacao_ativa and c_db.ativo

            # Busca todas as contas do lobby ativas para automação
            contas = Conta.query.filter_by(
                lobby_id=lobby.id,
                automacao_ativa=True,
                ativo=True
            ).all()

            if not contas:
                return

            context = page.context

            for conta in contas:
                # 1. Checagem de cancelamento do Lobby antes de cada conta no loop
                if not is_lobby_active():
                    print(f"[Server Login] Lobby ID {lobby.id} foi desativado ou página fechada. Cancelando execução.")
                    break

                # 2. Checagem de permissão da Conta individual em tempo real
                if not is_conta_active(conta.id):
                    print(f"[Server Login] Automação desativada para a conta {conta.nome_usuario} @ {conta.servidor}. Pulando...")
                    continue

                game_page = None
                try:
                    print(f"[Server Login] Iniciando fluxo de login para {conta.nome_usuario} @ {conta.servidor}...")

                    # 1. Navegação no Hub
                    if "/accounts" not in page.url:
                        main_play_btn = page.locator("button, a").filter(has_text="JOGAR").or_(
                            page.locator("button, a").filter(has_text="PLAY")
                        ).first

                        if main_play_btn.is_visible(timeout=3000):
                            print("[Server Login] Clicando no botão 'JOGAR' do Hub para abrir a lista de contas...")
                            main_play_btn.click()
                            try:
                                page.wait_for_url("**/accounts*", timeout=5000)
                            except Exception:
                                pass
                        else:
                            page.goto("https://lobby.ikariam.gameforge.com/pt_BR/accounts", timeout=30000, wait_until="domcontentloaded")

                        page.wait_for_timeout(1000)

                    # Re-checa flags de cancelamento após a navegação
                    if not is_conta_active(conta.id):
                        print(f"[Server Login] Parada solicitada para {conta.nome_usuario}. Cancelando antes do clique...")
                        continue

                    # 2. Localiza a linha do jogador na tabela de contas
                    row = page.locator("tr").filter(has_text=conta.nome_usuario).first

                    try:
                        row.wait_for(state="visible", timeout=5000)
                    except Exception:
                        pass

                    # 3. Localiza o botão "Jogar" correspondente ao jogador
                    play_button = row.locator("button, a").filter(
                        has_text="Jogar"
                    ).or_(
                        row.locator("button, a").filter(has_text="Play")
                    ).first

                    if not play_button.is_visible(timeout=2000):
                        play_button = page.locator("button, a").filter(
                            has_text="Jogar"
                        ).or_(
                            page.locator("button, a").filter(has_text="Play")
                        ).first

                    if not play_button.is_visible(timeout=4000):
                        print(f"[Server Login AVISO] Botão 'Jogar' não encontrado para {conta.nome_usuario}.")
                        continue

                    # Clica para abrir a nova aba do servidor do jogo
                    with context.expect_page(timeout=20000) as new_page_info:
                        play_button.click()

                    game_page = new_page_info.value

                    print(f"[Server Login] Aguardando autenticação e carregamento do jogo para {conta.nome_usuario}...")

                    try:
                        game_page.wait_for_url(
                            lambda url: "ikariam.gameforge.com" in url and ("view=" in url or "s" in url),
                            timeout=25000)
                        print(f"[Server Login] Autenticação confirmada na aba do jogo!")
                    except Exception as wait_err:
                        print(f"[Server Login AVISO] Timeout ao aguardar URL do jogo: {wait_err}")

                    # Atualiza o timestamp do último login no fuso de Brasília
                    conta_db = db.session.get(Conta, conta.id)
                    if conta_db:
                        conta_db.ultimo_login = get_brasilia_time()
                        db.session.commit()
                        print(f"[Server Login SUCESSO] Login efetuado em {conta.servidor} ({conta.nome_usuario}). Timestamp atualizado.")

                    # =========================================================================
                    # EXECUÇÃO DOS MÓDULOS DE AUTOMAÇÃO
                    # Passa o callback de verificação em tempo real da conta individual
                    # =========================================================================
                    dados_completos = AccountInfoTask.run(
                        conta.id,
                        game_page,
                        check_running_callback=lambda: is_conta_active(conta.id)
                    )

                    if dados_completos:
                        print(f"\n================ [INFORMAÇÕES DA CONTA] ================")
                        print(f" Ouro Total: {dados_completos['ouro_texto']}")
                        print(f" Barcos de Transporte: {dados_completos['barcos_transporte']}")
                        print(f" Total de Cidades: {dados_completos['qtd_cidades']}")
                        for c in dados_completos['cidades']:
                            print(f"   -> Cidade: {c['nome']} (ID: {c['id']})")
                            print(f"      Recursos: {c['recursos']}")
                        print(f"========================================================\n")
                    # =========================================================================

                except Exception as e:
                    db.session.rollback()
                    print(f"[Server Login ERRO] Falha ao realizar login no servidor {conta.servidor}: {e}")

                finally:
                    # Fecha a aba do jogo após concluir ou interromper o processamento
                    if game_page:
                        try:
                            if not game_page.is_closed():
                                print(f"[Server Login] Concluído o processamento de {conta.nome_usuario}. Fechando aba do jogo...")
                                game_page.close()
                        except Exception:
                            pass

                # --- CHECAGEM FORA DO FINALLY ---
                # Se o lobby foi desativado durante a tarefa, interrompe a navegação e sai do loop
                if not is_lobby_active():
                    print(f"[Server Login] Parada do Lobby detectada. Encerrando rotina imediatamente.")
                    break

                # Garante que a página principal esteja limpa para o próximo ciclo/lobby em /accounts
                try:
                    if not page.is_closed() and "/accounts" not in page.url:
                        page.goto("https://lobby.ikariam.gameforge.com/pt_BR/accounts", timeout=30000, wait_until="domcontentloaded")
                        page.wait_for_timeout(1000)
                except Exception:
                    pass