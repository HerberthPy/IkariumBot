# app/bot/auth.py

import os
import json
from app.bot.utils.ui_cleaner import UICleaner
from app.bot.utils import BotLogger

logger = BotLogger.get_logger()

SESSIONS_DIR = "sessions"
if not os.path.exists(SESSIONS_DIR):
    os.makedirs(SESSIONS_DIR)


class AuthManager:
    @staticmethod
    def _format_cookies_for_playwright(cookies_data, default_domain=".gameforge.com"):
        """Formata os cookies no formato exigido pelo Playwright."""
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
        """Retorna o caminho completo para o arquivo JSON da sessão do lobby."""
        return os.path.join(SESSIONS_DIR, f"session_lobby_{lobby_id}.json")

    @classmethod
    def save_client_session(cls, lobby_id, cookies, local_storage):
        """Salva os cookies e o local storage do lobby no disco."""
        session_file = cls.get_session_file_path(lobby_id)
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump({
                "cookies": cookies,
                "local_storage": local_storage if isinstance(local_storage, str) else json.dumps(local_storage)
            }, f)
        logger.info(f"[Auth] Sessão gravada com sucesso para o Lobby #{lobby_id}!")

    @classmethod
    async def get_authenticated_context(cls, browser, lobby, proxy_config=None):
        """
        Realiza a autenticação básica, injeta os cookies e localStorage,
        e abre a página base do Gameforge Lobby de forma assíncrona.
        """
        session_file = cls.get_session_file_path(lobby.id)
        cookies = []
        local_storage = "{}"
        session_valid = False

        if os.path.exists(session_file):
            logger.info(f"[Auth] Carregando sessão salva para '{lobby.nickname}'...")
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    saved_data = json.load(f)
                    cookies = saved_data.get("cookies", [])
                    local_storage = saved_data.get("local_storage", "{}")
                    if cookies:
                        session_valid = True
            except Exception as ex:
                logger.warning(f"[Auth] Erro ao ler sessão salva: {ex}.")

        if not session_valid:
            raise Exception(
                f"O Lobby '{lobby.nickname}' ainda não possui uma sessão válida salva. "
                f"Por favor, cadastre ou atualize a sessão pelo painel."
            )

        logger.info(f"[Auth] Iniciando contexto do navegador para '{lobby.nickname}'...")
        proxy_context = await browser.new_context()

        # Injeta os cookies
        formatted_cookies = cls._format_cookies_for_playwright(cookies)
        if formatted_cookies:
            await proxy_context.add_cookies(formatted_cookies)

        page = await proxy_context.new_page()

        # Acessa a raiz do lobby
        try:
            logger.info(f"[Auth] Conectando ao painel base do Ikariam...")
            await page.goto("https://lobby.ikariam.gameforge.com/pt_BR/", timeout=45000, wait_until="commit")
        except Exception as conn_err:
            await proxy_context.close()
            raise Exception(f"Falha ao carregar a página do Ikariam: {str(conn_err)}")

        # Limpa banners e popups iniciais
        await UICleaner.dismiss_popups_and_banners(page)

        # Injeta o LocalStorage salvo
        if local_storage and local_storage != "{}":
            await page.evaluate(
                f"storage => {{ const data = typeof storage === 'string' ? JSON.parse(storage) : storage; for (const key in data) {{ localStorage.setItem(key, data[key]); }} }}",
                local_storage
            )

        return proxy_context, page