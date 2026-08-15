import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
import telegram
from hamcrest import assert_that, equal_to, is_
from telegram.ext import ConversationHandler

from vk_channelify.manage_worker import (
    ASKED_CHANNEL_ACCESS_IN_NEW,
    ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG,
    ASKED_CHANNEL_ID_IN_RECOVER,
    ASKED_CHANNEL_MESSAGE_IN_NEW,
    ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG,
    ASKED_VK_GROUP_LINK_IN_NEW,
    cancel_filter_by_hashtag,
    cancel_new,
    cancel_recover,
    del_state,
    filter_by_hashtag,
    filter_by_hashtag_in_state_asked_channel_id,
    filter_by_hashtag_in_state_asked_hashtags,
    get_forwarded_chat_id,
    new,
    new_in_state_asked_channel_access,
    new_in_state_asked_channel_message,
    new_in_state_asked_vk_group_link,
    on_error,
    recover,
    recover_in_state_asked_channel_id,
    run_worker,
    start,
)


def make_forward_origin(origin_type: str) -> telegram.MessageOrigin:
    chat = telegram.Chat(
        id=-100123456,
        type=telegram.constants.ChatType.CHANNEL,
    )
    if origin_type == 'channel':
        return telegram.MessageOriginChannel(
            date=datetime.now(UTC),
            chat=chat,
            message_id=1,
        )
    return telegram.MessageOriginChat(
        date=datetime.now(UTC),
        sender_chat=chat,
    )


class TestRunWorker:
    @patch('vk_channelify.manage_worker.Application')
    def test_starts_polling(self, mock_application: Mock) -> None:
        application = mock_application.builder.return_value.token.return_value.build.return_value

        run_worker('token', Mock(), False)

        application.run_polling.assert_called_once_with()
        application.run_webhook.assert_not_called()

    @patch('vk_channelify.manage_worker.Application')
    def test_starts_webhook(self, mock_application: Mock) -> None:
        application = mock_application.builder.return_value.token.return_value.build.return_value

        run_worker('token', Mock(), True, 'bot.example.com', 8443)

        application.run_webhook.assert_called_once_with(
            listen='0.0.0.0',
            port=8443,
            url_path='token',
            webhook_url='https://bot.example.com/token',
        )
        application.run_polling.assert_not_called()


class TestGetForwardedChatId:
    def test_gets_channel_origin_chat_id(self) -> None:
        message = Mock(forward_origin=make_forward_origin('channel'))

        assert_that(get_forwarded_chat_id(message), equal_to(-100123456))

    def test_gets_chat_origin_sender_chat_id(self) -> None:
        message = Mock(forward_origin=make_forward_origin('chat'))

        assert_that(get_forwarded_chat_id(message), equal_to(-100123456))

    def test_rejects_user_origin(self) -> None:
        message = Mock(
            forward_origin=telegram.MessageOriginUser(
                date=datetime.now(UTC),
                sender_user=telegram.User(id=1, first_name='Test', is_bot=False),
            )
        )

        with pytest.raises(ValueError):
            get_forwarded_chat_id(message)


class TestDelState:
    def test_deletes_user_state_if_exists(self) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        users_state = {12345: {'data': 'value'}}

        del_state(update, users_state)

        assert_that(12345 not in users_state, is_(True))

    def test_does_nothing_if_state_not_exists(self) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        users_state = {}

        del_state(update, users_state)

        assert_that(12345 not in users_state, is_(True))


class TestOnError:
    @patch('vk_channelify.manage_worker.metrics')
    def test_records_polling_error(self, mock_metrics: Mock) -> None:
        error = Exception('Network is unreachable')
        context = Mock(error=error)

        with patch('vk_channelify.manage_worker.logger') as mock_logger:
            asyncio.run(on_error(None, context))

        mock_metrics.telegram_api_requests_total.labels.assert_called_once_with(
            method='get_updates', status='error', channel_id='', vk_group_id=''
        )
        mock_metrics.telegram_api_requests_total.labels.return_value.inc.assert_called_once_with()
        mock_logger.error.assert_called_once_with(
            'Telegram update failed',
            error='Network is unreachable',
            update='None',
            exc_info=error,
        )

    @patch('vk_channelify.manage_worker.metrics')
    def test_replies_to_effective_message(self, mock_metrics: Mock) -> None:
        update = Mock(spec=telegram.Update)
        update.effective_message = Mock(reply_text=AsyncMock())
        context = Mock(error=Exception('Failed'))

        asyncio.run(on_error(update, context))

        assert_that(update.effective_message.reply_text.call_count, equal_to(2))


