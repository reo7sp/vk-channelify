from sqlalchemy import Column, String, Integer

from . import Base


class DisabledChannel(Base):
    __tablename__ = 'disabled_channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    vk_group_id = Column(String)
    last_vk_post_id = Column(Integer)
    owner_id = Column(String)
    owner_username = Column(String)
    hashtag_filter = Column(String)

