# app/bot/utils/logger.py

import logging
import os


class BotLogger:
    _logger = None

    @classmethod
    def get_logger(cls):
        if cls._logger is not None:
            return cls._logger

        logger = logging.getLogger("IkariamBot")
        logger.setLevel(logging.INFO)

        # IMPEDE QUE OS LOGS PROPAGUEM PARA O ROOT LOGGER (Evita a duplicação)
        logger.propagate = False

        if not logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

            log_dir = os.path.join(os.getcwd(), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'bot.log')

            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)

        cls._logger = logger
        return cls._logger