class TestStart:
    def test_start_sends_welcome_message(self) -> None:
        update = Mock()
        context = Mock()
        update.message.reply_text = AsyncMock()

        asyncio.run(start(update, context))

        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args[0][0]
        assert_that('/new' in call_args, is_(True))


class TestNew:
    @patch('vk_channelify.manage_worker.metrics')
    def test_new_starts_conversation(self, mock_metrics: Mock) -> None:
        update = Mock()
        context = Mock()
        update.message.reply_text = AsyncMock()

        result = asyncio.run(new(update, context))

        assert_that(result, equal_to(ASKED_VK_GROUP_LINK_IN_NEW))
        update.message.reply_text.assert_called_once()


class TestNewInStateAskedVkGroupLink:
    def test_saves_vk_domain_and_asks_for_channel_access(self) -> None:
        update = Mock()
        context = Mock()
        update.message.text = 'https://vk.ru/mygroup'
        update.message.from_user.id = 12345
        update.message.reply_text = AsyncMock()
        users_state = {}

        result = asyncio.run(new_in_state_asked_vk_group_link(update, context, users_state=users_state))

        assert_that(result, equal_to(ASKED_CHANNEL_ACCESS_IN_NEW))
        assert_that(users_state[12345]['vk_domain'], equal_to('mygroup'))
        assert_that(update.message.reply_text.call_count, equal_to(3))


class TestNewInStateAskedChannelAccess:
    def test_asks_for_channel_message(self) -> None:
        update = Mock()
        context = Mock()
        update.message.reply_text = AsyncMock()

        result = asyncio.run(new_in_state_asked_channel_access(update, context))

        assert_that(result, equal_to(ASKED_CHANNEL_MESSAGE_IN_NEW))
        update.message.reply_text.assert_called_once()


class TestNewInStateAskedChannelMessage:
    @patch('vk_channelify.manage_worker.metrics')
    @patch('vk_channelify.manage_worker.Channel')
    @patch('vk_channelify.manage_worker.DisabledChannel')
    def test_creates_channel_successfully(
        self,
        mock_disabled_channel: Mock,
        mock_channel: Mock,
        mock_metrics: Mock,
    ) -> None:
        update = Mock()
        context = Mock()
        update.message.from_user.id = 12345
        update.message.from_user.username = 'testuser'
        update.message.forward_origin = telegram.MessageOriginChannel(
            date=datetime.now(UTC),
            chat=telegram.Chat(id=-100123456, type=telegram.constants.ChatType.CHANNEL),
            message_id=1,
        )
        update.message.reply_text = AsyncMock()
        context.bot.send_message = AsyncMock()
        users_state = {12345: {'vk_domain': 'mygroup'}}
        db = Mock()
        db_session_maker = Mock(return_value=db)

        result = asyncio.run(
            new_in_state_asked_channel_message(
                update, context, db_session_maker=db_session_maker, users_state=users_state
            )
        )

        assert_that(result, equal_to(ConversationHandler.END))
        db.add.assert_called_once()
        db.commit.assert_called_once()
        context.bot.send_message.assert_called_once()

    @patch('vk_channelify.manage_worker.metrics')
    @patch('vk_channelify.manage_worker.Channel')
    def test_rolls_back_on_error(self, mock_channel: Mock, mock_metrics: Mock) -> None:
        update = Mock()
        context = Mock()
        update.message.from_user.id = 12345
        update.message.from_user.username = 'testuser'
        update.message.forward_origin = telegram.MessageOriginChannel(
            date=datetime.now(UTC),
            chat=telegram.Chat(id=-100123456, type=telegram.constants.ChatType.CHANNEL),
            message_id=1,
        )
        update.message.reply_text = AsyncMock()
        users_state = {12345: {'vk_domain': 'mygroup'}}
        db = Mock()
        db.commit.side_effect = RuntimeError('DB Error')
        db_session_maker = Mock(return_value=db)

        with pytest.raises(RuntimeError):
            asyncio.run(
                new_in_state_asked_channel_message(
                    update, context, db_session_maker=db_session_maker, users_state=users_state
                )
            )

        db.rollback.assert_called_once()
        mock_metrics.telegram_conversations_total.labels.assert_called_with(type='new', status='failed')


