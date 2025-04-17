import os

from dotenv import find_dotenv, load_dotenv
from src.logger_download import logger
from src.telegram_bot import AgroReportTelegramBot


def main():
    load_dotenv(find_dotenv())

    required_values = [
        "TELEGRAM_BOT_TOKEN",
        "ALLOWED_TELEGRAM_USER_IDS",
        "ADMIN_USER_IDS",
        "MISTRAL_API_KEYS",
        "GROUP_CHAT_ID",
        "PROXY_IP",
        "PROXY_PORT",
        "PROXY_USERNAME",
        "PROXY_PASSWORD",
    ]
    missing_values = [
        value for value in required_values if os.environ.get(value) is None
    ]
    if len(missing_values) > 0:
        logger.error(
            f'The following environment values are missing in your .env: {", ".join(missing_values)}'
        )
        exit(1)

    config = {
        "token": os.environ["TELEGRAM_BOT_TOKEN"],
        "admin_user_ids": os.environ["ADMIN_USER_IDS"],
        "allowed_user_ids": os.environ["ALLOWED_TELEGRAM_USER_IDS"],
        "group_chat_id": os.environ["GROUP_CHAT_ID"],
    }

    telegram_bot = AgroReportTelegramBot(config)
    telegram_bot.run()


if __name__ == "__main__":
    main()
