import time
import logging
from app import create_app, db
from app.models import Lobby
from app.bot.runner import BotManager

# Configuração de logs para o worker
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s')
logger = logging.getLogger("BotWorker")


def main():
    app = create_app()
    logger.info("Servidor worker independente do bot iniciado com sucesso.")

    # Dicionário para controlar o tempo do último ciclo de cada lobby (em segundos)
    ultimos_ciclos = {}
    INTERVALO_COOLDOWN = 30 * 60  # 30 minutos em segundos

    while True:
        try:
            with app.app_context():
                # Busca todos os lobbies registados na base de dados
                lobbies = Lobby.query.all()

                for lobby in lobbies:
                    # Verifica se o lobby possui alguma conta ativa com automação ligada
                    contas_ativas = [c for c in lobby.contas if c.ativo and c.automacao_ativa]

                    if not contas_ativas:
                        continue  # Sem contas ativas neste lobby, passa para o próximo

                    tempo_atual = time.time()
                    ultimo_tempo = ultimos_ciclos.get(lobby.id, 0)

                    # Se já passou o tempo de cooldown e o bot não está a correr para este lobby
                    if (tempo_atual - ultimo_tempo) >= INTERVALO_COOLDOWN:
                        if not BotManager.is_running(lobby.id):
                            logger.info(f"Cooldown concluído para o Lobby '{lobby.nickname}' (ID: {lobby.id}). A disparar ciclo...")

                            # Atualiza o timestamp do último ciclo
                            ultimos_ciclos[lobby.id] = tempo_atual

                            # Executa o ciclo do lobby de forma totalmente limpa e isolada
                            BotManager.run_lobby_cycle(lobby.id, app)

        except Exception as e:
            logger.error(f"Erro crítico no loop do worker: {e}")

        # Intervalo de verificação da base de dados (a cada 15 segundos)
        time.sleep(15)


if __name__ == '__main__':
    main()