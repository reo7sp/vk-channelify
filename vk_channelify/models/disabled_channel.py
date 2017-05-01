from sqlalchemy import Column, String, Integer

from . import Base


class DisabledChannel(Base):
    __tablename__ = 'disabled_channels'

    vk_group_id = Column(String, primary_key=True)