class TestCancelNew:
    @patch('vk_channelify.manage_worker.metrics')
    def test_cancel_ends_conversation(self, mock_metrics: Mock) -> None:
        update = Mock()
        context = Mock()
        update.message.from_user.id = 12345
        update.message.reply_text = AsyncMock()
        users_state = {12345: {'vk_domain': 'mygroup'}}

        result = asyncio.run(cancel_new(update, context, users_state=users_state))

        assert_that(result, equal_to(ConversationHandler.END))
        assert_that(12345 not in users_state, is_(True))


class TestFilterByHashtag:
    @patch('vk_channelify.manage_worker.metrics')
    def test_lists_owned_channels(self, mock_metrics: Mock) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.reply_text = AsyncMock()
        context = Mock()
        context.bot.get_chat = AsyncMock(return_value=Mock(title='Test channel'))
        channel = Mock(channel_id='-1001')
        db = Mock()
        db.scalars.return_value = [channel]
        users_state = {}

        result = asyncio.run(
            filter_by_hashtag(
                update,
                context,
                db_session_maker=Mock(return_value=db),
                users_state=users_state,
            )
        )

        assert_that(result, equal_to(ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG))
        assert_that(users_state[12345]['channels']['Test channel'], equal_to('-1001'))
        db.close.assert_called_once_with()

    def test_rejects_missing_selected_channel(self) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.text = 'Missing channel'
        db = Mock()
        db.get.return_value = None

        with pytest.raises(ValueError, match='does not exist'):
            asyncio.run(
                filter_by_hashtag_in_state_asked_channel_id(
                    update,
                    Mock(),
                    db_session_maker=Mock(return_value=db),
                    users_state={12345: {'channels': {'Missing channel': '-1001'}}},
                )
            )

        db.close.assert_called_once_with()

    def test_selects_channel_and_shows_current_filter(self) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.text = 'Test channel'
        update.message.reply_text = AsyncMock()
        context = Mock()
        channel = Mock(hashtag_filter='#books')
        db = Mock()
        db.get.return_value = channel
        users_state = {12345: {'channels': {'Test channel': '-1001'}}}

        result = asyncio.run(
            filter_by_hashtag_in_state_asked_channel_id(
                update,
                context,
                db_session_maker=Mock(return_value=db),
                users_state=users_state,
            )
        )

        assert_that(result, equal_to(ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG))
        assert_that(users_state[12345]['channel_id'], equal_to('-1001'))
        assert_that(update.message.reply_text.call_count, equal_to(3))
        db.close.assert_called_once_with()

    @patch('vk_channelify.manage_worker.metrics')
    def test_saves_filter(self, mock_metrics: Mock) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.text = '#books, #news'
        update.message.reply_text = AsyncMock()
        context = Mock()
        channel = Mock()
        db = Mock()
        db.get.return_value = channel
        users_state = {12345: {'channel_id': '-1001'}}

        result = asyncio.run(
            filter_by_hashtag_in_state_asked_hashtags(
                update,
                context,
                db_session_maker=Mock(return_value=db),
                users_state=users_state,
            )
        )

        assert_that(result, equal_to(ConversationHandler.END))
        assert_that(channel.hashtag_filter, equal_to('#books,#news'))
        assert_that(12345 not in users_state, is_(True))
        db.commit.assert_called_once_with()
        db.close.assert_called_once_with()

    @patch('vk_channelify.manage_worker.metrics')
    def test_rolls_back_filter_on_error(self, mock_metrics: Mock) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.text = '#books'
        context = Mock()
        db = Mock()
        db.get.return_value = Mock()
        db.commit.side_effect = RuntimeError('DB Error')

        with pytest.raises(RuntimeError):
            asyncio.run(
                filter_by_hashtag_in_state_asked_hashtags(
                    update,
                    context,
                    db_session_maker=Mock(return_value=db),
                    users_state={12345: {'channel_id': '-1001'}},
                )
            )

        db.rollback.assert_called_once_with()
        db.close.assert_called_once_with()

    def test_rejects_missing_channel_when_saving_filter(self) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        db = Mock()
        db.get.return_value = None

        with pytest.raises(ValueError, match='does not exist'):
            asyncio.run(
                filter_by_hashtag_in_state_asked_hashtags(
                    update,
                    Mock(),
                    db_session_maker=Mock(return_value=db),
                    users_state={12345: {'channel_id': '-1001'}},
                )
            )

        db.close.assert_called_once_with()

    @patch('vk_channelify.manage_worker.metrics')
    def test_cancels_filter(self, mock_metrics: Mock) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.reply_text = AsyncMock()
        users_state = {12345: {'channel_id': '-1001'}}

        result = asyncio.run(
            cancel_filter_by_hashtag(
                update,
                Mock(),
                users_state=users_state,
            )
        )

        assert_that(result, equal_to(ConversationHandler.END))
        assert_that(12345 not in users_state, is_(True))


