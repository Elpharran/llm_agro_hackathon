from __future__ import annotations

import ast
import json
import traceback
from datetime import datetime
from typing import List, Optional, Union

from pydantic import (
    BaseModel,
    Field,
    RootModel,
    ValidationError,
    field_validator,
    model_validator,
)
from src.logger_download import logger
from src.utils import (
    MistralAPIInference,
    clean_string,
    load_entities,
    load_prompt,
)

ERROR_TEXT = "Ваш отчёт не может быть обработан 😭 Попробуйте переформулировать текст или приложить фото таблицы хорошего качества."
allowed_entities = load_entities()


class OperationEntry(BaseModel):
    Дата: datetime = Field(..., description="Дата операции в формате ДД.ММ.ГГГГ")
    Операция: str = Field(..., description="Название операции")
    Данные: str = Field(..., description="Дополнительные данные об операции")
    Подразделение: Optional[str] = None
    Культура: Optional[str] = None
    За_день_га: Optional[Union[int, str]] = Field(None, alias="За день, га")
    С_начала_операции_га: Optional[Union[int, str]] = Field(
        None, alias="С начала операции, га"
    )
    Вал_за_день_ц: Optional[Union[int, float, str]] = Field(
        None, alias="Вал за день, ц"
    )
    Вал_с_начала_ц: Optional[Union[int, float, str]] = Field(
        None, alias="Вал с начала, ц"
    )

    @model_validator(mode="before")
    @classmethod
    def validate_date(cls, data: dict) -> dict:
        if "Дата" in data:
            date_str = data["Дата"]
            try:
                parsed_date = datetime.strptime(date_str, "%d.%m.%Y")
            except ValueError:
                try:
                    parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    raise ValueError(
                        f"Invalid date format: {date_str}. "
                        "Use either ДД.ММ.ГГГГ or YYYY-MM-DD"
                    )
            data["Дата"] = parsed_date.strftime("%d.%m.%Y")
            data["Дата"] = datetime.strptime(data["Дата"], "%d.%m.%Y")
        return data

    @field_validator("Операция")
    def validate_operation(cls, v):

        allowed_entities["type"].append("Не определено")
        if v not in allowed_entities["type"]:
            raise ValueError(f"Операция '{v}' не в списке допустимых.")
        return v

    @field_validator("Культура")
    def validate_culture(cls, v):
        allowed_entities["culture"].append("Не определено")
        if v and v not in allowed_entities["culture"]:
            raise ValueError(f"Культура '{v}' не в списке допустимых.")
        return v

    @field_validator("Подразделение")
    def validate_division(cls, v):
        allowed_entities["division"].append("Не определено")
        if v and v not in allowed_entities["division"]:
            raise ValueError(f"Подразделение '{v}' не в списке допустимых.")
        return v


class OperationList(RootModel[List[OperationEntry]]):
    pass


class ReportBuilder:
    def __init__(self, config: dict):
        self.config = config
        self.model = MistralAPIInference(
            config_path="src/configs/mistral_api.cfg.yml",
            api_key=config["mistral_api_key"],
            proxy_url=None,
        )
        self.model.set_generation_params(system_prompt=config["assistant_prompt"])

    def _correct_fields(self, report: dict) -> dict:
        logger.warning("🚩 Correcting fields")
        logger.warning(report)

        prompt = load_prompt(
            "prompts/3. validation_fields.md", validation=True, report=str(report)
        )
        return self.model.predict(prompt)

    def _correct_json(self, report: str) -> dict:
        logger.warning("🚩 Correcting JSON structure")
        logger.warning(report)
        prompt = load_prompt(
            "prompts/4. validation_json.md",
            validation=True,
            report=report,
        )
        return self.model.predict(prompt, report)

    def _validate(self, reports: str) -> dict:
        try:
            cleaned = clean_string(reports)

            if "Отчёт не может быть обработан." in cleaned:
                raise ValueError("Poor quality data, nothing to extract")

            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                parsed = [
                    json.loads(clean_string(item)) if isinstance(item, str) else item
                    for item in parsed
                ]
            for item in parsed:
                try:
                    parsed_date = datetime.fromisoformat(item["Дата"])
                    item["Дата"] = parsed_date.strftime("%d.%m.%Y")
                except ValueError:
                    pass

            return OperationList.model_validate(parsed).model_dump(exclude_none=True)

        except ValidationError:
            correction = self._correct_fields(parsed)
            return OperationList.model_validate(
                ast.literal_eval(clean_string(correction))
            ).model_dump(exclude_none=True)

        except json.decoder.JSONDecodeError:
            correction = self._correct_json(reports)
            return OperationList.model_validate(
                ast.literal_eval(clean_string(correction))
            ).model_dump(exclude_none=True)

        except Exception:
            logger.error("Unexpected error:")
            logger.error(traceback.format_exc())
            raise

    def _gather_raw_results(self, prompt: str, report_data: list[dict]) -> list[str]:
        reports = []
        for report in report_data:
            raw_report = self.model.predict(prompt, str(report))
            reports.append(raw_report)
        return reports

    def _process_stage(
        self,
        report_data: Union[list[dict], str],
        prompt_path: str,
        initial=False,
    ) -> list[dict]:
        if initial:
            prompt = load_prompt(prompt_path, definition=True)
            reports = self.model.predict(prompt, report_data)
            logger.info(reports)
            return self._validate(reports)

        prompt = load_prompt(prompt_path, definition=False)
        reports = self._gather_raw_results(prompt, report_data)
        return self._validate(
            json.dumps(reports, ensure_ascii=False, indent=2, sort_keys=False)
        )

    def build(self, report_data: str) -> list[dict]:
        processing_steps = [
            (
                "prompts/1. initial.md",
                "Дата, операция, культура",
                True,
            ),
            ("prompts/2. final.md", "Подразделение, вычисления", False),
        ]

        result = report_data
        for prompt_path, field, initial in processing_steps:
            logger.info(f"Processing step: {field}")
            result = self._process_stage(result, prompt_path, initial)

        try:
            for item in result:
                item["Дата"] = item["Дата"].strftime("%d.%m.%Y")
                item["За день, га"] = item.pop("За_день_га")
                item["С начала операции, га"] = item.pop("С_начала_операции_га")
                item["Вал за день, ц"] = item.pop("Вал_за_день_ц")
                item["Вал с начала, ц"] = item.pop("Вал_с_начала_ц")

            return result
        except Exception:
            return ERROR_TEXT
