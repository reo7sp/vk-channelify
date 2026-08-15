import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
import requests
import telegram
from hamcrest import assert_that, equal_to, has_length, is_, none

from vk_channelify.repost_worker import (
    VK_API_TIMEOUT_SECONDS,
    disable_channel,
    extract_group_id_if_has,
    fetch_group_posts,
    is_passing_hashtag_filter,
    run_worker_iteration_with_bot,
)
from vk_channelify.vk_errors import VKError, VKWallAccessDeniedError


class TestRunWorkerIteration:
    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_sends_new_posts(self, mock_metrics: Mock, mock_fetch: Mock) -> None:
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup', last_vk_post_id=10, hashtag_filter=None)
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.return_value = [
            {'id': 11, 'owner_id': -123, 'text': 'New post 1'},
            {'id': 12, 'owner_id': -123, 'text': 'New post 2'},
        ]

        asyncio.run(run_worker_iteration_with_bot('vk_token', mock_bot, mock_db))

        assert_that(mock_bot.send_message.call_count, equal_to(2))
        assert_that(mock_channel.last_vk_post_id, equal_to(12))

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_skips_old_posts(self, mock_metrics: Mock, mock_fetch: Mock) -> None:
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup', last_vk_post_id=10, hashtag_filter=None)
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.return_value = [{'id': 9, 'owner_id': -123, 'text': 'Old post'}]

        asyncio.run(run_worker_iteration_with_bot('vk_token', mock_bot, mock_db))

        mock_bot.send_message.assert_not_called()

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.disable_channel')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_disables_channel_on_forbidden(
        self, mock_metrics: Mock, mock_disable: AsyncMock, mock_fetch: Mock
    ) -> None:
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock(side_effect=telegram.error.Forbidden('Forbidden'))
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup', last_vk_post_id=10, hashtag_filter=None)
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.return_value = [{'id': 11, 'owner_id': -123, 'text': 'New post'}]

        asyncio.run(run_worker_iteration_with_bot('vk_token', mock_bot, mock_db))

        mock_disable.assert_awaited_once_with(mock_channel, mock_db, mock_bot)

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_records_vk_timeout_for_channel(self, mock_metrics: Mock, mock_fetch: Mock) -> None:
        mock_bot = Mock()
        mock_bot.send_message = AsyncMock()
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup', last_vk_post_id=10, hashtag_filter=None)
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.side_effect = requests.Timeout('VK timed out')

        with pytest.raises(requests.Timeout):
            asyncio.run(run_worker_iteration_with_bot('vk_token', mock_bot, mock_db))

        mock_metrics.repost_errors_total.labels.assert_called_once_with(
            error_type='vk_timeout', channel_id='-100123456', vk_group_id='testgroup'
        )
        mock_metrics.repost_errors_total.labels.return_value.inc.assert_called_once_with()

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_records_vk_connection_error(self, mock_metrics: Mock, mock_fetch: Mock) -> None:
        mock_channel = Mock(
            channel_id='-100123456',
            vk_group_id='testgroup',
            last_vk_post_id=10,
            hashtag_filter=None,
        )
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.side_effect = requests.ConnectionError('Connection aborted')

        with pytest.raises(requests.ConnectionError):
            asyncio.run(run_worker_iteration_with_bot('vk_token', Mock(), mock_db))

        mock_metrics.repost_errors_total.labels.assert_called_once_with(
            error_type='vk_connection_error',
            channel_id='-100123456',
            vk_group_id='testgroup',
        )

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_records_generic_vk_request_error(self, mock_metrics: Mock, mock_fetch: Mock) -> None:
        mock_channel = Mock(
            channel_id='-100123456',
            vk_group_id='testgroup',
            last_vk_post_id=10,
            hashtag_filter=None,
        )
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.side_effect = requests.RequestException('Request failed')

        with pytest.raises(requests.RequestException):
            asyncio.run(run_worker_iteration_with_bot('vk_token', Mock(), mock_db))

        mock_metrics.repost_errors_total.labels.assert_called_once_with(
            error_type='vk_request_error',
            channel_id='-100123456',
            vk_group_id='testgroup',
        )

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_records_telegram_timeout(self, mock_metrics: Mock, mock_fetch: Mock) -> None:
        mock_bot = Mock(send_message=AsyncMock(side_effect=telegram.error.TimedOut()))
        mock_channel = Mock(
            channel_id='-100123456',
            vk_group_id='testgroup',
            last_vk_post_id=10,
            hashtag_filter=None,
        )
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.return_value = [{'id': 11, 'owner_id': -123, 'text': 'Post'}]

        asyncio.run(run_worker_iteration_with_bot('vk_token', mock_bot, mock_db))

        mock_metrics.repost_errors_total.labels.assert_called_once_with(
            error_type='telegram_timeout',
            channel_id='-100123456',
            vk_group_id='testgroup',
        )

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.disable_channel')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_disables_missing_chat(
        self, mock_metrics: Mock, mock_disable: AsyncMock, mock_fetch: Mock
    ) -> None:
        mock_bot = Mock(
            send_message=AsyncMock(side_effect=telegram.error.BadRequest('Chat not found')),
        )
        mock_channel = Mock(
            channel_id='-100123456',
            vk_group_id='testgroup',
            last_vk_post_id=10,
            hashtag_filter=None,
        )
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.return_value = [{'id': 11, 'owner_id': -123, 'text': 'Post'}]

        asyncio.run(run_worker_iteration_with_bot('vk_token', mock_bot, mock_db))

        mock_disable.assert_awaited_once_with(mock_channel, mock_db, mock_bot)
        mock_metrics.repost_errors_total.labels.assert_called_once_with(
            error_type='telegram_chat_not_found',
            channel_id='-100123456',
            vk_group_id='testgroup',
        )

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.disable_channel')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_disables_inaccessible_vk_wall(
        self, mock_metrics: Mock, mock_disable: AsyncMock, mock_fetch: Mock
    ) -> None:
        mock_bot = Mock()
        mock_channel = Mock(
            channel_id='-100123456',
            vk_group_id='testgroup',
            last_vk_post_id=10,
            hashtag_filter=None,
        )
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.side_effect = VKWallAccessDeniedError(15, 'Access denied', [])

        asyncio.run(run_worker_iteration_with_bot('vk_token', mock_bot, mock_db))

        mock_disable.assert_awaited_once_with(mock_channel, mock_db, mock_bot)
        mock_metrics.repost_errors_total.labels.assert_called_once_with(
            error_type='vk_wall_access_denied',
            channel_id='-100123456',
            vk_group_id='testgroup',
        )

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_reraises_generic_vk_error(self, mock_metrics: Mock, mock_fetch: Mock) -> None:
        mock_channel = Mock(
            channel_id='-100123456',
            vk_group_id='testgroup',
            last_vk_post_id=10,
            hashtag_filter=None,
        )
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.side_effect = VKError(5, 'Authorization failed', [])

        with pytest.raises(VKError):
            asyncio.run(run_worker_iteration_with_bot('vk_token', Mock(), mock_db))

        mock_metrics.repost_errors_total.labels.assert_called_once_with(
            error_type='vk_api_error',
            channel_id='-100123456',
            vk_group_id='testgroup',
        )

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_reraises_generic_telegram_bad_request(self, mock_metrics: Mock, mock_fetch: Mock) -> None:
        mock_bot = Mock(
            send_message=AsyncMock(side_effect=telegram.error.BadRequest('Invalid message')),
        )
        mock_channel = Mock(
            channel_id='-100123456',
            vk_group_id='testgroup',
            last_vk_post_id=10,
            hashtag_filter=None,
        )
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_fetch.return_value = [{'id': 11, 'owner_id': -123, 'text': 'Post'}]

        with pytest.raises(telegram.error.BadRequest):
            asyncio.run(run_worker_iteration_with_bot('vk_token', mock_bot, mock_db))

        mock_metrics.repost_errors_total.labels.assert_called_once_with(
            error_type='telegram_bad_request',
            channel_id='-100123456',
            vk_group_id='testgroup',
        )

    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_rolls_back_post_position_on_commit_error(self, mock_metrics: Mock, mock_fetch: Mock) -> None:
        mock_bot = Mock(send_message=AsyncMock())
        mock_channel = Mock(
            channel_id='-100123456',
            vk_group_id='testgroup',
            last_vk_post_id=10,
            hashtag_filter=None,
        )
        mock_db = Mock()
        mock_db.scalar.side_effect = [1, 0]
        mock_db.scalars.return_value = iter([mock_channel])
        mock_db.commit.side_effect = RuntimeError('DB Error')
        mock_fetch.return_value = [{'id': 11, 'owner_id': -123, 'text': 'Post'}]

        with pytest.raises(RuntimeError, match='DB Error'):
            asyncio.run(run_worker_iteration_with_bot('vk_token', mock_bot, mock_db))

        mock_db.rollback.assert_called_once_with()


