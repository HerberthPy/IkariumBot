from playwright.sync_api import sync_playwright
import time


def login_proton_vpn(email, password, headless=False):
    """
    Inicia o navegador e realiza o login na Proton VPN.
    """
    with sync_playwright() as p:
        # Lança o navegador (Chromium/Chrome)
        browser = p.chromium.launch(headless=headless)  # headless=False para ver o navegador abrindo
        context = browser.new_context()
        page = context.new_page()

        print(f"[*] Abrindo página de login do Proton para a conta: {email}")
        page.goto("https://account.proton.me/login")

        # Aguarda os campos estarem visíveis e realiza o preenchimento
        page.wait_for_selector("#username")
        page.fill("#username", email)

        page.wait_for_selector("#password")
        page.fill("#password", password)

        # Clica no botão de Submit
        page.click("button[type='submit']")

        # Aguarda navegação pós-login (ajuste o seletor ou tempo conforme necessário)
        page.wait_for_load_state("networkidle")
        print("[+] Login efetuado com sucesso (ou aguardando verificação 2FA se houver).")

        # Mantém aberto por alguns segundos para validação inicial
        time.sleep(5)

        # Fecha o navegador
        browser.close()


if __name__ == "__main__":
    # Teste isolado do script
    login_proton_vpn("seu_usuario_proton", "sua_senha_proton", headless=False)