class TestRecover:
    @patch('vk_channelify.manage_worker.metrics')
    def test_returns_end_when_there_are_no_channels(self, mock_metrics: Mock) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.reply_text = AsyncMock()
        db = Mock()
        db.scalars.return_value = []
        users_state = {}

        result = asyncio.run(
            recover(
                update,
                Mock(),
                db_session_maker=Mock(return_value=db),
                users_state=users_state,
            )
        )

        assert_that(result, equal_to(ConversationHandler.END))
        assert_that(12345 not in users_state, is_(True))
        db.close.assert_called_once_with()

    @patch('vk_channelify.manage_worker.metrics')
    def test_lists_disabled_channels(self, mock_metrics: Mock) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.reply_text = AsyncMock()
        disabled_channel = Mock(vk_group_id='books', channel_id='-1001')
        db = Mock()
        db.scalars.return_value = [disabled_channel]
        users_state = {}

        result = asyncio.run(
            recover(
                update,
                Mock(),
                db_session_maker=Mock(return_value=db),
                users_state=users_state,
            )
        )

        title = 'books (-1001)'
        assert_that(result, equal_to(ASKED_CHANNEL_ID_IN_RECOVER))
        assert_that(users_state[12345]['channels'][title], equal_to('-1001'))
        db.close.assert_called_once_with()

    @patch('vk_channelify.manage_worker.metrics')
    def test_recovers_channel(self, mock_metrics: Mock) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.text = 'books (-1001)'
        update.message.reply_text = AsyncMock()
        disabled_channel = Mock(
            channel_id='-1001',
            vk_group_id='books',
            last_vk_post_id=42,
            owner_id='12345',
            owner_username='test',
            hashtag_filter='#books',
        )
        db = Mock()
        db.scalars.return_value.one.return_value = disabled_channel
        users_state = {12345: {'channels': {'books (-1001)': '-1001'}}}

        result = asyncio.run(
            recover_in_state_asked_channel_id(
                update,
                Mock(),
                db_session_maker=Mock(return_value=db),
                users_state=users_state,
            )
        )

        assert_that(result, equal_to(ConversationHandler.END))
        db.add.assert_called_once()
        db.delete.assert_called_once_with(disabled_channel)
        db.commit.assert_called_once_with()
        db.close.assert_called_once_with()
        assert_that(12345 not in users_state, is_(True))

    @patch('vk_channelify.manage_worker.metrics')
    def test_rolls_back_recover_on_error(self, mock_metrics: Mock) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.text = 'books (-1001)'
        disabled_channel = Mock(
            channel_id='-1001',
            vk_group_id='books',
            last_vk_post_id=42,
            owner_id='12345',
            owner_username='test',
            hashtag_filter=None,
        )
        db = Mock()
        db.scalars.return_value.one.return_value = disabled_channel
        db.commit.side_effect = RuntimeError('DB Error')

        with pytest.raises(RuntimeError):
            asyncio.run(
                recover_in_state_asked_channel_id(
                    update,
                    Mock(),
                    db_session_maker=Mock(return_value=db),
                    users_state={12345: {'channels': {'books (-1001)': '-1001'}}},
                )
            )

        db.rollback.assert_called_once_with()
        db.close.assert_called_once_with()

    @patch('vk_channelify.manage_worker.metrics')
    def test_cancels_recover(self, mock_metrics: Mock) -> None:
        update = Mock()
        update.message.from_user.id = 12345
        update.message.reply_text = AsyncMock()
        users_state = {12345: {'channels': {}}}

        result = asyncio.run(cancel_recover(update, Mock(), users_state=users_state))

        assert_that(result, equal_to(ConversationHandler.END))
        assert_that(12345 not in users_state, is_(True))
