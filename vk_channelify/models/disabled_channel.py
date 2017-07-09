from sqlalchemy import Column, String, Integer

from . import Base


class DisabledChannel(Base):
    __tablename__ = 'disabled_channels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, nullable=False)
    vk_group_id = Column(String, nullable=False)
    last_vk_post_id = Column(Integer, nullable=False, server_default='0')
    owner_id = Column(String, nullable=False)
    owner_username = Column(String)
    hashtag_filter = Column(String)

