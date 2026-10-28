import re
import asyncio
import subprocess
import sys
from app import db
from app.models import Lobby, Conta, get_brasilia_time
from app.bot.auth import AuthManager
from app.bot.tasks.accounts_scraper import AccountsScraperTask
from app.bot.tasks.account_info import AccountInfoTask
from app.bot.utils import UICleaner, BotLogger

logger = BotLogger.get_logger()


class BotManager:
    _ativas = set()

    @classmethod
    def is_running(cls, lobby_id):
        return lobby_id in cls._ativas

    @classmethod
    def start_lobby(cls, lobby_id, app):
        if cls.is_running(lobby_id):
            return
        cls._rodar_em_subprocesso(lobby_id)

    @classmethod
    def _rodar_em_subprocesso(cls, lobby_id):
        try:
            cls._ativas.add(lobby_id)
            script_isolado = f"""
import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from app import create_app
from app.bot.runner import BotManager

app = create_app()
with app.app_context():
    BotManager.run_lobby_cycle_direto({lobby_id}, app)
"""
            subprocess.Popen([sys.executable, "-c", script_isolado])
        except Exception as e:
            logger.error(f"[BotManager] Erro ao iniciar subprocesso para o lobby #{lobby_id}: {e}")
            cls._ativas.discard(lobby_id)

    @classmethod
    def run_lobby_cycle(cls, lobby_id, app):
        cls.run_lobby_cycle_direto(lobby_id, app)

    @classmethod
    def run_lobby_cycle_direto(cls, lobby_id, app):
        cls._ativas.add(lobby_id)
        try:
            with app.app_context():
                lobby = db.session.get(Lobby, lobby_id)
                if not lobby:
                    return
                nickname = lobby.nickname

            logger.info(f"[BotRunner] A iniciar execução para o Lobby '{nickname}'...")
            asyncio.run(cls._run_async_cycle(lobby_id, app, nickname))

        except Exception as e:
            logger.error(f"[BotRunner ERRO] Falha ao executar o ciclo do lobby #{lobby_id}: {e}")
        finally:
            cls._ativas.discard(lobby_id)

    @classmethod
    async def _run_async_cycle(cls, lobby_id, app, nickname):
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--start-maximized"])
            try:
                with app.app_context():
                    lobby_db = db.session.get(Lobby, lobby_id)

                    # 1. Autentica e abre o navegador no Lobby
                    context, page = await AuthManager.get_authenticated_context(browser, lobby_db)
                    lobby_db.has_session = True
                    db.session.commit()

                    logger.info(f"[BotRunner] Conectado com sucesso ao Lobby '{lobby_db.nickname}'.")

                    # 2. Executa o scraper utilizando a mesma página aberta
                    await AccountsScraperTask.run_async_for_lobby(lobby_db, page)

                    # 3. Executa o pipeline de módulos para as contas ativas
                    await cls._executar_pipeline(context, page, lobby_db, app)

            finally:
                await browser.close()
                logger.info(f"[BotRunner] Navegador fechado para o Lobby '{nickname}'.")

    @classmethod
    async def _executar_pipeline(cls, context, lobby_page, lobby, app):
        with app.app_context():
            contas_ativas = [c for c in lobby.contas if c.ativo and c.automacao_ativa]

        if not contas_ativas:
            return

        for conta_ref in contas_ativas:
            with app.app_context():
                conta = db.session.get(Conta, conta_ref.id)
                if not conta or not conta.automacao_ativa:
                    continue
                nome_u = conta.nome_usuario
                serv = conta.servidor
                conta_id = conta.id
                modulos_habilitados = [cm.modulo.nome_tecnico for cm in conta.modulos_habilitados if cm.ativo]

            logger.info(f"[Pipeline] A processar conta: {nome_u} ({serv})")
            game_page = None

            try:
                game_page = await cls._entrar_na_conta(context, lobby_page, conta_ref)
                if not game_page:
                    logger.error(f"[Pipeline ERRO] Não foi possível abrir a conta {nome_u}.")
                    continue

                with app.app_context():
                    c_up = db.session.get(Conta, conta_id)
                    c_up.ultimo_login = get_brasilia_time()
                    c_up.ultima_sincronizacao = get_brasilia_time()
                    db.session.commit()

                    # MÓDULO 1: Coleta de Informações (Ativo)
                    if 'coleta_info' in modulos_habilitados:
                        logger.info(f" -> A executar Módulo: Coleta de Informações...")
                        dados_coletados = await AccountInfoTask.run_async(conta_id, game_page)

                        if dados_coletados:
                            with app.app_context():
                                try:
                                    conta_db = db.session.get(Conta, conta_id)
                                    if conta_db:
                                        # 1. Atualiza os campos principais da conta
                                        conta_db.ouro = str(dados_coletados.get("ouro", "0"))
                                        conta_db.ouro_rendimento = str(dados_coletados.get("ouro_rendimento", "+0/h"))
                                        conta_db.barcos_disponiveis = int(dados_coletados.get("barcos_disponiveis", 0))
                                        conta_db.barcos_totais = int(dados_coletados.get("barcos_totais", 0))

                                        # Tratativa para nomes de colunas de cargueiros
                                        if hasattr(conta_db, 'cargueiro_disponiveis'):
                                            conta_db.cargueiro_disponiveis = int(
                                                dados_coletados.get("cargueiros_disponiveis", 0))
                                        if hasattr(conta_db, 'cargueiro_totais'):
                                            conta_db.cargueiro_totais = int(dados_coletados.get("cargueiros_totais", 0))

                                        conta_db.ultima_sincronizacao = get_brasilia_time()

                                        # 2. Processa e salva as cidades recolhidas com os campos corretos da Ilha
                                        from app.models import Cidade, Ilha
                                        cidades_capturadas = dados_coletados.get("cidades", [])

                                        # Funções auxiliares seguras para conversão de números e recursos
                                        def parse_int_seguro(val):
                                            if not val:
                                                return 0
                                            s = str(val).strip()
                                            s_limpo = re.sub(r'[^\d]', '', s)
                                            return int(s_limpo) if s_limpo else 0

                                        def parse_res(val_str):
                                            if not val_str: return 0.0
                                            s = str(val_str).strip()
                                            if ',' in s and '.' in s:
                                                if s.find(',') < s.find('.'):
                                                    s = s.replace(',', '')
                                                else:
                                                    s = s.replace('.', '').replace(',', '.')
                                            elif ',' in s:
                                                if len(s.split(',')[-1]) == 2:
                                                    s = s.replace(',', '.')
                                                else:
                                                    s = s.replace(',', '')
                                            try:
                                                return float(s)
                                            except:
                                                return 0.0

                                        for c_data in cidades_capturadas:
                                            nome_cidade = c_data.get("nome")

                                            # Recolhe os dados da ilha extraídos do breadcrumb
                                            ilha_data = c_data.get("ilha", {})
                                            coords = ilha_data.get("coords")  # Ex: {'x': '78', 'y': '81'}

                                            recursos = c_data.get("recursos", {})

                                            # Garante a ilha no banco de dados usando coordenada_x e coordenada_y
                                            ilha_id_alvo = None
                                            if coords:
                                                x_val, y_val = int(coords.get("x", 0)), int(coords.get("y", 0))

                                                # Busca utilizando os nomes reais das colunas do seu modelo
                                                ilha_obj = Ilha.query.filter_by(coordenada_x=x_val,
                                                                                coordenada_y=y_val).first()

                                                if not ilha_obj:
                                                    # Cria a ilha usando coordenada_x e coordenada_y
                                                    ilha_obj = Ilha(coordenada_x=x_val, coordenada_y=y_val)
                                                    db.session.add(ilha_obj)
                                                    db.session.flush()

                                                ilha_id_alvo = ilha_obj.id

                                            if not ilha_id_alvo:
                                                # Fallback caso não venham coordenadas
                                                ilha_padrao = Ilha.query.first()
                                                if ilha_padrao:
                                                    ilha_id_alvo = ilha_padrao.id
                                                else:
                                                    continue

                                            # Procura ou cria a cidade
                                            cidade_obj = Cidade.query.filter_by(conta_id=conta_id,
                                                                                nome=nome_cidade).first()
                                            if not cidade_obj:
                                                cidade_obj = Cidade(
                                                    conta_id=conta_id,
                                                    ilha_id=ilha_id_alvo,
                                                    nome=nome_cidade
                                                )
                                                db.session.add(cidade_obj)

                                            # Atualiza as referências e dados da cidade com parsers seguros
                                            cidade_obj.ilha_id = ilha_id_alvo
                                            cidade_obj.populacao_livre = parse_int_seguro(c_data.get("cidadaos_livres", 0))
                                            cidade_obj.populacao_maxima = parse_int_seguro(c_data.get("cidadaos_totais", 0))

                                            cidade_obj.madeira = parse_res(recursos.get("madeira", 0))
                                            cidade_obj.vinho = parse_res(recursos.get("vinho", 0))
                                            cidade_obj.marmore = parse_res(recursos.get("marmore", 0))
                                            cidade_obj.cristal = parse_res(recursos.get("cristal", 0))
                                            cidade_obj.enxofre = parse_res(recursos.get("enxofre", 0))

                                        db.session.commit()
                                        logger.info(
                                            f"[Pipeline SUCESSO] Conta e {len(cidades_capturadas)} cidade(s) comitadas no BD com sucesso!")
                                except Exception as db_err:
                                    db.session.rollback()
                                    logger.error(f"[Pipeline ERRO BD] Falha ao persistir dados da conta: {db_err}")
                    else:
                        logger.info(f" -> Módulo 'coleta_info' desativado para esta conta.")

            except Exception as err:
                logger.error(f"[Pipeline ERRO] Erro na conta {nome_u}: {err}")
            finally:
                if game_page:
                    try:
                        if not game_page.is_closed():
                            await game_page.close()
                    except:
                        pass

    @classmethod
    async def _entrar_na_conta(cls, context, lobby_page, conta):
        try:
            await lobby_page.goto("https://lobby.ikariam.gameforge.com/pt_BR/accounts", timeout=30000,
                                  wait_until="domcontentloaded")
            await UICleaner.dismiss_popups_and_banners(lobby_page)
            await lobby_page.wait_for_selector("div.rt-tr-group", timeout=10000)
            await lobby_page.wait_for_timeout(1500)

            play_button = None
            target_user = str(conta.nome_usuario).strip().lower()
            target_server = str(conta.servidor).strip().lower()

            rows = await lobby_page.locator("div.rt-tr-group").all()
            for row in rows:
                try:
                    server_elem = (await row.locator("div.server-name-cell").inner_text()).strip().lower()
                    player_elem = (await row.locator("div.player-cell").inner_text()).strip().lower()

                    if target_server in server_elem and target_user in player_elem:
                        btn = row.locator("div.action-cell button, div.action-cell a").filter(
                            has_text=re.compile("Jogar|Play", re.IGNORECASE)).first
                        if await btn.is_visible(timeout=500):
                            play_button = btn
                            break
                except:
                    continue

            if not play_button or not (await play_button.is_visible(timeout=4000)):
                return None

            async with context.expect_page(timeout=20000) as new_page_info:
                await play_button.click()

            game_page = await new_page_info.value
            await game_page.wait_for_url(
                lambda url: "ikariam.gameforge.com" in url and ("view=" in url or "s" in url),
                timeout=25000
            )
            return game_page

        except Exception as e:
            logger.error(f"[Login ERRO] Falha ao abrir conta: {e}")
            return None