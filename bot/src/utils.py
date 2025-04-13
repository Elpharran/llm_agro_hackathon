from __future__ import annotations

import asyncio
import builtins
import json
import os
import re
import subprocess
import tempfile
import time
import traceback
from datetime import date
from typing import Union

import httpx
import markdown
import mistralai
import pandas as pd
import requests
import telegram
import yaml
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from dotenv import load_dotenv
from mistral_common.protocol.instruct.request import ChatCompletionRequest
from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
from mistralai import Mistral
from src.logger_download import logger
from telegram import InlineKeyboardMarkup, MessageEntity, Update, constants
from telegram.ext import CallbackContext, ContextTypes

load_dotenv(override=True)

UPLOAD_FOLDER = tempfile.gettempdir()
with open("src/messages.json", "r", encoding="utf-8") as f:
    reply_messages = json.load(f)


class MistralAPIInference:
    """
    Base class for LLMs hosted via Mistral API.

    Parameters
    ----------
    api_key : str
        The API key of the free API Mistral model.
    proxy_url : str
        The http proxy url for mistral client.
        Required format:
            `socks5://{username}:{password}@{proxy_host}:{proxy_port}`
    model_name : str
        Name of the model to be used.
    version : str
        Version of the model.
    config_path : str
        Path to the configuration files.

    Attributes
    ----------
    mistral_api_key : str
        The API key of the free API Mistral model.
    model_name : str
        The name of the model used for inference.
    params : dict
        Configuration parameters for the model.
    generation_params : dict
        Parameters used for text generation, including temperature and other settings.
    system_prompt : str
        The initial prompt used to guide the generation, which can be modified.
    """

    def __init__(
        self,
        api_key: str,
        proxy_url: str,
        config_path: str,
        model_name: str = "mistral-large",
        version: str = "2411",
    ):
        self.mistral_api_key = api_key
        self.model = f"{model_name}-{version}"

        with builtins.open(config_path) as models_config_file:
            self.params = yaml.safe_load(models_config_file)[model_name]

        self.set_generation_params()

        try:
            http_client = httpx.Client(proxy=proxy_url)
            self.mistral_client = Mistral(
                api_key=self.mistral_api_key, client=http_client
            )
            mistral_client_models = [
                m.name for m in self.mistral_client.models.list().data
            ]
            if self.model in mistral_client_models:
                self.is_dummy = False
            else:
                self.is_dummy = True

            self.tokenizer_v3 = MistralTokenizer.v3(is_tekken=True)

        except Exception as e:
            print(e)
            self.is_dummy = True

        if self.is_dummy:
            print(
                f"""Model {model_name} can't be initialized, check if model name is correct/model is availiable.
    This is dummy initialization just not to throw Exception. No other methods are availiable.
    To actually use the model, reinitialize it after checking what's wrong with the it."""
            )

    def set_generation_params(
        self,
        temperature: float = 0.0,
        system_prompt: str = "default",
    ) -> Union[None, str]:
        """
        Set the parameters used for text generation.

        Parameters
        ----------
        temperature : float, default=0.0
            Temperature setting for text generation.
        system_prompt : {"default", str}, default="default"
            Default system prompt from the model configuration.
            If True, enables the model to process sensitive topics.
        Returns
        -------
        None
        """
        self.generation_params = self.params["GENERATION_PARAMETERS"]
        self.generation_params.update({"temperature": temperature})
        self.system_prompt = (
            "You are helpful assistant" if system_prompt == "default" else system_prompt
        )

    def predict(
        self,
        instruction: str,
        text: str = "",
    ) -> str:
        """
        Generate a text response based on the provided instruction and optional text.

        Parameters
        ----------
        instruction : str
            The instruction or user prompt for task completion.
        text : str, optional, default=""
            Text to be analyzed according to the given instruction.
        Returns
        -------
        str
            The generated text response.
        """
        user_prompt = f"""{instruction}\n\n```{text}```""" if text else instruction
        messages = []
        messages.append(dict(role="system", content=self.system_prompt))
        messages.append(dict(role="user", content=user_prompt))

        fit, tokens = self._check_tokens_fit(messages)

        if tokens == 0:
            raise RuntimeError("Выбранная модель более не доступна через API Mistral.")
        if fit:
            try:
                prediction = (
                    self.mistral_client.chat.complete(
                        model=self.model,
                        messages=messages,
                        temperature=self.generation_params["temperature"],
                    )
                    .choices[0]
                    .message.content
                )
                time.sleep(1)

                return prediction
            except mistralai.models.sdkerror.SDKError:
                logger.warning("Rate limit exceeded. Sleeping for 60.")
                time.sleep(60)
                prediction = (
                    self.mistral_client.chat.complete(
                        model=self.model,
                        messages=messages,
                        temperature=self.generation_params["temperature"],
                    )
                    .choices[0]
                    .message.content
                )
                return prediction
            except requests.exceptions.HTTPError as http_err:
                print(
                    f"HTTP error occurred: {http_err.response.status_code} - {http_err.response.text}"
                )
                raise http_err
            except Exception as e:
                if isinstance(e, requests.exceptions.ConnectionError):
                    print(f"Connection error occurred: {e}")
                elif isinstance(e, requests.exceptions.Timeout):
                    print(f"Request timed out: {e}")
                else:
                    print(f"An error occurred: {e}")
                    traceback.print_exc()
                raise e
        else:
            raise ValueError(
                f"""Tokens count limit exceeded, consider cutting history or increasing
    `max_context_length` parameter before making prediction.
    Token count for current prompt: {tokens}"""
            )

    def _check_tokens_fit(self, messages):
        """
        Check if the token count of the generated prompt exceeds the model's context length limit.

        Parameters
        ----------
        prompt : str
            The prompt to be checked.

        Raises
        ------
        ValueError
            If the token count exceeds the model's context length.
        """

        if not self.is_dummy:
            try:
                tokenized = self.tokenizer_v3.encode_chat_completion(
                    ChatCompletionRequest(messages=messages)
                )
                tokens, _ = tokenized.tokens, tokenized.text

                tokencnt = len(tokens)
                if tokencnt >= self.generation_params["max_tokens"]:
                    return False, tokencnt
                else:
                    return True, tokencnt
            except requests.exceptions.ConnectTimeout:
                return False, "no response"
        else:
            return False, 0


