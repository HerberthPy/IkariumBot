# app/bot/utils/human.py

import random
import time


class HumanBehavior:
    @staticmethod
    def random_sleep(min_seconds=1.5, max_seconds=4.0):
        """Pausa a execução por um tempo aleatório no intervalo fornecido."""
        duration = random.uniform(min_seconds, max_seconds)
        time.sleep(duration)

    @staticmethod
    def human_click(page, selector, timeout=10000):
        """Move o ponteiro de forma orgânica até o elemento, faz uma pequena pausa e clica."""
        element = page.locator(selector).first
        element.wait_for(state="visible", timeout=timeout)

        # Posição do elemento
        box = element.bounding_box()
        if box:
            # Aponta para um ponto aleatório dentro das bordas do elemento (não exatamente no centro)
            x = box["x"] + random.uniform(2, box["width"] - 2)
            y = box["y"] + random.uniform(2, box["height"] - 2)

            # Move o mouse suavemente com passos intermediários
            page.mouse.move(x, y, steps=random.randint(5, 15))
            time.sleep(random.uniform(0.1, 0.4))

            # Executa o clique
            page.mouse.click(x, y)
        else:
            element.click()

        # Pausa após o clique como um humano reagindo
        time.sleep(random.uniform(0.8, 2.2))

    @staticmethod
    def human_type(page, selector, text, delay_range=(0.05, 0.18)):
        """Digita um texto caractere por caractere com intervalos variáveis entre as teclas."""
        element = page.locator(selector).first
        element.click()
        time.sleep(random.uniform(0.2, 0.5))

        for char in text:
            element.type(char)
            # Atraso aleatório entre cada letra
            time.sleep(random.uniform(delay_range[0], delay_range[1]))

            # Pequena probabilidade de hesitação (pausa curta como quem pensa/olha para o teclado)
            if random.random() < 0.05:
                time.sleep(random.uniform(0.4, 0.9))

        time.sleep(random.uniform(0.5, 1.2))

    @staticmethod
    def random_scroll(page):
        """Simula rolagens aleatórias na página para parecer uma leitura humana."""
        scroll_amount = random.randint(200, 500)
        page.mouse.wheel(0, scroll_amount)
        time.sleep(random.uniform(1.0, 2.5))