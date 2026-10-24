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
        """Abre o navegador Playwright, captura as contas no Hub e persiste no BD como inativas."""
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

                                # Identifica o status real retornado pela Gameforge (bloqueada, banida, ativa, etc.)
                                status_raw = item.get("status") or item.get("accountStatus") or ""
                                is_blocked = item.get("blocked") or item.get("banned") or False

                                if is_blocked:
                                    status_jogo = "Bloqueada"
                                elif status_raw:
                                    status_jogo = str(status_raw).capitalize()
                                else:
                                    status_jogo = "Ativa"

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

        unique_accounts = {}
        for acc in raw_accounts:
            key = acc.get("gameforge_account_id") or f"{acc.get('servidor')}_{acc.get('nome_usuario')}"
            unique_accounts[key] = acc

        captured_accounts = list(unique_accounts.values())

        db_accounts_list = []
        if captured_accounts:
            db_accounts_list = cls.save_to_db(lobby, captured_accounts)

        return db_accounts_list

    @staticmethod
    def save_to_db(lobby, captured_accounts):
        print(f"[Task Scraper] Iniciando gravação de {len(captured_accounts)} conta(s) no Banco de Dados...")

        app = current_app._get_current_object()
        enriched_accounts = []

        with app.app_context():
            try:
                lobby_db = db.session.get(Lobby, lobby.id)
                if not lobby_db:
                    lobby_db = lobby

                agora_brasilia = get_brasilia_time()

                ids_capturados = [acc.get("gameforge_account_id") for acc in captured_accounts if acc.get("gameforge_account_id")]

                if ids_capturados:
                    Conta.query.filter(
                        Conta.lobby_id == lobby_db.id,
                        ~Conta.gameforge_account_id.in_(ids_capturados)
                    ).delete(synchronize_session=False)

                for acc in captured_accounts:
                    servidor_nome = acc.get("servidor")
                    nome_user = acc.get("nome_usuario")
                    gf_id = acc.get("gameforge_account_id")
                    status_capturado = acc.get("status_jogo", "Ativa")

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
                            ativo=False,
                            automacao_ativa=False,
                            ultimo_login=agora_brasilia,
                            status_jogo=status_capturado
                        )
                        db.session.add(nova_conta)
                        db.session.flush()
                        conta_obj = nova_conta
                    else:
                        conta_obj = conta_existente
                        conta_obj.ultimo_login = agora_brasilia
                        conta_obj.status_jogo = status_capturado  # Atualiza o status caso tenha mudado

                    enriched_accounts.append({
                        "db_id": conta_obj.id,
                        "servidor": conta_obj.servidor,
                        "pais": conta_obj.pais,
                        "nome_usuario": conta_obj.nome_usuario,
                        "ativo": conta_obj.ativo
                    })

                db.session.commit()
                print(f"[Task Scraper SUCESSO] Contas persistidas no BD com sucesso!")
                return enriched_accounts

            except Exception as e:
                db.session.rollback()
                print(f"[Task Scraper ERRO BD] {e}")
                return []