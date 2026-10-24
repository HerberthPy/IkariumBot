# app/bot/tasks/account_info.py

import re
import time
from app.bot.utils.human import HumanBehavior


class AccountInfoTask:
    @staticmethod
    def _clean_number(text: str) -> int:
        if not text:
            return 0
        cleaned = re.sub(r"[^\d]", "", text)
        return int(cleaned) if cleaned else 0

    @staticmethod
    def _parse_gold(text: str) -> float:
        if not text:
            return 0.0
        text = text.strip()
        if "M" in text or "m" in text:
            num_part = re.sub(r"[^\d.]", "", text.replace(",", "."))
            return float(num_part) * 1_000_000 if num_part else 0.0
        if "K" in text or "k" in text:
            num_part = re.sub(r"[^\d.]", "", text.replace(",", "."))
            return float(num_part) * 1_000 if num_part else 0.0
        return float(AccountInfoTask._clean_number(text))

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
            game_page.wait_for_selector("#globalResources", timeout=20000)
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

            # 1. Leitura de Ouro Total
            gold_text = ""
            try:
                if game_page.locator("#js_GlobalMenu_gold").is_visible(timeout=3000):
                    gold_text = game_page.locator("#js_GlobalMenu_gold").inner_text()
            except Exception:
                pass

            # 2. Abertura da janela de quantias de ouro para ler o rendimento exato
            gold_rendimento = "+0/h"
            try:
                print("[Account Info] Clicando no ouro para abrir o modal de quantias...")

                modal_opened = game_page.evaluate(r"""() => {
                    const selectors = [
                        '#js_GlobalMenu_gold',
                        '.gold a',
                        'a[href*="finances"]',
                        '.gold',
                        '#gold'
                    ];
                    for (let sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const clickable = el.closest('a') || el.parentElement.querySelector('a') || el;
                            clickable.click();
                            return true;
                        }
                    }
                    return false;
                }""")

                if modal_opened:
                    HumanBehavior.random_sleep(1.5, 2.2)

                    rend_data = game_page.evaluate(r"""() => {
                        const rows = document.querySelectorAll('tr, div.row, div.contentBox, div.content');
                        let totalVal = '';

                        for (let row of rows) {
                            const text = row.innerText || '';
                            if (text.includes('Total') && (text.includes('Rendimento') || text.includes('Manutenção') || /\d/.test(text))) {
                                const match = text.match(/Total[^\d\-]*([\+\-\d\.,]+)/i);
                                if (match && match[1]) {
                                    totalVal = match[1].trim();
                                    break;
                                }
                            }
                        }

                        if (!totalVal) {
                            const modal = document.querySelector('.dynamic_popup, #js_Dialog, .contentBox, body');
                            if (modal) {
                                const mText = modal.innerText;
                                const m = mText.match(/Total[^\d\-]*([\+\-\d\.,]+)/i);
                                if (m) totalVal = m[1].trim();
                            }
                        }

                        return totalVal;
                    }""")

                    if rend_data:
                        val_clean = rend_data.replace('.', '').replace(',', '.')
                        if not val_clean.startswith('+') and not val_clean.startswith('-'):
                            val_clean = '+' + val_clean
                        gold_rendimento = val_clean + '/h'

                    try:
                        close_btn = game_page.locator(
                            ".dynamic_popup .close, .dialog .close, [title*='Fechar'], .closeButton, div.close").first
                        if close_btn.is_visible(timeout=1500):
                            close_btn.click()
                        else:
                            game_page.keyboard.press("Escape")
                        HumanBehavior.random_sleep(0.6, 1.0)
                    except Exception:
                        game_page.keyboard.press("Escape")
            except Exception as e:
                print(f"[Account Info AVISO] Falha ao capturar ouro/hora via modal: {e}")

            # 3. Extração Precisa de Barcos (Global)
            global_metrics = game_page.evaluate(r"""() => {
                let metrics = {
                    barcosLivres: 0,
                    barcosTotais: 0
                };

                const bodyText = document.body.innerText;
                const transpContainer = document.querySelectorAll('.transporter, #transporterCount, li, div');
                for (let el of transpContainer) {
                    let txt = el.innerText ? el.innerText.trim() : '';
                    const matchTransp = txt.match(/^(\d{1,4})\s*\(\s*(\d{1,4})\s*\)$/);
                    if (matchTransp && parseInt(matchTransp[2]) < 5000) {
                        metrics.barcosLivres = parseInt(matchTransp[1], 10);
                        metrics.barcosTotais = parseInt(matchTransp[2], 10);
                        break;
                    }
                }

                if (metrics.barcosTotais === 0) {
                    const mTr = bodyText.match(/(\d+)\s*\(\s*(\d+)\s*\)/g);
                    if (mTr) {
                        for (let t of mTr) {
                            const subM = t.match(/(\d+)\s*\(\s*(\d+)\s*\)/);
                            if (subM) {
                                let val1 = parseInt(subM[1], 10);
                                let val2 = parseInt(subM[2], 10);
                                if (val2 < 1000 && val2 >= val1) {
                                    metrics.barcosLivres = val1;
                                    metrics.barcosTotais = val2;
                                    break;
                                }
                            }
                        }
                    }
                }
                return metrics;
            }""")

            barcos_livres = global_metrics.get('barcosLivres', 0)
            barcos_totais = global_metrics.get('barcosTotais', 0)
            transporters_text = f"{barcos_livres} ({barcos_totais})"

            # 4. Mapeamento Preciso das Cidades via `.ownCity` e atributo `selectvalue`
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

                    # Extração precisa dos cidadãos utilizando os IDs oficiais (#js_GlobalMenu_citizens e #js_GlobalMenu_population)
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
                    "id": "atual",
                    "nome": "Cidade Atual",
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

            info = {
                "qtd_cidades": len(cidades_info),
                "ouro": cls._parse_gold(gold_text),
                "ouro_texto": gold_text.strip(),
                "ouro_rendimento": gold_rendimento,
                "barcos_disponiveis": barcos_livres,
                "barcos_totais": barcos_totais,
                "barcos_transporte": transporters_text.strip(),
                "cidades": cidades_info
            }

            HumanBehavior.random_sleep(4.0, 6.0)
            print(
                f"[Account Info SUCESSO] Extração concluída | Ouro: {info['ouro_texto']} ({info['ouro_rendimento']}) | Barcos: {barcos_livres}/{barcos_totais}")
            return info

        except Exception as e:
            print(f"[Account Info ERRO] {e}")
            return None