# app/bot/tasks/accounts_scrapper.py
import json
import asyncio
from flask import current_app
from app import db
from app.models import Lobby, Conta, Modulo, ContaModulo, get_brasilia_time
from app.bot.utils import get_world_name, BotLogger
from app.bot.utils.ui_cleaner import UICleaner

logger = BotLogger.get_logger()


class AccountsScraperTask:
    @classmethod
    async def run_async_for_lobby(cls, lobby, page=None):
        """
        Executa a raspagem das contas de forma assíncrona.
        Se a página não for fornecida, abre um navegador próprio com headless=False.
        """
        browser = None
        proxy_context = None
        fechar_browser_ao_terminar = False

        try:
            if page is None:
                from playwright.async_api import async_playwright
                from app.bot.auth import AuthManager

                fechar_browser_ao_terminar = True
                playwright_obj = async_playwright()
                p = await playwright_obj.start()

                browser = await p.chromium.launch(headless=False, args=["--start-maximized"])
                proxy_context, page = await AuthManager.get_authenticated_context(browser, lobby)

            raw_accounts = []

            async def async_handle_response(response):
                try:
                    if "accounts" in response.url or "gameforge.com/api/v1/user/accounts" in response.url:
                        if response.ok:
                            data = await response.json()
                            if isinstance(data, list):
                                for item in data:
                                    server_number = str(item.get("server", {}).get("number", ""))
                                    friendly_world_name = get_world_name(server_number)

                                    status_raw = item.get("status") or item.get("accountStatus") or ""
                                    is_blocked = item.get("blocked") or item.get("banned") or False

                                    status_jogo = "Bloqueada" if is_blocked else (
                                        str(status_raw).capitalize() if status_raw else "Ativa")

                                    raw_accounts.append({
                                        "gameforge_account_id": item.get("id"),
                                        "servidor": friendly_world_name,
                                        "pais": item.get("server", {}).get("language", "pt"),
                                        "nome_usuario": item.get("name", lobby.nickname),
                                        "status_jogo": status_jogo,
                                        "ativo": False
                                    })
                except Exception:
                    pass

            page.on("response", async_handle_response)

            try:
                logger.info(f"[Scraper] A navegar para o Hub do Lobby '{lobby.nickname}'...")
                await page.goto("https://lobby.ikariam.gameforge.com/pt_BR/hub", timeout=30000,
                                wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)  # Aguarda 5 segundos para garantir a captura da API
                await UICleaner.dismiss_popups_and_banners(page)
            except Exception as e:
                logger.warning(f"[Scraper] Erro ao navegar para o hub: {e}")

            unique_accounts = {
                acc.get("gameforge_account_id") or f"{acc.get('servidor')}_{acc.get('nome_usuario')}": acc for acc in
                raw_accounts}
            captured_accounts = list(unique_accounts.values())

            if fechar_browser_ao_terminar:
                if proxy_context:
                    await proxy_context.close()
                if browser:
                    await browser.close()
                if 'p' in locals():
                    await p.stop()

            if captured_accounts:
                return cls.save_to_db(lobby, captured_accounts)
            return []

        except Exception as err:
            logger.error(f"[Scraper ERRO] Falha na execução assíncrona: {err}")
            if fechar_browser_ao_terminar:
                try:
                    if proxy_context:
                        await proxy_context.close()
                    if browser:
                        await browser.close()
                except:
                    pass
            return []

    @staticmethod
    def run_sync_for_lobby(lobby):
        """
        Método de compatibilidade síncrono para ser chamado direto de rotas do Flask
        ou de locais síncronos, abrindo o navegador visível (headless=False).
        """
        return asyncio.run(AccountsScraperTask.run_async_for_lobby(lobby, page=None))

    @staticmethod
    def save_to_db(lobby, captured_accounts):
        logger.info(f"[Scraper] A gravar {len(captured_accounts)} conta(s) no Banco de Dados...")
        app = current_app._get_current_object()
        enriched_accounts = []

        with app.app_context():
            try:
                lobby_db = db.session.get(Lobby, lobby.id) or lobby
                agora_brasilia = get_brasilia_time()

                modulo_coleta = Modulo.query.filter_by(nome_tecnico='coleta_info').first()

                ids_capturados = [acc.get("gameforge_account_id") for acc in captured_accounts if
                                  acc.get("gameforge_account_id")]
                if ids_capturados:
                    Conta.query.filter(Conta.lobby_id == lobby_db.id,
                                       ~Conta.gameforge_account_id.in_(ids_capturados)).delete(
                        synchronize_session=False)

                for acc in captured_accounts:
                    servidor_nome, nome_user, gf_id = acc.get("servidor"), acc.get("nome_usuario"), acc.get(
                        "gameforge_account_id")
                    if not servidor_nome or not nome_user:
                        continue

                    conta_obj = Conta.query.filter_by(lobby_id=lobby_db.id, gameforge_account_id=gf_id,
                                                      servidor=servidor_nome).first()
                    if not conta_obj:
                        conta_obj = Conta(
                            lobby_id=lobby_db.id, gameforge_account_id=gf_id, servidor=servidor_nome,
                            pais=acc.get("pais", "pt"), nome_usuario=nome_user, ativo=False,
                            automacao_ativa=False, ultimo_login=agora_brasilia,
                            status_jogo=acc.get("status_jogo", "Ativa")
                        )
                        db.session.add(conta_obj)
                        db.session.flush()
                    else:
                        conta_obj.ultimo_login = agora_brasilia
                        conta_obj.status_jogo = acc.get("status_jogo", "Ativa")

                        # Garante que o módulo 'coleta_info' esteja associado à conta
                        if modulo_coleta:
                            vinculo = ContaModulo.query.filter_by(conta_id=conta_obj.id,
                                                                  modulo_id=modulo_coleta.id).first()

                            # Define se o módulo deve estar ativo com base no campo 'ativo' da conta (True/1 ou False/0)
                            deve_ativar = bool(conta_obj.ativo)

                            if not vinculo:
                                novo_vinculo = ContaModulo(conta_id=conta_obj.id, modulo_id=modulo_coleta.id,
                                                           ativo=deve_ativar)
                                db.session.add(novo_vinculo)
                            else:
                                vinculo.ativo = deve_ativar

                    enriched_accounts.append({
                        "db_id": conta_obj.id, "servidor": conta_obj.servidor, "pais": conta_obj.pais,
                        "nome_usuario": conta_obj.nome_usuario, "ativo": conta_obj.ativo,
                        "status_jogo": conta_obj.status_jogo
                    })

                db.session.commit()
                logger.info(f"[Scraper] Contas e módulos obrigatórios persistidos com sucesso!")
                return enriched_accounts
            except Exception as e:
                db.session.rollback()
                logger.error(f"[Scraper ERRO BD] {e}")
                return []