from __future__ import annotations

import pandas as pd
from src.logger_download import logger
from src.report_builder import ERROR_TEXT, ReportBuilder
from src.utils import (
    MistralAPIInference,
    edit_message_with_retry,
    error_handler,
    get_reply_text,
    manage_attachment,
    message_text,
    send_telegram_message,
)
from telegram import (
    BotCommand,
    Update,
    constants,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


class AgroReportTelegramBot:
    """
    Class representing a CISM-LLM Telegram Bot.
    """

    def __init__(self, builder: ReportBuilder):
        """
        Initializes the bot with the given configuration and LLM bot object.
        :param config: A dictionary containing the bot configuration
        :param openai: LLMHelper object
        """

        self.builder = builder
        self.config = self.builder.config
        self.model = MistralAPIInference(
            config_path="src/configs/mistral_api.cfg.yml",
            api_key=self.builder.config["mistral_api_key"],
            proxy_url=None,
        )
        self.commands = [
            BotCommand(
                command="help",
                description=get_reply_text("help_description"),
            ),
        ]

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Shows the help menu.
        """
        commands = self.commands
        commands_description = [
            f"/{command.command} - {command.description}" for command in commands
        ]
        help_text = ""
        for text in get_reply_text("help_text"):
            help_text += f"{text}\n\n"

        help_text += "\n".join(commands_description)
        await update.message.reply_text(
            help_text,
            parse_mode=constants.ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    async def prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        React to incoming messages and respond accordingly.
        """
        if update.edited_message or not update.message or update.message.via_bot:
            return

        chat_id = update.effective_chat.id
        query = message_text(update) or ""
        sent_message = None

        if update.edited_message or not update.message or update.message.via_bot:
            return

        logger.info(
            f"New message received from user {update.message.from_user.name} (id: {update.message.from_user.id})"
        )
        chat_id = update.effective_chat.id

        sent_message = None
        file = update.message.document
        photo = update.message.photo
        if file or photo:
            sent_message = await update.effective_message.reply_text(
                "Файл обрабатывается 🤖",
            )
            file_name, file_content = await manage_attachment(
                self.model, update, context, file, photo
            )

            if file_content == "Данный тип файла не поддерживается.":
                await edit_message_with_retry(
                    context,
                    chat_id,
                    str(sent_message.message_id),
                    "Данный тип файла не поддерживается.",
                )
                return
            if file_content in [
                "К сожалению, модель не может обработать данный файл 😢",
                "Файл не загружен",
            ]:
                await edit_message_with_retry(
                    context,
                    chat_id,
                    str(sent_message.message_id),
                    "К сожалению, модель не может обработать данный файл 😢 Приложите отчёт в текстовом виде, пожалуйста.",
                )
                return

            query = f"""[Отчет из {file_name}]:\n{file_content}\n\n{query}"""

        try:
            await update.effective_message.reply_chat_action(
                action=constants.ChatAction.TYPING,
            )
            if not sent_message:
                sent_message = await update.effective_message.reply_text(
                    "Формирую отчёт 📝",
                )
            else:
                await edit_message_with_retry(
                    context,
                    chat_id,
                    str(sent_message.message_id),
                    "Формирую отчёт 📝",
                )
            response = self.builder.build(query)
            if response != ERROR_TEXT:
                logger.info("Report ready!")
                formatted_report = (
                    f"<pre>{pd.DataFrame(response).to_string(index=False)}</pre>"
                )
                await edit_message_with_retry(
                    context,
                    chat_id,
                    str(sent_message.message_id),
                    formatted_report,
                    html=True,
                )
                group_report = f"""Отчет от {update.effective_user.full_name}:\n\n{formatted_report}
Исходный текст отчёта:
{query}"""
                await context.bot.send_message(
                    chat_id=self.config["group_chat_id"],
                    text=group_report,
                    parse_mode=constants.ParseMode.HTML,
                    disable_web_page_preview=True,
                )

        except Exception as e:
            logger.exception(f"{str(e)}")
            await update.effective_message.reply_text(
                text=f"""Не удалось получить ответ ❌ попробуйте отправить сообщение повторно 🔄
Текст ошибки:

```{str(e)}```

**При повторении ошибки обратитесь к администратору @elpharran**""",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
            pass

    async def post_init(self, application: Application) -> None:
        """
        Post initialization hook for the bot.
        """
        await application.bot.set_my_commands(self.commands)

    def run(self):
        """
        Runs the bot indefinitely until the user presses Ctrl+C
        """
        application = (
            ApplicationBuilder()
            .token(self.config["token"])
            .post_init(self.post_init)
            .concurrent_updates(True)
            .build()
        )

        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("start", self.help))
        application.add_handler(
            CommandHandler(
                "chat",
                self.prompt,
                filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP,
            )
        )
        application.add_handler(
            MessageHandler(
                filters.TEXT & filters.ChatType.PRIVATE & (~filters.COMMAND),
                self.prompt,
            )
        )

        application.add_error_handler(error_handler)

        application.run_polling(allowed_updates=Update.ALL_TYPES)
