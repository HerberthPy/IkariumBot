# app/bot/tasks/account_info.py

import re
import time


class AccountInfoTask:
    @staticmethod
    def _clean_number(text: str) -> int:
        """Converte strings formatadas (ex: '125,357' ou '125.357') para inteiros."""
        if not text:
            return 0
        cleaned = re.sub(r"[^\d]", "", text)
        return int(cleaned) if cleaned else 0

    @staticmethod
    def _parse_gold(text: str) -> float:
        """Converte valores de ouro formatados (ex: '107.37M' ou '107,370,000') para float/int."""
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
        """Tenta obter o valor de um recurso testando múltiplos seletores de forma segura."""
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
        """
        Aguarda o tempo especificado em pequenos intervalos de 500ms,
        permitindo a interrupção rápida se uma flag de parada for acionada.
        """
        steps = int(seconds * 2)
        for _ in range(steps):
            if check_callback and not check_callback():
                print("[Account Info] Interrupção detectada durante a pausa. Cancelando espera...")
                break
            try:
                game_page.wait_for_timeout(500)
            except Exception:
                break

    @classmethod
    def run(cls, conta_id: int, game_page, check_running_callback=None):
        """
        Coleta as informações globais da conta e os recursos detalhados de cada cidade via cliques no dropdown.
        """
        print(f"[Account Info] Coletando informações completas para a conta ID {conta_id}...")

        try:
            # 1. Aguarda a interface principal carregar completamente
            game_page.wait_for_selector("#globalResources", timeout=20000)
            print("[Account Info] Aguardando estabilização da interface...")
            game_page.wait_for_timeout(3000)

            # 2. Leitura de Dados Globais da Conta (Ouro e Barcos de Transporte)
            gold_text = ""
            try:
                if game_page.locator("#js_GlobalMenu_gold").is_visible(timeout=3000):
                    gold_text = game_page.locator("#js_GlobalMenu_gold").inner_text()
            except Exception:
                pass

            gold_value = cls._parse_gold(gold_text)

            transporters_text = ""
            try:
                if game_page.locator("#js_GlobalMenu_freeTransporters").is_visible(timeout=3000):
                    transporters_text = game_page.locator("#js_GlobalMenu_freeTransporters").inner_text()
            except Exception:
                pass

            # 3. Localiza o botão do dropdown de cidades
            drop_btn = game_page.locator("#js_citySelectContainer .dropDownButton").first

            cidades_raw = []
            if drop_btn.is_visible(timeout=5000):
                print("[Account Info] Clicando no dropdown para expandir a lista de cidades...")
                drop_btn.click()
                game_page.wait_for_timeout(1500)

                # Mapeia cada linha da lista por seu ÍNDICE (sem ignorar nomes repetidos)
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
                            let name = lines[0] || "Cidade";

                            cities.push({
                                index: index,
                                name: name
                            });
                        });

                        return cities;
                    }
                """)

                # Fecha o dropdown inicial
                try:
                    game_page.keyboard.press("Escape")
                    game_page.wait_for_timeout(500)
                except Exception:
                    pass

            cidades_info = []

            # 4. Navega cidade por cidade clicando diretamente pelo índice do elemento
            if cidades_raw:
                print(f"[Account Info] Total de cidades encontradas no menu: {len(cidades_raw)}")

                for i, city in enumerate(cidades_raw):
                    if check_running_callback and not check_running_callback():
                        print("[Account Info] Interrupção solicitada. Abortando leitura das cidades restantes.")
                        break

                    city_index = city["index"]
                    city_name = city["name"]

                    print(
                        f"[Account Info] Clicando na cidade {i + 1}/{len(cidades_raw)} (Índice {city_index}): '{city_name}'...")

                    # Abre o dropdown para tornar a opção clicável
                    try:
                        if drop_btn.is_visible(timeout=3000):
                            drop_btn.click()
                            game_page.wait_for_timeout(1000)
                    except Exception:
                        pass

                    # Clica diretamente na opção daquela posição
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

                    print(
                        f"[Account Info] Aguardando 5s para carregamento dos recursos da cidade #{i + 1} ('{city_name}')...")
                    cls._sleep_interruptible(game_page, 5, check_running_callback)

                    # Coleta os recursos atualizados
                    wood = cls._get_resource_value(game_page, ["#js_GlobalMenu_wood"])
                    wine = cls._get_resource_value(game_page, ["#js_GlobalMenu_wine"])
                    marble = cls._get_resource_value(game_page, ["#js_GlobalMenu_marble"])
                    glass = cls._get_resource_value(game_page, ["#js_GlobalMenu_glass", "#js_GlobalMenu_crystal"])
                    sulfur = cls._get_resource_value(game_page, ["#js_GlobalMenu_sulfur"])

                    cidades_info.append({
                        "id": f"cidade_{i + 1}",
                        "nome": city_name,
                        "recursos": {
                            "madeira": wood,
                            "vinho": wine,
                            "marmore": marble,
                            "cristal": glass,
                            "enxofre": sulfur
                        }
                    })
            else:
                print("[Account Info AVISO] Nenhuma cidade encontrada no menu. Lendo apenas a cidade ativa...")
                wood = cls._get_resource_value(game_page, ["#js_GlobalMenu_wood"])
                wine = cls._get_resource_value(game_page, ["#js_GlobalMenu_wine"])
                marble = cls._get_resource_value(game_page, ["#js_GlobalMenu_marble"])
                glass = cls._get_resource_value(game_page, ["#js_GlobalMenu_glass", "#js_GlobalMenu_crystal"])
                sulfur = cls._get_resource_value(game_page, ["#js_GlobalMenu_sulfur"])

                cidades_info.append({
                    "id": "atual",
                    "nome": "Cidade Atual",
                    "recursos": {
                        "madeira": wood,
                        "vinho": wine,
                        "marmore": marble,
                        "cristal": glass,
                        "enxofre": sulfur
                    }
                })

            info = {
                "qtd_cidades": len(cidades_info),
                "ouro": gold_value,
                "ouro_texto": gold_text.strip(),
                "barcos_transporte": transporters_text.strip(),
                "cidades": cidades_info
            }

            # Pausa visual final de 8s (interrompível ao clicar em Parar)
            print("[Account Info] Coleta finalizada! Aguardando 8 segundos para acompanhamento na tela...")
            cls._sleep_interruptible(game_page, 8, check_running_callback)

            print(
                f"[Account Info SUCESSO] Processamento concluído para Conta ID {conta_id} | Total de cidades: {info['qtd_cidades']} | Ouro: {info['ouro_texto']}")
            return info

        except Exception as e:
            print(f"[Account Info ERRO] Falha ao extrair informações da conta ID {conta_id}: {e}")
            return None