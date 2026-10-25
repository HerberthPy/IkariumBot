# app/bot/tasks/account_info.py
import re

from app.bot.utils.human import HumanBehavior

class AccountInfoTask:

    @staticmethod
    def _clean_number(text: str) -> int:
        if not text:
            return 0
        cleaned = re.sub(r"[^\d]", "", text)
        return int(cleaned) if cleaned else 0

    @classmethod
    def _get_resource_value(cls, game_page, selectors) -> int:
        for selector in selectors:
            try:
                loc = game_page.locator(selector)
                if loc.is_visible(timeout=2000):
                    text = loc.inner_text()
                    val = cls._clean_number(text)
                    if val >= 0:
                        return val
            except Exception:
                pass
        return 0

    @classmethod
    def run(cls, conta_id: int, game_page, check_running_callback=None):
        print(f"[Account Info] Coletando informações completas para a conta ID {conta_id}...")

        try:
            game_page.wait_for_selector("#topnavi", timeout=20000)
            HumanBehavior.random_sleep(2.0, 3.5)

            # =========================================================================
            # LIMPEZA INICIAL: FECHAR POP-UPS DE ANÚNCIO E COOKIES
            # =========================================================================
            try:
                print("[Game Cleaner] Verificando pop-ups de anúncio e banner de cookies...")

                close_btn = game_page.locator(
                    "button:has-text('Close'), a:has-text('Close'), button:has-text('Fechar'), a:has-text('Fechar'), .closeBtn, .ui-dialog-titlebar-close").first
                if close_btn.is_visible(timeout=2500):
                    close_btn.click()
                    print("[Game Cleaner] Pop-up de anúncio fechado com sucesso.")
                    HumanBehavior.random_sleep(0.6, 1.0)

                cookie_btn = game_page.locator(
                    "button:has-text('Aceitar Cookies'), button:has-text('Accept Cookies'), #cookie-consent button, button[id*='cookie']").first
                if cookie_btn.is_visible(timeout=1500):
                    cookie_btn.click()
                    print("[Game Cleaner] Banner de cookies aceito/fechado com sucesso.")
                    HumanBehavior.random_sleep(0.4, 0.8)

            except Exception as cleaner_err:
                print(f"[Game Cleaner Aviso] Nenhum pop-up ou cookie bloqueando a tela: {cleaner_err}")

            # Captura o texto dos elementos diretamente pelos IDs exatos
            barcos_livres = int(game_page.locator("#js_GlobalMenu_freeTransporters").inner_text().strip())
            barcos_totais = int(game_page.locator("#js_GlobalMenu_maxTransporters").inner_text().strip())

            # Formato string se precisar
            transporters_text = f"{barcos_livres} ({barcos_totais})"
            print(transporters_text)

            # 2. Mapeamento e Varredura de Cidades
            drop_btn_selector = "#js_citySelectContainer .dropDownButton"
            cidades_info = []
            cidades_data = []

            try:
                if game_page.locator(drop_btn_selector).is_visible(timeout=4000):
                    HumanBehavior.human_click(game_page, drop_btn_selector)
                    HumanBehavior.random_sleep(1.0, 1.5)

                    cidades_data = game_page.evaluate("""
                        () => {
                            let list = [];
                            let items = document.querySelectorAll("li.ownCity, #dropDown_js_citySelectContainer li.ownCity");
                            items.forEach((li) => {
                                let selectVal = li.getAttribute("selectvalue");
                                let aTag = li.querySelector("a");
                                let name = aTag ? aTag.innerText.trim() : li.innerText.trim();
                                if (selectVal && name) {
                                    name = name.split("\\n")[0].trim();
                                    list.push({ id: selectVal, name: name });
                                }
                            });
                            return list;
                        }
                    """)

                    try:
                        game_page.keyboard.press("Escape")
                        HumanBehavior.random_sleep(0.4, 0.7)
                    except Exception:
                        pass
            except Exception as err:
                print(f"[Account Info AVISO] Falha ao listar cidades via dropdown: {err}")

            if cidades_data:
                print(f"[Account Info] Cidades válidas mapeadas com sucesso: {len(cidades_data)}")

                for idx, city in enumerate(cidades_data):
                    if check_running_callback and not check_running_callback():
                        break

                    city_id = city["id"]
                    city_name = city["name"]

                    print(
                        f"[Account Info] Acessando cidade [{idx + 1}/{len(cidades_data)}]: {city_name} (ID: {city_id})...")

                    try:
                        game_page.goto(f"https://{game_page.url.split('/')[2]}/index.php?view=city&cityId={city_id}",
                                       timeout=30000, wait_until="domcontentloaded")
                        HumanBehavior.random_sleep(3.5, 5.0)
                    except Exception as nav_err:
                        print(f"[Account Info AVISO] Falha ao navegar diretamente para a cidade {city_name}: {nav_err}")
                        continue

                    wood = cls._get_resource_value(game_page, ["#js_GlobalMenu_wood"])
                    wine = cls._get_resource_value(game_page, ["#js_GlobalMenu_wine"])
                    marble = cls._get_resource_value(game_page, ["#js_GlobalMenu_marble"])
                    glass = cls._get_resource_value(game_page, ["#js_GlobalMenu_glass", "#js_GlobalMenu_crystal"])
                    sulfur = cls._get_resource_value(game_page, ["#js_GlobalMenu_sulfur"])

                    c_livres = "0"
                    c_totais = "0"
                    try:
                        pop_metrics = game_page.evaluate(r"""() => {
                            const citEl = document.querySelector('#js_GlobalMenu_citizens');
                            const popEl = document.querySelector('#js_GlobalMenu_population');

                            return {
                                livres: citEl ? citEl.innerText.trim() : '0',
                                totais: popEl ? popEl.innerText.trim() : '0'
                            };
                        }""")

                        if pop_metrics:
                            c_livres = pop_metrics.get('livres', '0')
                            c_totais = pop_metrics.get('totais', '0')
                    except Exception:
                        pass

                    cidades_info.append({
                        "id": f"cidade_{idx + 1}",
                        "nome": city_name,
                        "cidadaos_livres": c_livres,
                        "cidadaos_totais": c_totais,
                        "recursos": {
                            "madeira": f"{wood:,}".replace(",", "."),
                            "vinho": f"{wine:,}".replace(",", "."),
                            "marmore": f"{marble:,}".replace(",", "."),
                            "cristal": f"{glass:,}".replace(",", "."),
                            "enxofre": f"{sulfur:,}".replace(",", ".")
                        }
                    })
            else:
                print("Recursos não coletados.")

            # 3. COLETA DO OURO E RENDIMENTO POR ÚLTIMO

            # Aguarda o modal carregar completamente
            HumanBehavior.random_sleep(3.0, 4.5)
            exact_gold = "0"
            rendimento_exato = "+0/h"
            HumanBehavior.human_click(game_page, "#js_GlobalMenu_gold")
            try:
                # 1. Captura o ouro total exato na célula de recursos
                exact_gold = game_page.locator("td.nowrap.res div.tooltip").first.inner_text(timeout=3000).strip()
                print(f"Ouro total exato: {exact_gold.strip()}")
            except Exception as e:
                print(f"Não foi possível capturar o ouro total: {e}")

            try:
                # 2. Captura o rendimento exato na linha de resultado (tr.result)
                rendimento_exato = game_page.locator("tr.result td.nowrap div.tooltip").nth(2).inner_text(timeout=3000).strip()
                print(f"Rendimento exato: {rendimento_exato.strip()}")
            except Exception as e:
                print(f"Não foi possível capturar o rendimento exato: {e}")

            # Fecha o modal pressionando Escape ou clicando no botão de fechar
            try:
                close_btn = game_page.locator(".dynamic_popup .close, .dialog .close, [title*='Fechar']").first
                if close_btn.is_visible(timeout=1000):
                    close_btn.click()
                else:
                    game_page.keyboard.press("Escape")
                HumanBehavior.random_sleep(0.5, 0.8)
            except:
                game_page.keyboard.press("Escape")

            ouro_limpo = str(cls._clean_number(exact_gold))
            rendimento_limpo = str(cls._clean_number(rendimento_exato))

            info = {
                "qtd_cidades": len(cidades_info),
                "ouro": ouro_limpo,
                "ouro_rendimento": rendimento_limpo,
                "barcos_disponiveis": barcos_livres,
                "barcos_totais": barcos_totais,
                "barcos_transporte": transporters_text.strip(),
                "cidades": cidades_info
            }

            HumanBehavior.random_sleep(4.0, 6.0)
            print(
                f"[Account Info SUCESSO] Extração concluída | Ouro: {info['ouro']} ({info['ouro_rendimento']}) | Barcos: {barcos_livres}/{barcos_totais}")
            return info

        except Exception as e:
            print(f"[Account Info ERRO] {e}")
            return None