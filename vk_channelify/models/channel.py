from sqlalchemy import Column, String, Integer

from . import Base


class Channel(Base):
    __tablename__ = 'channels'

    channel_id = Column(String, primary_key=True, nullable=False)
    vk_group_id = Column(String, nullable=False)
    last_vk_post_id = Column(Integer, nullable=False, server_default='0')
    owner_id = Column(String, nullable=False)
    owner_username = Column(String)
    hashtag_filter = Column(String)
