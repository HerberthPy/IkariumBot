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
    def get_authenticated_context(cls, browser, lobby, proxy_config):
        session_file = os.path.join(SESSIONS_DIR, f"session_lobby_{lobby.id}.json")
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
                    session_valid = True
            except Exception as ex:
                print(f"[Auth AVISO] Erro ao ler sessão salva: {ex}. Forçando novo login.")

        # FASE 1: Login sem Proxy (quando não há sessão válida)
        if not session_valid:
            print(f"[Auth] Executando FASE 1 (Login sem Proxy) para '{lobby.nickname}'...")
            clean_context = browser.new_context()
            login_page = clean_context.new_page()

            print(f"[Auth IP] FASE 1 - IP Real: {cls._get_current_ip(login_page)}")

            login_page.goto("https://lobby.ikariam.gameforge.com/pt_BR/", timeout=30000, wait_until="networkidle")

            # Aceita Cookies se o banner estiver visível
            try:
                btn_cookie = login_page.locator("button:has-text('Accept Cookies'), button:has-text('Aceitar')").first
                if btn_cookie.is_visible(timeout=3000):
                    btn_cookie.click()
            except Exception:
                pass

            login_page.get_by_text("Login").click()
            login_page.locator("input[name=\"email\"]").fill(lobby.email)
            login_page.locator("input[name=\"password\"]").fill(lobby.get_password())
            login_page.get_by_role("button", name="Login", exact=True).click()

            # Trata Captcha se surgir
            login_page.wait_for_timeout(2000)
            geetest_selector = ".geetest_slider, .geetest_box, [class*='geetest']"
            try:
                if login_page.locator(geetest_selector).first.is_visible(timeout=3000):
                    print(f"[Auth AVISO] Captcha detectado para '{lobby.nickname}'! Aguardando resolução...")
                    login_page.locator(geetest_selector).first.wait_for(state="detached", timeout=120000)
            except Exception:
                pass

            login_page.wait_for_url("**/hub**", timeout=45000)
            login_page.wait_for_load_state("networkidle")

            cookies = clean_context.cookies()
            local_storage = login_page.evaluate("() => JSON.stringify(localStorage)")
            clean_context.close()

            with open(session_file, "w", encoding="utf-8") as f:
                json.dump({"cookies": cookies, "local_storage": local_storage}, f)
            print(f"[Auth] Nova sessão gravada em disco para '{lobby.nickname}'!")

        # FASE 2: Restauração via Proxy
        print(f"[Auth] Executando FASE 2 (Com Proxy) para '{lobby.nickname}'...")
        proxy_context = browser.new_context(proxy=proxy_config)
        if cookies:
            proxy_context.add_cookies(cookies)

        page = proxy_context.new_page()
        print(f"[Auth IP] FASE 2 - IP da Proxy #{lobby.proxy.id}: {cls._get_current_ip(page)}")

        # Navega para a origem antes de injetar o localStorage
        page.goto("https://lobby.ikariam.gameforge.com/pt_BR/", timeout=30000, wait_until="domcontentloaded")

        # Aceita cookies se surgir
        try:
            btn_cookie = page.locator("button:has-text('Accept Cookies'), button:has-text('Aceitar')").first
            if btn_cookie.is_visible(timeout=3000):
                btn_cookie.click()
        except Exception:
            pass

        # Injeta LocalStorage
        page.evaluate(
            f"storage => {{ const data = JSON.parse(storage); for (const key in data) {{ localStorage.setItem(key, data[key]); }} }}",
            local_storage
        )

        return proxy_context, page