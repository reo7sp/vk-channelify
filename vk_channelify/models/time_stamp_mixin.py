from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, DateTime, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TimeStampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    @staticmethod
    def _updated_at(mapper: Mapper[Any], connection: Connection, target: TimeStampMixin) -> None:
        target.updated_at = utc_now()

    @classmethod
    def __declare_last__(cls) -> None:
        event.listen(cls, 'before_update', cls._updated_at)
