from __future__ import annotations

import pandas as pd
from src.logger_download import logger
from src.report_builder import ERROR_TEXT, ReportBuilder
from src.utils import (
    MistralAPIInference,
    edit_message_with_retry,
    error_handler,
    get_reply_text,
    is_allowed,
    manage_attachment,
    message_text,
)
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
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
        if not await self.check_allowed(update, context):
            return

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

    async def check_allowed(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> bool:
        """
        Checks if the user is allowed to use the bot
        :param update: Telegram update object
        :param context: Telegram context object
        :return: Boolean indicating if the user is allowed to use the bot
        """
        name = update.message.from_user.name
        user_id = update.message.from_user.id

        if not await is_allowed(self.config, update, context):
            logger.warning(f"User {name} (id: {user_id}) is not allowed to use the bot")
            await self.send_disallowed_message(update, context)
            return False

        return True

    async def send_disallowed_message(
        self, update: Update, _: ContextTypes.DEFAULT_TYPE
    ):
        """
        Sends the disallowed message to the user.
        """
        await update.effective_message.reply_text(
            text=get_reply_text("disallowed"),
            disable_web_page_preview=True,
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data == "final_yes":
            corrected_entries = context.user_data.get("corrected_entries")
            if corrected_entries is not None:

                # TODO: сохранялка отчетов с обновленной даткой

                pass

            # TODO сохранялка отчетов обычная

            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Отчёт записан в сводную таблицу ✅",
                reply_to_message_id=query.message.message_id,
            )

        elif query.data == "final_no":
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Отчёт не записан в сводную таблицу ⚠️",
                reply_to_message_id=query.message.message_id,
            )

        context.user_data.pop("corrected_entries", None)
        await query.edit_message_reply_markup(reply_markup=None)

    async def prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        if update.edited_message or not update.message or update.message.via_bot:
            return

        if not await self.check_allowed(update, context):
            return

        # Проверка состояния исправления
        if context.user_data.get("awaiting_correction"):
            user_input = update.message.text
            if not user_input:
                await update.message.reply_text("Пожалуйста, введите значение.")
                return

            user_input = user_input.strip()
            correction_data = context.user_data.get("corrections")
            if not correction_data:
                context.user_data.pop("awaiting_correction", None)
                return

            current_index = correction_data["current_index"]
            queue = correction_data["queue"]
            entries = correction_data["entries"]

            if current_index >= len(queue):
                context.user_data.pop("awaiting_correction", None)
                return

            entry_idx, key = queue[current_index]

            # Обновляем запись
            entries[entry_idx][key] = user_input
            correction_data["current_index"] += 1

            # Если остались исправления
            if correction_data["current_index"] < len(queue):
                next_entry_idx, next_key = queue[correction_data["current_index"]]
                entry_number = next_entry_idx + 1
                await update.message.reply_text(
                    f"""Запись {entry_number}. Нераспознанные данные: ```
{entries[entry_number]['Данные']}```

Введите значение для поля '{next_key}':""",
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
            else:
                # Все исправления завершены
                context.user_data.pop("awaiting_correction", None)
                for entry in entries:
                    entry.pop("Данные", None)
                context.user_data["corrected_entries"] = entries

                # Форматируем отчет
                formatted_report = (
                    "<pre>"
                    + "\n\n".join(
                        [
                            pd.DataFrame([entry]).to_string(index=False)
                            for entry in entries
                        ]
                    )
                    + "</pre>"
                )
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "Финальный отчёт ✅", callback_data="final_yes"
                        ),
                        InlineKeyboardButton(
                            "Промежуточный отчёт ⚠️", callback_data="final_no"
                        ),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    formatted_report, reply_markup=reply_markup, parse_mode="HTML"
                )
            return

        # Обработка входящих сообщений
        chat_id = update.effective_chat.id
        query_text = message_text(update) or ""
        sent_message = None
        logger.info(
            f"New message received from user {update.message.from_user.name} (id: {update.message.from_user.id})"
        )

        # Обработка вложений
        file = update.message.document
        photo = update.message.photo
        if file or photo:
            self.has_attachment = True
            sent_message = await update.effective_message.reply_text(
                "Файл обрабатывается 🤖", reply_to_message_id=update.message.message_id
            )
            try:
                file_content = await manage_attachment(
                    self.model, update, context, file, photo
                )
                logger.info(file_content)
                query_text = f"""[ТАБЛИЦА]:\n{file_content}\n\n{query_text}"""

            except Exception:
                await edit_message_with_retry(
                    context,
                    chat_id,
                    str(sent_message.message_id),
                    "К сожалению, модель не может обработать данный файл 😢 Приложите отчёт в текстовом виде, пожалуйста.",
                )
                return

        # Формирование отчета
        await update.effective_message.reply_chat_action(constants.ChatAction.TYPING)
        if not sent_message:
            sent_message = await update.effective_message.reply_text(
                "Формирую отчёт 📝", reply_to_message_id=update.message.message_id
            )
        else:
            await edit_message_with_retry(
                context,
                chat_id,
                str(sent_message.message_id),
                "Формирую отчёт 📝",
            )

        response = self.builder.build(query_text)
        formatted_report = ""

        if response != ERROR_TEXT:

            logger.info("Report ready!")
            # Проверка на необходимость исправлений
            corrections_queue = []
            for entry_idx, entry in enumerate(response):
                for key, value in entry.items():
                    if value == "Не определено":
                        corrections_queue.append((entry_idx, key))

            if corrections_queue:
                context.user_data["corrections"] = {
                    "entries": response,
                    "queue": corrections_queue,
                    "current_index": 0,
                }
                context.user_data["awaiting_correction"] = True
                first_entry_idx, first_key = corrections_queue[0]
                await update.message.reply_text(
                    f"""При заполнении отчёта не удалось распознать некоторые значения, требуется уточнение.

Запись {first_entry_idx + 1}. Нераспознанные данные: ```
{response[first_entry_idx]['Данные']}```

Введите значение для поля '{first_key}':
""",
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
                return

            # Если исправления не требуются
            for entry in response:
                entry.pop("Данные", None)

            formatted_report = (
                "<pre>"
                + "\n\n".join(
                    [pd.DataFrame([entry]).to_string(index=False) for entry in response]
                )
                + "</pre>"
            )
            keyboard = [
                [
                    InlineKeyboardButton(
                        "Финальный отчёт ✅", callback_data="final_yes"
                    ),
                    InlineKeyboardButton(
                        "Промежуточный отчёт ⚠️", callback_data="final_no"
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                formatted_report, reply_markup=reply_markup, parse_mode="HTML"
            )

        #             group_report = f"""Отчёт от {update.effective_user.full_name}:\n\n{formatted_report}
        # Исходный текст:

        # {query_text}"""
        #             await context.bot.send_message(
        #                 chat_id=self.config["group_chat_id"],
        #                 text=group_report,
        #                 parse_mode=constants.ParseMode.HTML,
        #                 disable_web_page_preview=True,
        #             )
        else:
            await edit_message_with_retry(
                context,
                chat_id,
                str(sent_message.message_id),
                response,
                html=True,
            )

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
                (
                    filters.TEXT
                    | filters.FORWARDED
                    | filters.PHOTO
                    | filters.Document.ALL
                )
                & filters.ChatType.PRIVATE
                & (~filters.COMMAND),
                self.prompt,
            )
        )
        application.add_handler(
            CallbackQueryHandler(self.button_callback, pattern="^final_")
        )

        application.add_error_handler(error_handler)

        application.run_polling(allowed_updates=Update.ALL_TYPES)
