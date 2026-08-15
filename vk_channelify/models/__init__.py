from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .time_stamp_mixin import TimeStampMixin


class Base(TimeStampMixin, DeclarativeBase):
    pass


from .channel import Channel
from .disabled_channel import DisabledChannel


def make_session_maker(url: str) -> sessionmaker[Session]:
    engine = create_engine(url)
    return sessionmaker(bind=engine)