def load_entities():
    with open("src/allowed_entities.json", "r") as f:
        entities = json.load(f)

    return entities


def get_reply_text(key):
    """
    Return text for a key.
    Keys and messages can be found in the messages.json.
    """
    return reply_messages[key]


async def is_allowed(config, update: Update, context: CallbackContext) -> bool:
    """
    Checks if the user is allowed to use the bot.
    """
    # If allowed_user_ids is "*" in config, allow everyone
    if config["allowed_user_ids"] == "*":
        return True

    user_id = update.message.from_user.id

    if is_admin(config, user_id):
        return True

    if user_id in config["allowed_user_ids"].split(","):
        return True

    return False


def is_admin(config, user_id: int, log_no_admin=False) -> bool:
    """
    Checks if the user is the admin of the bot.
    The first user in the user list is the admin.
    """
    if config["admin_user_ids"] == "-":
        if log_no_admin:
            logger.warning("No admin user defined.")
            logger.warning("No admin user defined.")
        return False

    admin_user_ids = config["admin_user_ids"].split(",")

    # Check if user is in the admin user list
    if str(user_id) in admin_user_ids:
        return True

    return False


def markdown_to_string(file_path):
    """
    Reads a Markdown file and converts it into a formatted string.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            markdown_content = file.read()

        html_content = markdown.markdown(markdown_content)

        return html_content
    except FileNotFoundError:
        return "Error: File not found."
    except Exception as e:
        return f"Error: {e}"


def load_prompt(
    prompt_path,
    definition=False,
    validation=False,
    report=None,
    field=None,
    allowed=None,
):
    if definition:
        today = date.today()
        year = today.year
        entities = load_entities()
        division = entities["division"]
        subdivision = entities["subdivision"]
        formatted_date = today.isoformat()
        return markdown_to_string(prompt_path).format(
            year=year, date=formatted_date, division=division + subdivision
        )
    if validation:
        if field:
            return markdown_to_string(prompt_path).format(
                report=report, field=field, allowed=allowed
            )
        else:
            return markdown_to_string(prompt_path).format(report=report)
    return markdown_to_string(prompt_path)


def clean_string(json_string):
    cleaned_string = re.sub(r"```json|```", "", json_string)
    cleaned_string = re.sub(r"\\n", "", cleaned_string)
    cleaned_string = re.sub(r"\n", "", cleaned_string)
    cleaned_string = re.sub(r"\s+", " ", cleaned_string)
    cleaned_string = re.sub(r"\t", " ", cleaned_string)
    cleaned_string = re.sub(r"\\t", " ", cleaned_string)
    cleaned_string = re.sub(r'\\([^"\\/bfnrt])', r"\\\\\1", cleaned_string)
    cleaned_string = re.sub(r"([}\]])\s*([{\[])", r"\1,\2", cleaned_string)
    return cleaned_string.strip()


def message_text(update: Update, reset=False) -> str:
    """
    Returns the text of a message, excluding any bot commands.
    If reset is True, extracts the message or caption excluding bot commands.
    """
    message_txt = update.message.caption or update.message.text or ""

    if reset:
        # Try removing bot commands from message_txt to return user's system prompt
        # If not removed, returns command as is, in reset method of tgbot basic system prompt is inserted
        try:
            for _, text in sorted(
                update.message.parse_entities([MessageEntity.BOT_COMMAND]).items(),
                key=(lambda item: item[0].offset),
            ):
                if text == "/reset":
                    message_txt = message_txt.replace(text, "").strip()
                    logger.info(
                        "Removing bot reset command text inside 'message_text', returning empty str."
                    )
                else:
                    message_txt = text.replace("/reset", "").strip()
                    logger.info(
                        f"Removing bot reset command text inside 'message_text', returning new system promt {message_txt}"
                    )

        except Exception as e:
            logger.error(f"Error parsing bot commands: {e}")
            # Fallback to original message text
            message_txt = update.message.caption or update.message.text

    return message_txt


async def edit_message_with_retry(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | None,
    message_id: str,
    text: str,
    html: bool = False,
    reply_markup: InlineKeyboardMarkup = None,
):
    """
    Edit a message with retry logic in case of failure (e.g. broken markdown)
    :param context: The context to use
    :param chat_id: The chat id to edit the message in
    :param message_id: The message id to edit
    :param text: The text to edit the message with
    :param markdown: Whether to use markdown parse mode
    :return: None
    """
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=int(message_id),
            text=text,
            parse_mode=constants.ParseMode.HTML if html else None,
            reply_markup=reply_markup,
        )
    except telegram.error.RetryAfter as e:
        logger.warning(
            f"Flood control exceeded for chat id {chat_id}, going to sleep for {e.retry_after}."
        )
        await asyncio.sleep(e.retry_after)
        await edit_message_with_retry(
            context, chat_id, message_id, text, markdown, reply_markup=reply_markup
        )

    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            return
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(message_id),
                text=text,
            )
        except Exception as e:
            logger.exception(f"Failed to edit message: {str(e)}")
            raise e

    except Exception as e:
        logger.exception(str(e))
        raise e


async def error_handler(_: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles errors in the telegram-python-bot library.
    """
    logger.error(f"Exception while handling an update: {context.error}")
    try:
        logger.error(f"DETAILS on error: {str(context.error), traceback.format_exc()}")
    except Exception:
        logger.error(traceback.format_exc())


