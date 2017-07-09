from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from .time_stamp_mixin import TimeStampMixin


class Base(TimeStampMixin):
    pass


Base = declarative_base(cls=Base)

from .channel import Channel
from .disabled_channel import DisabledChannel


def connect_db(url):
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    db = Session()
    return db
