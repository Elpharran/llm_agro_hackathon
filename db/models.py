from db.connection import get_engine
from bot.src.logger_download import logger
from sqlalchemy import ( DateTime, Float, Integer, MetaData, String)
from sqlalchemy.orm import declarative_base, mapped_column
from sqlalchemy.schema import CreateSchema

SCHEMA_NAME = "reports"

engine = get_engine()
metadata = MetaData()
Base = declarative_base(metadata=metadata)


class OperationInfo(Base):
    __tablename__ = "generation_info"
    __table_args__ = {'schema': SCHEMA_NAME}

    id = mapped_column(Integer, primary_key=True)
    date = mapped_column(DateTime, nullable=True)
    unit = mapped_column(String(255), nullable=False)
    operation = mapped_column(String(255), nullable=False)
    cultura = mapped_column(String(255), nullable=False)
    GA_per_day = mapped_column(Integer, nullable=False)
    GA_per_operation = mapped_column(Integer, nullable=False)
    val_per_day = mapped_column(Float, nullable=True, default=0)
    val_per_operation = mapped_column(Float, nullable=False, default=0)


    def to_dict(self):
        return {
            "id": self.id,
            "Дата": self.date,
            "Подразделение": self.unit,
            "Операция": self.operation,
            "Культура": self.cultura,
            "За день, га": self.GA_per_day,
            "С начала операции, га": self.GA_per_operation,
            "Вал за день, ц": self.val_per_day,
            "Вал с начала, ц": self.val_per_operation,
        }

def create_all():
    try:
        logger.info("Connecting")
        with engine.connect() as conn:
            logger.info(
                "Connection established. Starting to create schema"
            )
            conn.execute(CreateSchema(SCHEMA_NAME, if_not_exists=True))
            conn.commit()
            logger.info("Schema created. Changes commited")
            logger.info("No tables found. Creating tables...")
            Base.metadata.create_all(conn)
            conn.commit()
            logger.info("Tables created. Changes committed")
        logger.info("All done, connection closed.")
    except Exception as e:
        logger.info("Something went wrong, and that's why:")
        logger.info(e)
