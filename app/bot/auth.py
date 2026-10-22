# app/bot/auth.py

import os
import json
import time

SESSIONS_DIR = "sessions"
if not os.path.exists(SESSIONS_DIR):
    os.makedirs(SESSIONS_DIR)


class AuthManager:
    @staticmethod
    def _get_current_ip(page):
        try:
            response = page.goto("https://api.ipify.org?format=json", timeout=10000)
            if response and response.ok:
                data = json.loads(page.inner_text("body"))
                return data.get("ip", "IP Desconhecido")
        except Exception as e:
            return f"Erro ao verificar IP: {e}"
        return "IP Não Obtido"

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

        # Se não houver sessão salva do cliente, interrompe a automação pedindo a autenticação
        if not session_valid:
            raise Exception(
                f"O Lobby '{lobby.nickname}' ainda não possui uma sessão válida salva. "
                f"Por favor, realize a primeira autenticação via painel para resolver eventuais CAPTCHAs."
            )

        # FASE UNIFICADA: Restauração da Sessão via Proxy
        print(f"[Auth] Restaurando sessão com Proxy para '{lobby.nickname}'...")
        proxy_context = browser.new_context(proxy=proxy_config)

        if cookies:
            proxy_context.add_cookies(cookies)

        page = proxy_context.new_page()
        print(f"[Auth IP] Proxy #{lobby.proxy.id if lobby.proxy else 'Sem Proxy'}: {cls._get_current_ip(page)}")

        # Navega para a origem do lobby para aplicar o localStorage
        page.goto("https://lobby.ikariam.gameforge.com/pt_BR/", timeout=30000, wait_until="domcontentloaded")

        # Aceita cookies se o banner da Gameforge surgir
        try:
            btn_cookie = page.locator("button:has-text('Accept Cookies'), button:has-text('Aceitar')").first
            if btn_cookie.is_visible(timeout=3000):
                btn_cookie.click()
        except Exception:
            pass

        # Injeta LocalStorage
        if local_storage and local_storage != "{}":
            page.evaluate(
                f"storage => {{ const data = typeof storage === 'string' ? JSON.parse(storage) : storage; for (const key in data) {{ localStorage.setItem(key, data[key]); }} }}",
                local_storage
            )

        # Atualiza para garantir navegação autenticada no Hub
        page.goto("https://lobby.ikariam.gameforge.com/pt_BR/hub", timeout=30000, wait_until="domcontentloaded")

        # Verifica se o login permaneceu ativo ou se os cookies expiraram
        if "login" in page.url.lower():
            # Apaga o arquivo de sessão expirado para forçar novo login pelo usuário
            if os.path.exists(session_file):
                os.remove(session_file)
            proxy_context.close()
            raise Exception(f"A sessão salva para o Lobby '{lobby.nickname}' expirou. Faça login novamente no painel.")

        return proxy_context, page