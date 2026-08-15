from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from vk_channelify.models.time_stamp_mixin import TimeStampMixin


class Base(TimeStampMixin, DeclarativeBase):
    pass


from vk_channelify.models.channel import Channel as Channel  # noqa: E402
from vk_channelify.models.disabled_channel import DisabledChannel as DisabledChannel  # noqa: E402


def make_session_maker(url: str) -> sessionmaker[Session]:
    engine = create_engine(url)
    return sessionmaker(bind=engine)
