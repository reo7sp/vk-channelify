import pytest
from unittest.mock import Mock, patch
import telegram
from hamcrest import assert_that, equal_to, is_, none, has_length

from vk_channelify.repost_worker import (
    extract_group_id_if_has,
    is_passing_hashtag_filter,
    fetch_group_posts,
    disable_channel,
    run_worker_iteration
)
from vk_channelify.vk_errors import VkError, VkWallAccessDeniedError


class TestRunWorkerIteration:
    @patch('vk_channelify.repost_worker.telegram.Bot')
    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_sends_new_posts(self, mock_metrics, mock_fetch, mock_bot_class):
        mock_bot = Mock()
        mock_bot_class.return_value = mock_bot
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup', last_vk_post_id=10, hashtag_filter=None)
        mock_db = Mock()
        mock_db.query.return_value.count.return_value = 1
        mock_db.query.return_value.__iter__ = Mock(return_value=iter([mock_channel]))
        mock_fetch.return_value = [
            {'id': 11, 'owner_id': -123, 'text': 'New post 1'},
            {'id': 12, 'owner_id': -123, 'text': 'New post 2'}
        ]

        run_worker_iteration('vk_token', 'tg_token', mock_db)

        assert_that(mock_bot.send_message.call_count, equal_to(2))
        assert_that(mock_channel.last_vk_post_id, equal_to(12))

    @patch('vk_channelify.repost_worker.telegram.Bot')
    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_skips_old_posts(self, mock_metrics, mock_fetch, mock_bot_class):
        mock_bot = Mock()
        mock_bot_class.return_value = mock_bot
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup', last_vk_post_id=10, hashtag_filter=None)
        mock_db = Mock()
        mock_db.query.return_value.count.return_value = 1
        mock_db.query.return_value.__iter__ = Mock(return_value=iter([mock_channel]))
        mock_fetch.return_value = [{'id': 9, 'owner_id': -123, 'text': 'Old post'}]

        run_worker_iteration('vk_token', 'tg_token', mock_db)

        mock_bot.send_message.assert_not_called()

    @patch('vk_channelify.repost_worker.telegram.Bot')
    @patch('vk_channelify.repost_worker.fetch_group_posts')
    @patch('vk_channelify.repost_worker.disable_channel')
    @patch('vk_channelify.repost_worker.metrics')
    def test_iteration_disables_channel_on_unauthorized(self, mock_metrics, mock_disable, mock_fetch, mock_bot_class):
        mock_bot = Mock()
        mock_bot_class.return_value = mock_bot
        mock_bot.send_message.side_effect = telegram.error.Unauthorized('Unauthorized')
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup', last_vk_post_id=10, hashtag_filter=None)
        mock_db = Mock()
        mock_db.query.return_value.count.return_value = 1
        mock_db.query.return_value.__iter__ = Mock(return_value=iter([mock_channel]))
        mock_fetch.return_value = [{'id': 11, 'owner_id': -123, 'text': 'New post'}]

        run_worker_iteration('vk_token', 'tg_token', mock_db)

        mock_disable.assert_called_once_with(mock_channel, mock_db, mock_bot)


class TestFetchGroupPosts:
    @patch('vk_channelify.repost_worker.requests.get')
    @patch('vk_channelify.repost_worker.time.sleep')
    @patch('vk_channelify.repost_worker.metrics')
    def test_fetch_success(self, mock_metrics, mock_sleep, mock_get):
        mock_get.return_value.json.return_value = {
            'response': {'items': [{'id': 1, 'text': 'Post 1'}]}
        }

        posts = fetch_group_posts('mygroup', 'test_token')

        assert_that(posts, has_length(1))
        assert_that(posts[0]['id'], equal_to(1))

    @patch('vk_channelify.repost_worker.requests.get')
    @patch('vk_channelify.repost_worker.time.sleep')
    @patch('vk_channelify.repost_worker.metrics')
    def test_fetch_access_denied_error(self, mock_metrics, mock_sleep, mock_get):
        mock_get.return_value.json.return_value = {
            'error': {'error_code': 15, 'error_msg': 'Access denied', 'request_params': []}
        }

        with pytest.raises(VkWallAccessDeniedError):
            fetch_group_posts('mygroup', 'test_token')


class TestExtractGroupIdIfHas:
    def test_extract_club_id(self):
        assert_that(extract_group_id_if_has('club12345'), equal_to('12345'))

    def test_extract_public_id(self):
        assert_that(extract_group_id_if_has('public67890'), equal_to('67890'))

    def test_domain_name_returns_none(self):
        assert_that(extract_group_id_if_has('mygroup'), is_(none()))


class TestIsPassingHashtagFilter:
    def test_no_filter_always_passes(self):
        assert_that(is_passing_hashtag_filter(None, {'text': 'Any text'}), is_(True))

    def test_single_hashtag_match(self):
        assert_that(is_passing_hashtag_filter('#news', {'text': 'Post with #news'}), is_(True))

    def test_single_hashtag_no_match(self):
        assert_that(is_passing_hashtag_filter('#news', {'text': 'Post with #other'}), is_(False))

    def test_multiple_hashtags_match(self):
        assert_that(is_passing_hashtag_filter('#news, #update', {'text': 'Post with #update'}), is_(True))


class TestDisableChannel:
    @patch('vk_channelify.repost_worker.metrics')
    def test_disable_channel_success(self, mock_metrics):
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup')
        mock_db = Mock()
        mock_bot = Mock()

        disable_channel(mock_channel, mock_db, mock_bot)

        mock_db.add.assert_called_once()
        mock_db.delete.assert_called_once_with(mock_channel)
        mock_db.commit.assert_called_once()

    @patch('vk_channelify.repost_worker.metrics')
    def test_disable_channel_rollback_on_error(self, mock_metrics):
        mock_channel = Mock(channel_id='-100123456', vk_group_id='testgroup')
        mock_db = Mock()
        mock_db.commit.side_effect = Exception('DB Error')

        with pytest.raises(Exception):
            disable_channel(mock_channel, mock_db, Mock())

        mock_db.rollback.assert_called_once()
