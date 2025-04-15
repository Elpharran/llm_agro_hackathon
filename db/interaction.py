from db.connection import session_scope
from db.models import OperationInfo
import pandas as pd


# Функция для получения всех записей в форме DataFrame
def get_all_models_as_dataframe():
    with session_scope() as session:
        data = session.query(OperationInfo).all()
        records = [model.to_dict() for model in data]
        df = pd.DataFrame(records)
        return df
    
# Вставка записи
def insert_objects(records):
    with session_scope() as session:
        objects = [OperationInfo(**record) for record in records]
        session.bulk_save_objects(objects)
        session.commit()

# Функция для обновления записи по ID
def update_record_by_id(record_id, new_data):
    """
    Обновляет запись по ID с учетом только переданных полей.
    
    param record_id: ID записи, которую нужно обновить
    param new_data: Словарь с данными для обновления (передаются только измененные поля)
    """
    with session_scope() as session:
  
        record = session.query(OperationInfo).filter(OperationInfo.id == record_id).first()
        
        if record:
            if 'date' in new_data:
                record.date = new_data['date']
            if 'unit' in new_data:
                record.unit = new_data['unit']
            if 'operation' in new_data:
                record.operation = new_data['operation']
            if 'cultura' in new_data:
                record.cultura = new_data['cultura']
            if 'GA_per_day' in new_data:
                record.GA_per_day = new_data['GA_per_day']
            if 'GA_per_operation' in new_data:
                record.GA_per_operation = new_data['GA_per_operation']
            if 'val_per_day' in new_data:
                record.val_per_day = new_data['val_per_day']
            if 'val_per_operation' in new_data:
                record.val_per_operation = new_data['val_per_operation']
            session.commit()
            return record
        else:
            return None  # Если запись не найдена