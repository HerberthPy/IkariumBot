# app/bot/auth.py

import os
import json
import time

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
    def get_authenticated_context(cls, browser, lobby, proxy_config):
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

        print(f"[Auth] Restaurando sessão com Proxy para '{lobby.nickname}'...")
        proxy_context = browser.new_context(proxy=proxy_config)

        # Injeta cookies formatados no contexto
        formatted_cookies = cls._format_cookies_for_playwright(cookies)
        if formatted_cookies:
            proxy_context.add_cookies(formatted_cookies)

        page = proxy_context.new_page()

        # Tenta conectar ao Ikariam com timeout controlado
        try:
            print(f"[Auth] Conectando ao Ikariam através da Proxy #{lobby.proxy.id if lobby.proxy else 'Sem Proxy'}...")
            page.goto("https://lobby.ikariam.gameforge.com/pt_BR/", timeout=20000, wait_until="domcontentloaded")
        except Exception as conn_err:
            proxy_context.close()
            raise Exception(f"A Proxy #{lobby.proxy.id if lobby.proxy else 'N/A'} falhou ou não respondeu a tempo (Timeout). Verifique se a proxy está ativa.")

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
            page.goto("https://lobby.ikariam.gameforge.com/pt_BR/hub", timeout=20000, wait_until="domcontentloaded")
        except Exception:
            pass

        # Se for redirecionado para a tela de login, a sessão do arquivo expirou
        if "login" in page.url.lower():
            if os.path.exists(session_file):
                os.remove(session_file)
            proxy_context.close()
            raise Exception(f"A sessão salva para o Lobby '{lobby.nickname}' expirou. Capture um novo código de sessão.")

        return proxy_context, page