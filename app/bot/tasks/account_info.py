# app/bot/tasks/account_info.py
import asyncio
import re

from app.bot.utils import HumanBehavior, UICleaner, BotLogger

logger = BotLogger.get_logger()


class AccountInfoTask:

    @staticmethod
    def _clean_number(text: str) -> int:
        if not text:
            return 0

        str_val = str(text).strip()

        # Remove tudo o que não for número, ponto ou vírgula
        str_val = re.sub(r"[^\d,\.]", "", str_val)
        if not str_val:
            return 0

        # Se houver ponto e vírgula (ex: formato europeu/brasileiro)
        if ',' in str_val and '.' in str_val:
            if str_val.find(',') < str_val.find('.'):
                str_val = str_val.replace(',', '')
            else:
                str_val = str_val.replace('.', '').replace(',', '.')
        elif ',' in str_val:
            # Se tem vírgula, remove-a se for milhar ou substitui por ponto se for decimal
            if len(str_val.split(',')[-1]) == 2:
                str_val = str_val.replace(',', '.')
            else:
                str_val = str_val.replace(',', '')
        elif '.' in str_val:
            # Se tem ponto (ex: 16.794 ou 11.41), removemos o ponto para que vire um inteiro puro (16794)
            # Se o ponto for decimal real com 2 dígitos (ex: 13.51 -> 1351 ou arredondado), tratamos em segurança:
            parts = str_val.split('.')
            if len(parts) == 2 and len(parts[1]) == 2:
                # Caso seja um decimal curto do jogo, tratamos como inteiro multiplicando ou limpando
                str_val = "".join(parts)
            else:
                # Ponto de milhar (ex: 16.794 vira 16794)
                str_val = str_val.replace('.', '')

        try:
            return int(float(str_val))
        except ValueError:
            cleaned = re.sub(r"[^\d]", "", str_val)
            return int(cleaned) if cleaned else 0

    @classmethod
    async def _get_resource_value(cls, game_page, selectors) -> int:
        for selector in selectors:
            try:
                loc = game_page.locator(selector)
                if await loc.is_visible(timeout=2000):
                    text = await loc.inner_text()
                    # Como _clean_number é staticmethod, chamamos diretamente pela classe ou cls
                    val = cls._clean_number(text)
                    if val >= 0:
                        return val
            except Exception:
                pass
        return 0

    @classmethod
    async def _get_island_info(cls, game_page):
        """
        Extrai o ID, nome e coordenadas da ilha usando os seletores da barra superior (breadcrumb).
        """
        try:
            island_elem = game_page.locator("#js_islandBread")
            if await island_elem.is_visible(timeout=2000):
                # Extrai o ID da ilha do link (href)
                href = await island_elem.get_attribute("href")
                id_match = re.search(r"islandId=(\d+)", href) if href else None
                ilha_id = int(id_match.group(1)) if id_match else None

                # Extrai o nome da ilha
                name_elem = game_page.locator("#js_islandBreadName")
                nome_ilha = (await name_elem.inner_text()).strip() if await name_elem.is_visible(
                    timeout=1000) else "Ilha"

                # Extrai as coordenadas [X:Y]
                coords_elem = game_page.locator("#js_islandBreadCoords")
                coords_text = (await coords_elem.inner_text()).strip() if await coords_elem.is_visible(
                    timeout=1000) else ""

                coord_match = re.search(r"\[(\d+):(\d+)\]", coords_text)
                coords = {"x": coord_match.group(1), "y": coord_match.group(2)} if coord_match else None

                return {
                    "ilha_id": ilha_id,
                    "nome": nome_ilha,
                    "coords": coords
                }
        except Exception:
            pass

        return {"ilha_id": None, "nome": "Ilha Desconhecida", "coords": None}

    @classmethod
    async def run_async(cls, conta_id: int, game_page):
        logger.info(f"[Account Info] Coletando informações completas para a conta ID {conta_id}...")

        try:
            await game_page.wait_for_selector("#topnavi", timeout=20000)
            await HumanBehavior.random_sleep(2.0, 3.5)

            # =========================================================================
            # LIMPEZA INICIAL: TRATADO DE FORMA SEGURA
            # =========================================================================
            try:
                logger.info("[Game Cleaner] Verificando pop-ups, anúncios e banner de cookies...")
                if asyncio.iscoroutinefunction(UICleaner.dismiss_popups_and_banners):
                    await UICleaner.dismiss_popups_and_banners(game_page)
                else:
                    UICleaner.dismiss_popups_and_banners(game_page)
            except Exception as e:
                logger.warning(f"[Game Cleaner AVISO] Erro ao tentar limpar elementos da tela: {e}")

            # 1 - Captura os barcos disponíveis, totais, cargueiros e ouro.
            barcos_livres_text = await game_page.locator("#js_GlobalMenu_freeTransporters").inner_text()
            barcos_totais_text = await game_page.locator("#js_GlobalMenu_maxTransporters").inner_text()
            cargueiros_livres_text = await game_page.locator("#js_GlobalMenu_freeFreighters").inner_text()
            cargueiros_totais_text = await game_page.locator("#js_GlobalMenu_maxFreighters").inner_text()

            barcos_livres = cls._clean_number(barcos_livres_text)
            barcos_totais = cls._clean_number(barcos_totais_text)
            cargueiros_livres = cls._clean_number(cargueiros_livres_text)
            cargueiros_totais = cls._clean_number(cargueiros_totais_text)

            transporters_text = f"{barcos_livres} ({barcos_totais})"
            cargueiros_text = f"{cargueiros_livres} ({cargueiros_totais})"
            logger.info(f"Barcos de transporte: {transporters_text}")
            logger.info(f"Cargueiros: {cargueiros_text}")

            # COLETA DO OURO E RENDIMENTO
            exact_gold = "0"
            rendimento_exato = "+0/h"
            await HumanBehavior.human_click(game_page, "#js_GlobalMenu_gold")
            await HumanBehavior.random_sleep(3.5, 5.0)

            try:
                exact_gold = (await game_page.locator("td.nowrap.res div.tooltip").first.inner_text(timeout=3000)).strip()
                logger.info(f"Ouro total exato: {exact_gold.strip()}")
            except Exception as e:
                logger.warning(f"Não foi possível capturar o ouro total: {e}")

            try:
                rendimento_exato = (await game_page.locator("tr.result td.nowrap div.tooltip").nth(7).inner_text(
                    timeout=3000)).strip()
                logger.info(f"Rendimento exato: {rendimento_exato.strip()}")
            except Exception as e:
                logger.warning(f"Não foi possível capturar o rendimento exato: {e}")

            # Fecha o modal pressionando Escape ou clicando no botão de fechar
            try:
                close_btn = game_page.locator(".dynamic_popup .close, .dialog .close, [title*='Fechar']").first
                if await close_btn.is_visible(timeout=1000):
                    await close_btn.click()
                else:
                    await game_page.keyboard.press("Escape")
                await HumanBehavior.random_sleep(0.5, 0.8)
            except Exception:
                await game_page.keyboard.press("Escape")

            ouro_limpo = str(cls._clean_number(exact_gold))
            rendimento_limpo = str(cls._clean_number(rendimento_exato))

            # 2. Mapeamento e Varredura de Cidades
            drop_btn_selector = "#js_citySelectContainer .dropDownButton"
            cidades_info = []
            cidades_data = []

            try:
                if await game_page.locator(drop_btn_selector).is_visible(timeout=4000):
                    await HumanBehavior.human_click(game_page, drop_btn_selector)
                    await HumanBehavior.random_sleep(1.0, 1.5)

                    cidades_data = await game_page.evaluate("""
                        () => {
                            let list = [];
                            let items = document.querySelectorAll("li.ownCity, #dropDown_js_citySelectContainer li.ownCity");

                            items.forEach((li) => {
                                let selectVal = li.getAttribute("selectvalue");
                                let aTag = li.querySelector("a");
                                let rawText = aTag ? aTag.innerText : li.innerText;

                                if (selectVal && rawText) {
                                    let name = rawText.split("\\n")[0].trim();

                                    list.push({ 
                                        id: selectVal, 
                                        name: name
                                    });
                                }
                            });

                            return list;
                        }
                    """)

                    try:
                        await game_page.keyboard.press("Escape")
                        await HumanBehavior.random_sleep(0.4, 0.7)
                    except Exception:
                        pass
            except Exception as err:
                logger.warning(f"[Account Info AVISO] Falha ao listar cidades via dropdown: {err}")

            if cidades_data:
                logger.info(f"[Account Info] Cidades válidas mapeadas com sucesso: {len(cidades_data)}")

                for idx, city in enumerate(cidades_data):
                    city_id = city["id"]
                    city_name = city["name"]

                    logger.info(
                        f"[Account Info] Acessando cidade [{idx + 1}/{len(cidades_data)}]: {city_name} (ID: {city_id})...")

                    try:
                        await game_page.goto(f"https://{game_page.url.split('/')[2]}/index.php?view=city&cityId={city_id}",
                                       timeout=30000, wait_until="domcontentloaded")
                        await HumanBehavior.random_sleep(3.5, 5.0)
                    except Exception as nav_err:
                        logger.warning(f"[Account Info AVISO] Falha ao navegar diretamente para a cidade {city_name}: {nav_err}")
                        continue

                    # Coleta os dados da ilha
                    ilha_info = await cls._get_island_info(game_page)

                    wood = await cls._get_resource_value(game_page, ["#js_GlobalMenu_wood"])
                    wine = await cls._get_resource_value(game_page, ["#js_GlobalMenu_wine"])
                    marble = await cls._get_resource_value(game_page, ["#js_GlobalMenu_marble"])
                    glass = await cls._get_resource_value(game_page, ["#js_GlobalMenu_glass", "#js_GlobalMenu_crystal"])
                    sulfur = await cls._get_resource_value(game_page, ["#js_GlobalMenu_sulfur"])

                    c_livres = "0"
                    c_totais = "0"
                    try:
                        pop_metrics = await game_page.evaluate(r"""() => {
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
                        "ilha": ilha_info,
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
                logger.info("Recursos não coletados.")

            info = {
                "qtd_cidades": len(cidades_info),
                "ouro": ouro_limpo,
                "ouro_rendimento": rendimento_limpo,
                "barcos_disponiveis": barcos_livres,
                "barcos_totais": barcos_totais,
                "barcos_transporte": transporters_text.strip(),
                "cargueiros_disponiveis": cargueiros_livres,
                "cargueiros_totais": cargueiros_totais,
                "cidades": cidades_info
            }

            await HumanBehavior.random_sleep(4.0, 6.0)
            logger.info(
                f"[Account Info SUCESSO] Extração concluída | Ouro: {info['ouro']} ({info['ouro_rendimento']}) | Barcos: {barcos_livres}/{barcos_totais}")
            return info

        except Exception as e:
            logger.error(f"[Account Info ERRO] {e}")
            return None