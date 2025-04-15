import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

load_dotenv()

engine = None

url_object = URL.create(
    "postgresql+psycopg2",
    username=os.getenv("DATABASE_USER"),
    password=os.getenv("DATABASE_PASSWORD"),
    host=os.getenv("DATABASE_HOST"),
    port=os.getenv("DATABASE_PORT"),
    database=os.getenv("DATABASE_NAME"),
)


def get_engine():
    global engine
    if engine is None:
        engine = create_engine(url_object)
    return engine


engine = get_engine()
Session = sessionmaker(bind=engine)


@contextmanager
def session_scope() -> Generator[Session, None, None]: # type: ignore
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()
