# app/bot/tasks/accounts_scraper.py

import time
from flask import current_app
from app import db
from app.models import Lobby, Conta, get_brasilia_time


class AccountsScraperTask:
    @staticmethod
    def run(lobby, page, captured_accounts):
        """Força a navegação para o Hub, aguarda a API JSON e salva na base de dados."""
        print(f"[Task Scraper] Navegando para o Hub do Lobby '{lobby.nickname}'...")

        page.goto("https://lobby.ikariam.gameforge.com/pt_BR/hub", timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        if "hub" not in page.url and "accounts" not in page.url:
            print(f"[Task Scraper AVISO] Sessão expirada para o Lobby '{lobby.nickname}'.")
            return

        # Aguarda a resposta da API JSON ser capturada
        max_wait = 12
        waited = 0
        while not captured_accounts and waited < max_wait:
            time.sleep(0.5)
            waited += 0.5

        if not captured_accounts:
            print(f"[Task Scraper AVISO] Nenhuma conta capturada no tempo limite para o Lobby #{lobby.id}.")
            return

        print(f"[Task Scraper] Iniciando gravação de {len(captured_accounts)} conta(s) no Banco de Dados...")

        app = current_app._get_current_object()
        with app.app_context():
            try:
                # Reabre a sessão do banco nesta thread
                lobby_db = db.session.get(Lobby, lobby.id)
                if not lobby_db:
                    lobby_db = lobby

                novas_inseridas = 0
                atualizadas = 0
                agora_brasilia = get_brasilia_time()

                for acc in captured_accounts:
                    servidor_nome = acc.get("servidor")
                    nome_user = acc.get("nome_usuario")

                    if not servidor_nome or not nome_user:
                        print(f"[Task Scraper ERRO] Dados incompletos na conta: {acc}")
                        continue

                    # Busca se a conta já existe para este lobby
                    conta_existente = Conta.query.filter_by(
                        lobby_id=lobby_db.id,
                        servidor=servidor_nome,
                        nome_usuario=nome_user
                    ).first()

                    if not conta_existente:
                        nova_conta = Conta(
                            lobby_id=lobby_db.id,
                            gameforge_account_id=acc.get("gameforge_account_id"),
                            servidor=servidor_nome,
                            pais=acc.get("pais", "pt"),
                            nome_usuario=nome_user,
                            email=lobby_db.email,
                            ativo=acc.get("ativo", True),
                            automacao_ativa=False,
                            ultimo_login=agora_brasilia
                        )
                        db.session.add(nova_conta)
                        novas_inseridas += 1
                        print(f"[Task Scraper DB] Inserindo nova conta: {nome_user} @ {servidor_nome}")
                    else:
                        conta_existente.ativo = acc.get("ativo", True)
                        conta_existente.ultimo_login = agora_brasilia
                        if acc.get("gameforge_account_id"):
                            conta_existente.gameforge_account_id = acc.get("gameforge_account_id")
                        atualizadas += 1
                        print(f"[Task Scraper DB] Atualizando conta existente: {nome_user} @ {servidor_nome}")

                # Força o envio e a gravação definitiva em disco
                db.session.flush()
                db.session.commit()

                # Confirmação imediata via query pós-commit
                total_salvas = Conta.query.filter_by(lobby_id=lobby_db.id).count()
                print(f"[Task Scraper SUCESSO] Commit realizado! Total de contas no BD para este Lobby: {total_salvas}")

            except Exception as e:
                db.session.rollback()
                print(f"[Task Scraper ERRO GRAVE BD] Falha ao fazer commit no SQLite: {e}")