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
                    return cls._clean_number(text)
            except Exception:
                pass
        return 0

    @classmethod
    def _sleep_interruptible(cls, game_page, seconds: int, check_callback=None):
        steps = int(seconds * 2)
        for _ in range(steps):
            if check_callback and not check_callback():
                break
            try:
                game_page.wait_for_timeout(500)
            except Exception:
                break

    @classmethod
    def run(cls, conta_id: int, game_page, check_running_callback=None):
        print(f"[Account Info] Coletando informações completas para a conta ID {conta_id}...")

        try:
            game_page.wait_for_selector("#globalResources", timeout=20000)
            HumanBehavior.random_sleep(2.0, 3.5)

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

            # 3. Extração Precisa de Barcos e Cidadãos
            global_metrics = game_page.evaluate(r"""() => {
                let metrics = {
                    barcosLivres: 0,
                    barcosTotais: 0,
                    cidLivres: '0',
                    cidTotais: '0'
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

                const allMatches = bodyText.match(/(\d[\d\.,]*)\s*\(\s*(\d[\d\.,]*)\s*\)/g);
                if (allMatches) {
                    for (let matchStr of allMatches) {
                        const parts = matchStr.match(/(\d[\d\.,]*)\s*\(\s*(\d[\d\.,]*)\s*\)/);
                        if (parts) {
                            let p1 = parts[1].replace(/\./g, '');
                            let p2 = parts[2].replace(/\./g, '');
                            let n1 = parseInt(p1, 10);
                            let n2 = parseInt(p2, 10);
                            if (n2 > 10 && n2 <= 100000 && n2 >= n1) {
                                metrics.cidLivres = parts[1];
                                metrics.cidTotais = parts[2];
                                if (n2 !== metrics.barcosTotais) {
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
            cid_livres_str = global_metrics.get('cidLivres', '0')
            cid_totais_str = global_metrics.get('cidTotais', '0')

            # 4. Dropdown de Cidades
            drop_btn = game_page.locator("#js_citySelectContainer .dropDownButton").first
            cidades_raw = []

            if drop_btn.is_visible(timeout=5000):
                HumanBehavior.human_click(game_page, "#js_citySelectContainer .dropDownButton")
                HumanBehavior.random_sleep(1.0, 1.8)

                cidades_raw = game_page.evaluate("""
                    () => {
                        let cities = [];
                        let listItems = document.querySelectorAll(
                            "#dropDown_js_citySelectContainer li, #js_citySelectContainer li"
                        );
                        listItems.forEach((li, index) => {
                            let a = li.querySelector("a");
                            let rawText = a ? a.innerText : li.innerText;
                            if (!rawText) return;
                            let lines = rawText.split("\\n").map(s => s.trim()).filter(s => s.length > 0);
                            cities.push({ index: index, name: lines[0] || "Cidade" });
                        });
                        return cities;
                    }
                """)
                try:
                    game_page.keyboard.press("Escape")
                    HumanBehavior.random_sleep(0.4, 0.8)
                except Exception:
                    pass

            cidades_info = []

            if cidades_raw:
                for i, city in enumerate(cidades_raw):
                    if check_running_callback and not check_running_callback():
                        break

                    city_index = city["index"]
                    city_name = city["name"]

                    try:
                        if drop_btn.is_visible(timeout=3000):
                            HumanBehavior.human_click(game_page, "#js_citySelectContainer .dropDownButton")
                            HumanBehavior.random_sleep(0.8, 1.4)
                    except Exception:
                        pass

                    game_page.evaluate("""
                        (idx) => {
                            let items = document.querySelectorAll(
                                "#dropDown_js_citySelectContainer li, #js_citySelectContainer li"
                            );
                            if (items[idx]) {
                                let link = items[idx].querySelector("a") || items[idx];
                                link.click();
                            }
                        }
                    """, city_index)

                    HumanBehavior.random_sleep(3.5, 5.0)

                    wood = cls._get_resource_value(game_page, ["#js_GlobalMenu_wood"])
                    wine = cls._get_resource_value(game_page, ["#js_GlobalMenu_wine"])
                    marble = cls._get_resource_value(game_page, ["#js_GlobalMenu_marble"])
                    glass = cls._get_resource_value(game_page, ["#js_GlobalMenu_glass", "#js_GlobalMenu_crystal"])
                    sulfur = cls._get_resource_value(game_page, ["#js_GlobalMenu_sulfur"])

                    c_livres = cid_livres_str
                    c_totais = cid_totais_str
                    try:
                        city_pop = game_page.evaluate(r"""() => {
                            const bodyText = document.body.innerText;
                            const matches = bodyText.match(/(\d[\d\.,]*)\s*\(\s*(\d[\d\.,]*)\s*\)/g);
                            if (matches) {
                                for (let mStr of matches) {
                                    const parts = mStr.match(/(\d[\d\.,]*)\s*\(\s*(\d[\d\.,]*)\s*\)/);
                                    if (parts) {
                                        let n2 = parseInt(parts[2].replace(/\./g, ''), 10);
                                        if (n2 > 10 && n2 <= 100000) {
                                            return { livres: parts[1], totais: parts[2] };
                                        }
                                    }
                                }
                            }
                            return null;
                        }""")
                        if city_pop:
                            c_livres = city_pop['livres']
                            c_totais = city_pop['totais']
                    except Exception:
                        pass

                    cidades_info.append({
                        "id": f"cidade_{i + 1}",
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

                cidades_info.append({
                    "id": "atual",
                    "nome": "Cidade Atual",
                    "cidadaos_livres": cid_livres_str,
                    "cidadaos_totais": cid_totais_str,
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
                f"[Account Info SUCESSO] Extração concluída | Ouro: {info['ouro_texto']} ({info['ouro_rendimento']}) | Barcos: {barcos_livres}/{barcos_totais} | Cidadãos: {cid_livres_str}/{cid_totais_str}")
            return info

        except Exception as e:
            print(f"[Account Info ERRO] {e}")
            return None