# app/bot/auth.py

import os
import json
import time
from app import db
from app.models import LobbyIPHistory, get_brasilia_time

SESSIONS_DIR = "sessions"
if not os.path.exists(SESSIONS_DIR):
    os.makedirs(SESSIONS_DIR)


class AuthManager:
    @staticmethod
    def _format_cookies_for_playwright(cookies_data, default_domain=".gameforge.com"):
        """
        Garante que os cookies estejam no formato exigido pelo Playwright (lista de dicionários).
        Trata o caso de vir uma string pura ("cookie=valor; ...") ou uma lista.
        """
        formatted_cookies = []

        if isinstance(cookies_data, str):
            pairs = cookies_data.split(";")
            for pair in pairs:
                if "=" in pair:
                    name, val = pair.strip().split("=", 1)
                    if name:
                        formatted_cookies.append({
                            "name": name,
                            "value": val,
                            "domain": default_domain,
                            "path": "/",
                            "httpOnly": False,
                            "secure": False,
                            "sameSite": "Lax"
                        })

        elif isinstance(cookies_data, list):
            for item in cookies_data:
                if isinstance(item, dict) and "name" in item and "value" in item:
                    cookie = {
                        "name": str(item["name"]),
                        "value": str(item["value"]),
                        "domain": item.get("domain", default_domain),
                        "path": item.get("path", "/"),
                        "httpOnly": item.get("httpOnly", False),
                        "secure": item.get("secure", False),
                        "sameSite": item.get("sameSite", "Lax")
                    }
                    formatted_cookies.append(cookie)

        return formatted_cookies

    @classmethod
    def get_session_file_path(cls, lobby_id):
        """Retorna o caminho do ficheiro JSON de sessão do lobby."""
        return os.path.join(SESSIONS_DIR, f"session_lobby_{lobby_id}.json")

    @classmethod
    def save_client_session(cls, lobby_id, cookies, local_storage):
        """Salva em disco os cookies e local_storage capturados via cliente/navegador."""
        session_file = cls.get_session_file_path(lobby_id)
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump({
                "cookies": cookies,
                "local_storage": local_storage if isinstance(local_storage, str) else json.dumps(local_storage)
            }, f)
        print(f"[Auth] Sessão do cliente gravada com sucesso para o Lobby #{lobby_id}!")

    @classmethod
    def verify_and_record_ip(cls, lobby, external_ip):
        """
        Verifica se o IP externo atual já foi utilizado por OUTRO lobby no histórico.
        Se sim, bloqueia o login. Se não, regista o IP no histórico deste lobby caso seja novo.
        """
        if not external_ip or external_ip == "Desconhecido":
            return

        # Verifica se o IP já pertence ao histórico de outro lobby diferente
        existing_record = LobbyIPHistory.query.filter(
            LobbyIPHistory.ip_address == external_ip,
            LobbyIPHistory.lobby_id != lobby.id
        ).first()

        if existing_record:
            raise Exception(
                f"[SEGURANÇA BLOQUEADA] O IP {external_ip} já foi utilizado anteriormente pelo Lobby ID #{existing_record.lobby_id}. "
                f"Por favor, troque o proxy da conta '{lobby.nickname}' (#{lobby.id}) para evitar conflito de IPs entre contas diferentes."
            )

        # Regista o IP no histórico deste lobby caso ainda não conste
        my_record = LobbyIPHistory.query.filter_by(
            lobby_id=lobby.id,
            ip_address=external_ip
        ).first()

        if not my_record:
            new_history = LobbyIPHistory(
                lobby_id=lobby.id,
                ip_address=external_ip,
                recorded_at=get_brasilia_time()
            )
            db.session.add(new_history)
            db.session.commit()
            print(f"[Auth] Novo IP {external_ip} associado e guardado no histórico do Lobby #{lobby.id}.")

    @classmethod
    def get_authenticated_context(cls, browser, lobby, proxy_config=None):
        session_file = cls.get_session_file_path(lobby.id)
        cookies = []
        local_storage = "{}"
        session_valid = False

        if os.path.exists(session_file):
            print(f"[Auth] Encontrada sessão salva para '{lobby.nickname}'. Carregando...")
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    saved_data = json.load(f)
                    cookies = saved_data.get("cookies", [])
                    local_storage = saved_data.get("local_storage", "{}")
                    if cookies:
                        session_valid = True
            except Exception as ex:
                print(f"[Auth AVISO] Erro ao ler sessão salva: {ex}.")

        if not session_valid:
            raise Exception(
                f"O Lobby '{lobby.nickname}' ainda não possui uma sessão válida salva. "
                f"Por favor, realize a primeira autenticação via painel."
            )

        # =========================================================================
        # MODO SEM PROXYS (TEMPORÁRIO) - Para reativar proxies no futuro, substitua
        # esta linha pelo bloco comentado abaixo.
        # =========================================================================
        # print(f"[Auth - MODO TESTE] Iniciando contexto SEM PROXY para '{lobby.nickname}'...")
        # proxy_context = browser.new_context()

        # [BLOCO DE PROXY ORIGINAL COMENTADO PARA FUTURA REATIVAÇÃO]

        playwright_proxy = None
        proxy_address_str = "Sem Proxy"
        if proxy_config:
            playwright_proxy = proxy_config
            proxy_address_str = proxy_config.get("server", "Personalizado")
        elif lobby.proxy:
            addr = lobby.proxy.address
            port = lobby.proxy.port
            pwd = lobby.proxy.get_password()
            proxy_address_str = f"{addr}:{port}"

            playwright_proxy = {
                "server": f"http://{proxy_address_str}"
            }
            if lobby.proxy.username and pwd:
                playwright_proxy["username"] = lobby.proxy.username
                playwright_proxy["password"] = pwd

        proxy_id_str = f"#{lobby.proxy.id}" if lobby.proxy else 'Sem Proxy'
        print(f"[Auth] Restaurando sessão com Proxy {proxy_id_str} ({proxy_address_str}) para '{lobby.nickname}'...")
        proxy_context = browser.new_context(proxy=playwright_proxy)

        temp_ip_page = proxy_context.new_page()
        external_ip = "Desconhecido"
        try:
            temp_ip_page.goto("https://api.ipify.org?format=json", timeout=15000)
            ip_data = temp_ip_page.inner_text("body")
            external_ip = json.loads(ip_data).get("ip", "Desconhecido")
        except Exception as ip_err:
            print(f"[Auth AVISO] Não foi possível verificar o IP externo: {ip_err}")
        finally:
            try:
                temp_ip_page.close()
            except:
                pass

        try:
            cls.verify_and_record_ip(lobby, external_ip)
        except Exception as sec_err:
            proxy_context.close()
            raise sec_err

        # Injeta cookies formatados no contexto
        formatted_cookies = cls._format_cookies_for_playwright(cookies)
        if formatted_cookies:
            proxy_context.add_cookies(formatted_cookies)

        page = proxy_context.new_page()

        # Tenta conectar ao Ikariam sem proxy
        try:
            print(f"[Auth] Conectando ao Ikariam utilizando o proxy configurado...")
            page.goto("https://lobby.ikariam.gameforge.com/pt_BR/", timeout=45000, wait_until="commit")
        except Exception as conn_err:
            proxy_context.close()
            raise Exception(f"Falha ao carregar a página do Ikariam: {str(conn_err)}")

        # Trata o banner de cookies se ele aparecer
        try:
            btn_cookie = page.locator("button:has-text('Accept Cookies'), button:has-text('Aceitar')").first
            if btn_cookie.is_visible(timeout=2000):
                btn_cookie.click()
        except Exception:
            pass

        # Injeta LocalStorage
        if local_storage and local_storage != "{}":
            page.evaluate(
                f"storage => {{ const data = typeof storage === 'string' ? JSON.parse(storage) : storage; for (const key in data) {{ localStorage.setItem(key, data[key]); }} }}",
                local_storage
            )

        # Atualiza para navegar autenticado para o Hub
        try:
            page.goto("https://lobby.ikariam.gameforge.com/pt_BR/hub", timeout=30000, wait_until="domcontentloaded")
        except Exception:
            pass

        # Se for redirecionado para a tela de login, a sessão do arquivo expirou
        if "login" in page.url.lower():
            if os.path.exists(session_file):
                os.remove(session_file)
            proxy_context.close()
            raise Exception(
                f"A sessão salva para o Lobby '{lobby.nickname}' expirou. Capture um novo código de sessão.")

        return proxy_context, page