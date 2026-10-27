# app/bot/utils/human.py

import random
import asyncio


class HumanBehavior:
    @staticmethod
    async def random_sleep(min_seconds=1.5, max_seconds=4.0):
        """Pausa a execução de forma assíncrona por um tempo aleatório no intervalo fornecido."""
        duration = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(duration)

    @staticmethod
    async def human_click(page, selector, timeout=10000):
        """Move o ponteiro de forma orgânica até o elemento, faz uma pequena pausa e clica (Assíncrono)."""
        element = page.locator(selector).first
        await element.wait_for(state="visible", timeout=timeout)

        # Posição do elemento
        box = await element.bounding_box()
        if box:
            # Aponta para um ponto aleatório dentro das bordas do elemento
            x = box["x"] + random.uniform(2, max(2, box["width"] - 2))
            y = box["y"] + random.uniform(2, max(2, box["height"] - 2))

            # Move o mouse suavemente com passos intermediários
            await page.mouse.move(x, y, steps=random.randint(5, 15))
            await asyncio.sleep(random.uniform(0.1, 0.4))

            # Executa o clique
            await page.mouse.click(x, y)
        else:
            await element.click()

        # Pausa após o clique como um humano reagindo
        await asyncio.sleep(random.uniform(0.8, 2.2))

    @staticmethod
    async def human_type(page, selector, text, delay_range=(0.05, 0.18)):
        """Digita um texto caractere por caractere com intervalos variáveis entre as teclas (Assíncrono)."""
        element = page.locator(selector).first
        await element.click()
        await asyncio.sleep(random.uniform(0.2, 0.5))

        for char in text:
            await element.type(char)
            # Atraso aleatório entre cada letra
            await asyncio.sleep(random.uniform(delay_range[0], delay_range[1]))

            # Pequena probabilidade de hesitação
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.4, 0.9))

        await asyncio.sleep(random.uniform(0.5, 1.2))

    @staticmethod
    async def random_scroll(page):
        """Simula rolagens aleatórias na página para parecer uma leitura humana (Assíncrono)."""
        scroll_amount = random.randint(200, 500)
        await page.mouse.wheel(0, scroll_amount)
        await asyncio.sleep(random.uniform(1.0, 2.5))