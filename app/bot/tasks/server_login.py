# app/bot/tasks/server_login.py

import time
from flask import current_app
from app import db
from app.models import Conta, Lobby, get_brasilia_time
from app.bot.auth import AuthManager
from app.bot.tasks.account_info import AccountInfoTask


class ServerLoginTask:
    @staticmethod
    def run_and_get_info(lobby_id, conta_id):
        """
        Faz o login estritamente na conta ativa do lobby utilizando a sessão e o proxy correspondentes,
        executa a extração de informações da conta e retorna o resultado.
        """
        app = current_app._get_current_object()

        with app.app_context():
            lobby = db.session.get(Lobby, lobby_id)
            if not lobby or lobby.status != 'ATIVO':
                print(f"[Server Login] Lobby ID {lobby_id} não encontrado ou inativo.")
                return False, None

            conta = db.session.get(Conta, conta_id)
            if not conta:
                print(f"[Server Login] Conta ID {conta_id} não encontrada.")
                return False, None

            print(f"[Server Login] Iniciando fluxo de login para a conta: {conta.nome_usuario} @ {conta.servidor}...")

            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False) # Mude para False se quiser ver o navegador a abrir visualmente
                game_page = None
                context = None

                try:
                    # Utiliza o AuthManager para autenticar com a sessão e proxy salvos do lobby
                    context, page = AuthManager.get_authenticated_context(browser, lobby, proxy_config=None)

                    # Navega diretamente para a lista de contas no Hub do Ikariam
                    page.goto("https://lobby.ikariam.gameforge.com/pt_BR/accounts", timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

                    # Localiza a linha do jogador na tabela de contas
                    row = page.locator("tr").filter(has_text=conta.nome_usuario).first
                    try:
                        row.wait_for(state="visible", timeout=5000)
                    except Exception:
                        pass

                    # Localiza o botão "Jogar" correspondente à conta
                    play_button = row.locator("button, a").filter(
                        has_text="Jogar"
                    ).or_(
                        row.locator("button, a").filter(has_text="Play")
                    ).first

                    if not play_button.is_visible(timeout=4000):
                        play_button = page.locator("button, a").filter(
                            has_text="Jogar"
                        ).or_(
                            page.locator("button, a").filter(has_text="Play")
                        ).first

                    if not play_button.is_visible(timeout=4000):
                        print(f"[Server Login AVISO] Botão 'Jogar' não encontrado para a conta {conta.nome_usuario}.")
                        return False, None

                    # Clica para abrir a nova aba do servidor do jogo
                    with context.expect_page(timeout=20000) as new_page_info:
                        play_button.click()

                    game_page = new_page_info.value

                    print(f"[Server Login] Aguardando carregamento do jogo para {conta.nome_usuario}...")

                    try:
                        game_page.wait_for_url(
                            lambda url: "ikariam.gameforge.com" in url and ("view=" in url or "s" in url),
                            timeout=25000
                        )
                        print(f"[Server Login SUCESSO] Login efetuado com sucesso no mundo {conta.servidor}!")
                    except Exception as wait_err:
                        print(f"[Server Login AVISO] Timeout ao aguardar URL do jogo: {wait_err}")

                    # Atualiza o timestamp do último login no fuso de Brasília
                    conta.ultimo_login = get_brasilia_time()
                    conta.ultima_sincronizacao = get_brasilia_time()
                    db.session.commit()

                    # =========================================================================
                    # EXECUTAR O MÓDULO DE INFORMAÇÕES DA CONTA
                    # =========================================================================
                    print(f"[Server Login] Extraindo dados da conta com AccountInfoTask...")
                    dados_completos = AccountInfoTask.run(
                        conta.id,
                        game_page,
                        check_running_callback=lambda: True
                    )

                    if dados_completos:
                        return True, dados_completos
                    else:
                        print(f"[Server Login AVISO] A tarefa concluiu mas não retornou dados estruturados.")
                        return False, None

                except Exception as e:
                    print(f"[Server Login ERRO] Falha durante o login ou extração: {e}")
                    return False, None

                finally:
                    if game_page:
                        try:
                            if not game_page.is_closed():
                                game_page.close()
                        except Exception:
                            pass
                    if context:
                        try:
                            context.close()
                        except Exception:
                            pass
                    try:
                        browser.close()
                    except Exception:
                        pass