import os
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from vk_channelify.models import Channel


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='TEST_DATABASE_URL is not configured')
def test_channel_crud_against_postgresql() -> None:
    engine = create_engine(os.environ['TEST_DATABASE_URL'])
    connection = engine.connect()
    transaction = connection.begin()
    channel_id = f'-test-{uuid.uuid4()}'

    try:
        with Session(bind=connection) as session:
            session.add(Channel(channel_id=channel_id, vk_group_id='integration', owner_id='1'))
            session.flush()

            channel = session.scalars(select(Channel).where(Channel.channel_id == channel_id)).one()
            channel.last_vk_post_id = 42
            session.flush()

            assert channel.vk_group_id == 'integration'
            assert channel.last_vk_post_id == 42
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