async def manage_attachment(
    model, update: Update, context: CallbackContext, file=None, photo=None
):
    if file:
        file_name = file.file_name
        file_extension = os.path.splitext(file_name)[1].lower()
        file_path = os.path.join(UPLOAD_FOLDER, file_name)
        file_obj = await context.bot.get_file(file.file_id)

    elif photo:
        file_name = "image.png"
        file_extension = os.path.splitext(file_name)[1].lower()
        file_path = os.path.join(UPLOAD_FOLDER, file_name)
        file_obj = await context.bot.get_file(photo[-1].file_id)

    else:
        return None, "Файл не загружен"

    if file_obj.file_size // 1e6 >= 10:
        await update.message.reply_text(
            "Загруженный файл слишком большой ⚠️ Модель не может его обработать."
        )
        return

    await file_obj.download_to_drive(file_path)

    try:
        file_content = extract_file_content(file_path, file_extension)
        if not model._check_tokens_fit([{"role": "user", "content": file_content}])[0]:
            await update.message.reply_text(
                "Загруженный файл слишком большой ⚠️ Модель не может его обработать."
            )
            return

        return file_content

    except Exception:
        raise


def extract_file_content(file_path: str, file_extension: str) -> str:
    """
    Extract content from the file based on its type.
    Dispatches file processing to specific subfunctions based on the file extension.
    """
    logger.info(
        f"Attempting to extract content from file with extension {file_extension}"
    )

    file_handlers = {
        ".docx": _handle_file,
        ".pdf": _handle_file,
        ".jpg": _handle_file,
        ".jpeg": _handle_file,
        ".png": _handle_file,
        ".xlsx": _handle_excel_file,
        ".xls": _handle_excel_file,
        ".doc": _handle_doc_file,
        ".txt": _handle_text_file,
    }

    if file_extension in list(file_handlers.keys()):
        handler = file_handlers.get(file_extension)

        try:
            content = handler(file_path)
            return content
        except Exception as e:
            logger.error(f"Error reading file {file_path} \: {str(e)}")
            raise RuntimeError(f"Unable to read file with {file_path}")
    else:
        raise ValueError("File extension is not supported.")


def _handle_file(file_path: str) -> str:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.ocr_options = EasyOcrOptions()
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    return converter.convert(file_path).document.export_to_markdown()


def _handle_text_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def _handle_excel_file(file_path: str) -> str:
    df = pd.read_excel(file_path)
    return df.to_markdown()


def _handle_doc_file(file_path: str) -> str:
    result = subprocess.run(
        [
            "libreoffice",
            "--headless",
            "--convert-to",
            "txt",
            file_path,
            "--outdir",
            "/tmp",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        txt_file = file_path.replace(".doc", ".txt")
        if os.path.exists(txt_file):
            with open(txt_file, "r", encoding="utf-8") as f:
                return f.read()
        else:
            return f"Error: Converted TXT file not found at {txt_file}"
    else:
        error_msg = result.stderr.decode("utf-8")
        return f"Error converting DOC file with LibreOffice: {error_msg}"
