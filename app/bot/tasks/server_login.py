# app/bot/tasks/server_login.py

import time
import re
from flask import current_app
from app import db
from app.models import Conta, Lobby, get_brasilia_time
from app.bot.auth import AuthManager
from app.bot.tasks.account_info import AccountInfoTask


class ServerLoginTask:
    @staticmethod
    def run_and_get_info(lobby_id, conta_id):
        """
        Faz o login estritamente na conta ativa do lobby utilizando a estrutura exata
        da tabela React do lobby da GameForge (div.rt-tr-group).
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
                browser = p.chromium.launch(headless=False)  # Mude para True se quiser rodar oculto
                game_page = None
                context = None

                try:
                    # Utiliza o AuthManager para autenticar com a sessão e proxy salvos do lobby
                    context, page = AuthManager.get_authenticated_context(browser, lobby, proxy_config=None)

                    # Navega diretamente para a lista de contas no Hub do Ikariam
                    page.goto("https://lobby.ikariam.gameforge.com/pt_BR/accounts", timeout=30000,
                              wait_until="domcontentloaded")

                    # Aguarda a tabela React carregar completamente na tela
                    print(f"[Server Login] Aguardando renderização da tabela React de contas...")
                    try:
                        page.wait_for_selector("div.rt-tr-group", timeout=10000)
                    except Exception:
                        pass
                    page.wait_for_timeout(2000)

                    play_button = None
                    target_user = str(conta.nome_usuario).strip().lower()
                    target_server = str(conta.servidor).strip().lower()

                    print(
                        f"[Server Login] Procurando linha da conta: Servidor='{target_server}', Utilizador='{target_user}'...")

                    # Pega todas as linhas da tabela React (.rt-tr-group)
                    rows = page.locator("div.rt-tr-group").all()

                    for row in rows:
                        try:
                            # Extrai o texto da célula do servidor e do jogador dentro desta linha específica
                            server_elem = row.locator("div.server-name-cell").inner_text().strip().lower()
                            player_elem = row.locator("div.player-cell").inner_text().strip().lower()

                            # Verifica se ambos conferem exatamente com a conta alvo
                            if target_server in server_elem and target_user in player_elem:
                                # Encontrou a linha exata! Agora localiza o botão "Jogar" na célula de ação (`action-cell`)
                                btn = row.locator("div.action-cell button, div.action-cell a").filter(
                                    has_text=re.compile("Jogar|Play", re.IGNORECASE)).first
                                if btn.is_visible(timeout=500):
                                    play_button = btn
                                    print(
                                        f"[Server Login SUCESSO] Linha e botão 'Jogar' isolados com precisão para {conta.nome_usuario} ({conta.servidor})!")
                                    break
                        except Exception:
                            continue

                    # Fallback caso os seletores específicos de células mudem: varredura genérica de texto na linha
                    if not play_button or not play_button.is_visible(timeout=500):
                        print(
                            f"[Server Login AVISO] Busca por células específicas falhou. Tentando varredura geral de texto nas linhas...")
                        for row in rows:
                            try:
                                row_text = row.inner_text().lower()
                                if target_server in row_text and target_user in row_text:
                                    btn = row.locator("button, a").filter(
                                        has_text=re.compile("Jogar|Play", re.IGNORECASE)).first
                                    if btn.is_visible(timeout=500):
                                        play_button = btn
                                        print(
                                            f"[Server Login SUCESSO] Botão encontrado na varredura geral de texto da linha!")
                                        break
                            except Exception:
                                continue

                    if not play_button or not play_button.is_visible(timeout=4000):
                        print(
                            f"[Server Login ERRO] Botão 'Jogar' não pôde ser encontrado na tabela para a conta {conta.nome_usuario} ({conta.servidor}).")
                        return False, None

                    # Clica para abrir a nova aba do servidor do jogo
                    with context.expect_page(timeout=20000) as new_page_info:
                        play_button.click()

                    game_page = new_page_info.value

                    print(
                        f"[Server Login] Aguardando carregamento do jogo para {conta.nome_usuario} ({conta.servidor})...")

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