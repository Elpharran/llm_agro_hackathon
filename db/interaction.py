from db.connection import session_scope
from db.models import OperationInfo
import pandas as pd

mapping = {
    "Дата": "date",
    "Подразделение": "unit",
    "Операция": "operation",
    "Культура": "cultura",
    "За день, га": "GA_per_day",
    "С начала операции, га": "GA_per_operation",
    "Вал за день, ц": "val_per_day",
    "Вал с начала, ц": "val_per_operation",
}


def get_all_operations():
    with session_scope() as session:
        data = session.query(OperationInfo).all()
        records = [model.to_dict() for model in data]
        df = pd.DataFrame(records)
        return df


def insert_objects(records):
    with session_scope() as session:
        mapped_records = []
        for record in records:
            mapped_fields = {}
            for key, value in record.items():
                column_name = mapping.get(key)
                if column_name:
                    mapped_fields[column_name] = value
            mapped_records.append(mapped_fields)
        objects = [OperationInfo(**record) for record in mapped_records]
        session.bulk_save_objects(objects)
        session.commit()


def update_record_by_id(record_id, new_data):
    """
    Обновляет запись по ID с учетом только переданных полей.

    param record_id: ID записи, которую нужно обновить
    param new_data: Словарь с данными для обновления (передаются только измененные поля)
    """
    with session_scope() as session:

        record = (
            session.query(OperationInfo).filter(OperationInfo.id == record_id).first()
        )

        if record:
            if "Дата" in new_data:
                record.date = new_data["Дата"]
            if "Подразделение" in new_data:
                record.unit = new_data["Подразделение"]
            if "Операция" in new_data:
                record.operation = new_data["Операция"]
            if "Культура" in new_data:
                record.cultura = new_data["Культура"]
            if "За день, га" in new_data:
                record.GA_per_day = new_data["За день, га"]
            if "С начала операции, га" in new_data:
                record.GA_per_operation = new_data["С начала операции, га"]
            if "Вал за день, ц" in new_data:
                record.val_per_day = new_data["Вал за день, ц"]
            if "Вал с начала, ц" in new_data:
                record.val_per_operation = new_data["Вал с начала, ц"]
            session.commit()
            return record
        else:
            return None
