# app/bot/utils/ui_cleaner.py

class UICleaner:
    @staticmethod
    async def dismiss_popups_and_banners(page):
        """
        Varre a página em busca de banners de cookies, modais, avisos de termos,
        popups promocionais ou bônus diários e os fecha/dispensa automaticamente (Assíncrono).
        """
        try:
            # Lista ampla de seletores comuns para cookies, popups, modais, bônus diários e avisos na Gameforge/Ikariam
            selectors = [
                "button:has-text('Fechar')",
                "a:has-text('Fechar')",
                "button:has-text('Accept Cookies')",
                "button:has-text('Aceitar')",
                "button:has-text('Akzeptieren')",
                "button:has-text('Close')",
                ".dynamic_popup .close",
                ".dialog .close",
                "[title*='Fechar']",
                ".modal-close",
                "button#consentCookie",
                ".cookie-banner-btn",
                "div[id*='cookie'] button",
                "div[class*='popup'] button[class*='close']",
                "div[class*='modal'] button[class*='close']"
            ]

            for selector in selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        print(f"[UICleaner] Elemento intrusivo dispensado com sucesso usando o seletor: {selector}")
                        await page.wait_for_timeout(500)  # Pequena pausa para estabilizar a interface
                except Exception:
                    continue

            # Tenta pressionar ESC para fechar eventuais modais restantes que aceitem atalho de teclado
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

        except Exception:
            # Silencia caso nenhum elemento esteja visível ou ocorra timeout
            pass