class TestFetchGroupPosts:
    @patch('vk_channelify.repost_worker.requests.get')
    @patch('vk_channelify.repost_worker.time.sleep')
    @patch('vk_channelify.repost_worker.metrics')
    def test_fetch_success(self, mock_metrics: Mock, mock_sleep: Mock, mock_get: Mock) -> None:
        mock_get.return_value.json.return_value = {'response': {'items': [{'id': 1, 'text': 'Post 1'}]}}

        posts = fetch_group_posts('mygroup', 'test_token')

        assert_that(posts, has_length(1))
        assert_that(posts[0]['id'], equal_to(1))
        mock_get.assert_called_once()
        assert_that(mock_get.call_args.kwargs['timeout'], equal_to(VK_API_TIMEOUT_SECONDS))
        mock_metrics.vk_api_requests_total.labels.assert_called_once_with(
            method='wall.get', status='success', vk_group_id='mygroup'
        )

    @patch('vk_channelify.repost_worker.requests.get')
    @patch('vk_channelify.repost_worker.time.sleep')
    @patch('vk_channelify.repost_worker.metrics')
    def test_fetch_access_denied_error(self, mock_metrics: Mock, mock_sleep: Mock, mock_get: Mock) -> None:
        mock_get.return_value.json.return_value = {
            'error': {'error_code': 15, 'error_msg': 'Access denied', 'request_params': []}
        }

        with pytest.raises(VKWallAccessDeniedError):
            fetch_group_posts('mygroup', 'test_token')

    @patch('vk_channelify.repost_worker.requests.get')
    @patch('vk_channelify.repost_worker.time.sleep')
    @patch('vk_channelify.repost_worker.metrics')
    def test_fetch_timeout_is_recorded(self, mock_metrics: Mock, mock_sleep: Mock, mock_get: Mock) -> None:
        mock_get.side_effect = requests.Timeout('VK timed out')

        with pytest.raises(requests.Timeout):
            fetch_group_posts('mygroup', 'test_token')

        mock_metrics.vk_api_requests_total.labels.assert_called_once_with(
            method='wall.get', status='error', vk_group_id='mygroup'
        )
        mock_metrics.vk_api_requests_total.labels.return_value.inc.assert_called_once_with()

    @patch('vk_channelify.repost_worker.requests.get')
    @patch('vk_channelify.repost_worker.time.sleep')
    @patch('vk_channelify.repost_worker.metrics')
    def test_fetch_generic_api_error(self, mock_metrics: Mock, mock_sleep: Mock, mock_get: Mock) -> None:
        mock_get.return_value.json.return_value = {
            'error': {
                'error_code': 5,
                'error_msg': 'Authorization failed',
                'request_params': [],
            },
        }

        with pytest.raises(VKError):
            fetch_group_posts('mygroup', 'test_token')

        mock_metrics.vk_api_requests_total.labels.assert_called_once_with(
            method='wall.get',
            status='error',
            vk_group_id='mygroup',
        )


