# app/bot/runner.py

import threading
import time
from playwright.sync_api import sync_playwright
from app import db
from app.models import Lobby
from app.bot.auth import AuthManager
from app.bot.network import NetworkInterceptor
from app.bot.tasks.accounts_scraper import AccountsScraperTask
from app.bot.tasks.server_login import ServerLoginTask


class BotManager:
    _instances = {}
    _lock = threading.Lock()

    @classmethod
    def start_lobby(cls, lobby_id, app):
        with cls._lock:
            if lobby_id in cls._instances:
                return
            stop_event = threading.Event()
            cls._instances[lobby_id] = {"stop_event": stop_event}

        thread = threading.Thread(target=cls._run_browser, args=(lobby_id, app, stop_event))
        thread.daemon = True
        thread.start()

    @classmethod
    def _run_browser(cls, lobby_id, app, stop_event):
        with app.app_context():
            lobby = db.session.get(Lobby, lobby_id)
            if not lobby or not lobby.proxy or lobby.proxy.status != 'ATIVO':
                with cls._lock:
                    cls._instances.pop(lobby_id, None)
                return

            proxy_info = lobby.proxy
            proxy_config = {"server": f"http://{proxy_info.address}:{proxy_info.port}"}
            if proxy_info.username and proxy_info.get_password():
                proxy_config["username"] = proxy_info.username
                proxy_config["password"] = proxy_info.get_password()

            p = None
            browser = None

            try:
                p = sync_playwright().start()
                browser = p.chromium.launch(headless=False)

                # 1. Autenticação utilizando os cookies/storage_state salvos do cliente
                context, page = AuthManager.get_authenticated_context(browser, lobby, proxy_config)

                # Marca no banco que o lobby possui uma sessão ativa válida
                lobby.has_session = True
                db.session.commit()

                print(f"[BotManager] Lobby '{lobby.nickname}' rodando tarefas ativas...")

                # Loop contínuo de vida útil da instância Playwright
                while not stop_event.is_set():
                    # Reabre a sessão para verificar o status atualizado do Lobby no Banco de Dados
                    lobby_atualizado = db.session.get(Lobby, lobby_id)

                    # Se o Lobby foi inativado pelo usuário, encerra o loop da thread
                    if not lobby_atualizado or lobby_atualizado.status != 'ATIVO':
                        print(f"[BotManager] Lobby '{lobby.nickname}' inativado pelo usuário. Encerrando automação...")
                        break

                    # 2. Instancia a lista mutável de contas para captura via Network Interceptor
                    captured_accounts = []
                    NetworkInterceptor.listen_accounts_api(page, captured_accounts)

                    # 3. TASK 1: Varrida/Scraping contínuo para manter os servidores atualizados no BD
                    AccountsScraperTask.run(lobby_atualizado, page, captured_accounts)

                    # 4. TASK 2: Automação e Login nos servidores individuais com automação ativa
                    ServerLoginTask.run(lobby_atualizado, page)

                    # Intervalo entre os ciclos de verificação/automação (ajustável conforme a necessidade)
                    time.sleep(5.0)

            except Exception as e:
                print(f"[BotManager ERRO] Falha no Lobby #{lobby_id}: {e}")

                # Se a falha foi por sessão expirada/ausente, atualiza a flag no banco
                lobby_atual = db.session.get(Lobby, lobby_id)
                if lobby_atual:
                    lobby_atual.has_session = lobby_atual.is_session_valid
                    lobby_atual.status = 'ERRO'
                    db.session.commit()

            finally:
                print(f"[BotManager] Encerrando instância do Lobby #{lobby_id}...")
                try:
                    if browser:
                        browser.close()
                    if p:
                        p.stop()
                except Exception:
                    pass

                with cls._lock:
                    cls._instances.pop(lobby_id, None)

    @classmethod
    def stop_lobby(cls, lobby_id):
        with cls._lock:
            instance = cls._instances.get(lobby_id)
        if instance and "stop_event" in instance:
            instance["stop_event"].set()
            with cls._lock:
                cls._instances.pop(lobby_id, None)

    @classmethod
    def is_running(cls, lobby_id):
        with cls._lock:
            return lobby_id in cls._instances