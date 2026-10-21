import threading
import time
from playwright.sync_api import sync_playwright
from app import db
from app.models import Lobby


class BotManager:
    """Gerenciador central de instâncias do Playwright em memória com sinalização limpa."""
    _instances = {}
    _lock = threading.Lock()

    @classmethod
    def start_lobby(cls, lobby_id, app):
        with cls._lock:
            if lobby_id in cls._instances:
                print(f"[BotManager] Lobby ID {lobby_id} já está marcado como em execução.")
                return

            # Registra o evento de parada IMEDIATAMENTE no dicionário
            stop_event = threading.Event()
            cls._instances[lobby_id] = {
                "stop_event": stop_event
            }

        thread = threading.Thread(
            target=cls._run_browser,
            args=(lobby_id, app, stop_event)
        )
        thread.daemon = True
        thread.start()

    @classmethod
    def _run_browser(cls, lobby_id, app, stop_event):
        with app.app_context():
            lobby = Lobby.query.get(lobby_id)
            if not lobby:
                print(f"[BotManager ERRO] Lobby ID {lobby_id} não foi encontrado.")
                with cls._lock:
                    cls._instances.pop(lobby_id, None)
                return

            if not lobby.proxy or lobby.proxy.status != 'ATIVO':
                print(f"[BotManager ERRO] Proxy indisponível para o Lobby '{lobby.nickname}' (#ID {lobby.id}).")
                lobby.status = 'ERRO'
                db.session.commit()
                with cls._lock:
                    cls._instances.pop(lobby_id, None)
                return

            proxy_info = lobby.proxy
            proxy_config = {
                "server": f"http://{proxy_info.address}:{proxy_info.port}"
            }
            if proxy_info.username and proxy_info.get_password():
                proxy_config["username"] = proxy_info.username
                proxy_config["password"] = proxy_info.get_password()

            print(f"[BotManager] Iniciando navegador para Lobby '{lobby.nickname}' (#ID {lobby.id})...")

            p = None
            browser = None

            try:
                p = sync_playwright().start()
                browser = p.chromium.launch(headless=False)
                context = browser.new_context(proxy=proxy_config)
                page = context.new_page()

                # Abre a página de teste / jogo
                page.goto("https://www.whatismyip.com", timeout=30000, wait_until="domcontentloaded")
                print(f"[BotManager] Lobby '{lobby.nickname}' conectado ao site com sucesso!")

                # Aguarda até que a flag de parada seja acionada
                while not stop_event.is_set():
                    time.sleep(0.5)

            except Exception as e:
                print(f"[BotManager ERRO] Falha no Lobby #{lobby_id}: {e}")
                lobby.status = 'ERRO'
                db.session.commit()

            finally:
                print(f"[BotManager] Encerrando navegador do Lobby #{lobby_id}...")
                try:
                    if browser:
                        browser.close()
                    if p:
                        p.stop()
                except Exception as ex:
                    print(f"[BotManager AVISO] Erro ao fechar browser do Lobby #{lobby_id}: {ex}")

                # Garante a remoção final da memória
                with cls._lock:
                    cls._instances.pop(lobby_id, None)

                print(f"[BotManager] Lobby #{lobby_id} removido da memória.")

    @classmethod
    def stop_lobby(cls, lobby_id):
        """Ativa a flag de parada e remove a referência para atualizar a UI imediatamente."""
        with cls._lock:
            instance = cls._instances.get(lobby_id)

        if instance and "stop_event" in instance:
            print(f"[BotManager] Sinalizando parada para o Lobby ID {lobby_id}...")
            instance["stop_event"].set()

            # Remove imediatamente da memória para que a tela não exiba 'Rodando'
            with cls._lock:
                cls._instances.pop(lobby_id, None)
        else:
            print(f"[BotManager] Nenhuma instância ativa encontrada para o Lobby ID {lobby_id}.")

    @classmethod
    def is_running(cls, lobby_id):
        with cls._lock:
            return lobby_id in cls._instances