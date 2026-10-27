# app/bot/tasks/__init__.py

from app.bot.tasks.accounts_scraper import AccountsScraperTask
from app.bot.tasks.account_info import AccountInfoTask

__all__ = [
    'AccountsScraperTask',
    'AccountInfoTask'
]