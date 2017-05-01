from sqlalchemy import Column, String

from . import Base


class Channel(Base):
    __tablename__ = 'channels'

    channel_id = Column(String, primary_key=True)
    vk_group_id = Column(String)
