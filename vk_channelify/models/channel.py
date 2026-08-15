from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class Channel(Base):
    __tablename__ = 'channels'

    channel_id: Mapped[str] = mapped_column(String, primary_key=True)
    vk_group_id: Mapped[str] = mapped_column(String, nullable=False)
    last_vk_post_id: Mapped[int] = mapped_column(nullable=False, server_default='0', default=0)
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    owner_username: Mapped[str | None] = mapped_column(String)
    hashtag_filter: Mapped[str | None] = mapped_column(String)
