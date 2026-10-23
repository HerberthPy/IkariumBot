# app/bot/tasks/accounts_scraper.py

import time
from flask import current_app
from app import db
from app.models import Lobby, Conta, get_brasilia_time
from app.bot.auth import AuthManager
from app.bot.utils.worlds import get_world_name
from playwright.sync_api import sync_playwright


class AccountsScraperTask:
    @classmethod
    def run_sync_for_lobby(cls, lobby):
        """Abre o navegador Playwright de forma síncrona (SEM PROXY), captura as contas no Hub e persiste no BD."""
        raw_accounts = []

        def handle_response(response):
            try:
                if "accounts" in response.url or "gameforge.com/api/v1/user/accounts" in response.url:
                    if response.ok:
                        data = response.json()
                        if isinstance(data, list):
                            for item in data:
                                server_number = str(item.get("server", {}).get("number", ""))
                                friendly_world_name = get_world_name(server_number)

                                raw_accounts.append({
                                    "gameforge_account_id": item.get("id"),
                                    "servidor": friendly_world_name,
                                    "pais": item.get("server", {}).get("language", "pt"),
                                    "nome_usuario": item.get("name", lobby.nickname),
                                    "ativo": not item.get("blocked", False)
                                })
            except Exception:
                pass

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            proxy_config = None

            print(f"[Task Scraper] Conectando diretamente para o Lobby '{lobby.nickname}'...")
            proxy_context, page = AuthManager.get_authenticated_context(browser, lobby, proxy_config)

            page.on("response", handle_response)

            page.goto("https://lobby.ikariam.gameforge.com/pt_BR/hub", timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            proxy_context.close()
            browser.close()

        # Deduplica as contas capturadas com base no gameforge_account_id ou (servidor + nome_usuario)
        unique_accounts = {}
        for acc in raw_accounts:
            key = acc.get("gameforge_account_id") or f"{acc.get('servidor')}_{acc.get('nome_usuario')}"
            unique_accounts[key] = acc

        captured_accounts = list(unique_accounts.values())

        if captured_accounts:
            cls.save_to_db(lobby, captured_accounts)

        return captured_accounts

    @staticmethod
    def save_to_db(lobby, captured_accounts):
        print(f"[Task Scraper] Iniciando gravação de {len(captured_accounts)} conta(s) unicas no Banco de Dados...")

        app = current_app._get_current_object()
        with app.app_context():
            try:
                lobby_db = db.session.get(Lobby, lobby.id)
                if not lobby_db:
                    lobby_db = lobby

                agora_brasilia = get_brasilia_time()

                # 1. Coleta todos os IDs da Gameforge encontrados e limpos agora
                ids_capturados = [acc.get("gameforge_account_id") for acc in captured_accounts if
                                  acc.get("gameforge_account_id")]

                # 2. Remove do banco contas deste lobby que não vieram na sincronização atual
                if ids_capturados:
                    Conta.query.filter(
                        Conta.lobby_id == lobby_db.id,
                        ~Conta.gameforge_account_id.in_(ids_capturados)
                    ).delete(synchronize_session=False)

                # 3. Limpeza preventiva de eventuais duplicadas já existentes no SQLite
                todas_contas_db = Conta.query.filter_by(lobby_id=lobby_db.id).all()
                vistos = set()
                for c in todas_contas_db:
                    chave = (c.gameforge_account_id, c.servidor, c.nome_usuario)
                    if chave in vistos:
                        db.session.delete(c)
                    else:
                        vistos.add(chave)

                # 4. Insere ou atualiza as contas atuais de forma rigorosa
                for acc in captured_accounts:
                    servidor_nome = acc.get("servidor")
                    nome_user = acc.get("nome_usuario")
                    gf_id = acc.get("gameforge_account_id")

                    if not servidor_nome or not nome_user:
                        continue

                    conta_existente = Conta.query.filter_by(
                        lobby_id=lobby_db.id,
                        gameforge_account_id=gf_id,
                        servidor=servidor_nome
                    ).first()

                    if not conta_existente:
                        nova_conta = Conta(
                            lobby_id=lobby_db.id,
                            gameforge_account_id=gf_id,
                            servidor=servidor_nome,
                            pais=acc.get("pais", "pt"),
                            nome_usuario=nome_user,
                            email=lobby_db.email,
                            ativo=acc.get("ativo", True),
                            automacao_ativa=False,
                            ultimo_login=agora_brasilia
                        )
                        db.session.add(nova_conta)
                        print(f"[Task Scraper DB] Inserindo nova conta: {nome_user} @ {servidor_nome}")
                    else:
                        conta_existente.ativo = acc.get("ativo", True)
                        conta_existente.ultimo_login = agora_brasilia
                        print(f"[Task Scraper DB] Atualizando conta existente: {nome_user} @ {servidor_nome}")

                db.session.flush()
                db.session.commit()
                print(f"[Task Scraper SUCESSO] Duplicatas eliminadas e contas limpas com sucesso!")

            except Exception as e:
                db.session.rollback()
                print(f"[Task Scraper ERRO BD] {e}")