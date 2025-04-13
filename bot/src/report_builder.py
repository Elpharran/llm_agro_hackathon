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

ERROR_TEXT = (
    "Ваш отчёт не может быть обработан 😭"
)
allowed_entities = load_entities()


class OperationEntry(BaseModel):
    Дата: datetime = Field(..., description="Дата операции в формате ДД.ММ.ГГГГ")
    Операция: str = Field(..., description="Название операции")
    Данные: str = Field(..., description="Дополнительные данные об операции")
    Подразделение: Optional[str] = None
    Культура: Optional[str] = None
    За_день_га: Optional[Union[int, str]] = Field(None, alias="За день, га")
    С_начала_операции_га: Optional[Union[int, str]] = Field(None, alias="С начала операции, га")
    Вал_за_день_ц: Optional[Union[int, str]] = Field(None, alias="Вал за день, ц")
    Вал_с_начала_ц: Optional[Union[int, str]] = Field(None, alias="Вал с начала, ц")

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
        if v not in allowed_entities["type"]:
            raise ValueError(f"Операция '{v}' не в списке допустимых.")
        return v

    @field_validator("Культура")
    def validate_culture(cls, v):
        if v and v not in allowed_entities["culture"]:
            raise ValueError(f"Культура '{v}' не в списке допустимых.")
        return v

    @field_validator("Подразделение")
    def validate_division(cls, v):
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

    def _correct_fields(self, field: str, data: dict) -> dict:
        logger.warning(f"🚩 Correcting field {field}")
        logger.warning(data)

        if field == "Операция":
            allowed = ", ".join(allowed_entities["type"])
        if field == "Культура":
            allowed = ", ".join(allowed_entities["culture"])
        if field == "Подразделение":
            allowed = ", ".join(allowed_entities["division"])

        prompt = load_prompt(
            prompt_path="prompts/5. validation_fields.md",
            validation=True,
            report=str(data),
            field=field,
            allowed=allowed,
        )
        return self.model.predict(prompt)

    def _correct_json(self, data: str) -> dict:
        logger.warning("🚩 Correcting JSON structure")
        logger.warning(data)
        prompt = load_prompt(
            prompt_path="prompts/5. validation_json.md",
            validation=True,
            report=data,
        )
        return self.model.predict(prompt)

    def _validate(self, report: str, field=None, initial=False) -> dict:
        try:
            cleaned = clean_string(report)
            if cleaned == "Отчёт не может быть обработан.":
                raise ValueError("Poor quality data, nothing to extract")
            parsed = json.loads(cleaned)

            if initial:
                return OperationList.model_validate(parsed).model_dump(
                    exclude_none=True
                )
            return OperationEntry(**parsed).model_dump(exclude_none=True)

        except ValidationError:
            correction = self._correct_fields(field, parsed)
            if initial:
                return OperationList.model_validate(correction).model_dump(
                    exclude_none=True
                )
            return OperationEntry(
                **ast.literal_eval(clean_string(correction))
            ).model_dump(exclude_none=True)

        except json.decoder.JSONDecodeError:
            correction = self._correct_json(report if initial else clean_string(report))
            if initial:
                return OperationList.model_validate(
                    ast.literal_eval(clean_string(correction))
                ).model_dump(exclude_none=True)
            return OperationEntry(**correction).model_dump(exclude_none=True)

        except Exception:
            logger.error("Unexpected error:")
            logger.error(traceback.format_exc())
            raise

    def _gather_validated(
        self, prompt: str, report_data: list[dict], field=None
    ) -> list[dict]:
        validated = []
        for entry in report_data:
            raw_report = self.model.predict(prompt, str(entry))
            validated_entry = self._validate(raw_report, field=field)
            validated.append(validated_entry)
        return validated

    def _process_stage(
        self, report_data: Union[dict, str], prompt_path, field=None, initial=False
    ):
        if initial:
            prompt = load_prompt(prompt_path, definition=True)
            reports = self.model.predict(prompt, report_data)

            logger.info(reports)

            return self._validate(reports, initial=initial, field=field)
        else:
            prompt = load_prompt(prompt_path)
            return self._gather_validated(prompt, report_data, field=field)

    def build(self, report_data: str) -> list[dict]:
        processing_steps = [
            ("prompts/1. date_and_type_definition.md", "Операция", True),
            ("prompts/2. culture_definition.md", "Культура", False),
            ("prompts/3. division_definition.md", "Подразделение", False),
            ("prompts/4. calculation.md", None, False),
        ]
        result = report_data
        for prompt_path, field, initial in processing_steps:
            logger.info(f"Processing field: {field if field else 'Вычисления'}")
            try:
                result = self._process_stage(result, prompt_path, field, initial)
            except Exception:
                return ERROR_TEXT

        for item in result:
            item["Дата"] = item["Дата"].strftime("%d.%m.%Y")
            item["За день, га"] = item.pop("За_день_га")
            item["С начала операции, га"] = item.pop("С_начала_операции_га")
            item["Вал за день, ц"] = item.pop("Вал_за_день_ц")
            item["Вал с начала, ц"] = item.pop("Вал_с_начала_ц")

        return result
