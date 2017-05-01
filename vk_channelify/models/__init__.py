from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

from .channel import Channel


def connect(url: str):
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    db = Session()
    return db
