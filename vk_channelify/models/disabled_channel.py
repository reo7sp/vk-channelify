from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class DisabledChannel(Base):
    __tablename__ = 'disabled_channels'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String, nullable=False)
    vk_group_id: Mapped[str] = mapped_column(String, nullable=False)
    last_vk_post_id: Mapped[int] = mapped_column(nullable=False, server_default='0')
    owner_id: Mapped[str] = mapped_column(String, nullable=False)
    owner_username: Mapped[str | None] = mapped_column(String)
    hashtag_filter: Mapped[str | None] = mapped_column(String)