class TestExtractGroupIdIfHas:
    def test_extract_club_id(self) -> None:
        assert_that(extract_group_id_if_has('club12345'), equal_to('12345'))

    def test_extract_public_id(self) -> None:
        assert_that(extract_group_id_if_has('public67890'), equal_to('67890'))

    def test_domain_name_returns_none(self) -> None:
        assert_that(extract_group_id_if_has('mygroup'), is_(none()))


class TestIsPassingHashtagFilter:
    def test_no_filter_always_passes(self) -> None:
        assert_that(is_passing_hashtag_filter(None, {'text': 'Any text'}), is_(True))

    def test_single_hashtag_match(self) -> None:
        assert_that(is_passing_hashtag_filter('#news', {'text': 'Post with #news'}), is_(True))

    def test_single_hashtag_no_match(self) -> None:
        assert_that(is_passing_hashtag_filter('#news', {'text': 'Post with #other'}), is_(False))

    def test_multiple_hashtags_match(self) -> None:
        assert_that(is_passing_hashtag_filter('#news, #update', {'text': 'Post with #update'}), is_(True))


class TestDisableChannel:
    @patch('vk_channelify.repost_worker.metrics')
    def test_disable_channel_success(self, mock_metrics: Mock) -> None:
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup')
        mock_db = Mock()
        mock_bot = Mock(send_message=AsyncMock())

        asyncio.run(disable_channel(mock_channel, mock_db, mock_bot))

        mock_db.add.assert_called_once()
        mock_db.delete.assert_called_once_with(mock_channel)
        mock_db.commit.assert_called_once()

    @patch('vk_channelify.repost_worker.metrics')
    def test_disable_channel_rollback_on_error(self, mock_metrics: Mock) -> None:
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup')
        mock_db = Mock()
        mock_db.commit.side_effect = RuntimeError('DB Error')

        with pytest.raises(RuntimeError):
            asyncio.run(disable_channel(mock_channel, mock_db, Mock(send_message=AsyncMock())))

        mock_db.rollback.assert_called_once()

    @patch('vk_channelify.repost_worker.metrics')
    def test_disable_channel_ignores_owner_notification_error(self, mock_metrics: Mock) -> None:
        mock_channel = Mock(
            channel_id='-100123456',
            vk_group_id='testgroup',
            owner_id='12345',
            owner_username='testuser',
        )
        mock_db = Mock()
        mock_bot = Mock(
            send_message=AsyncMock(side_effect=telegram.error.Forbidden('Forbidden')),
        )

        asyncio.run(disable_channel(mock_channel, mock_db, mock_bot))

        mock_db.commit.assert_called_once_with()
