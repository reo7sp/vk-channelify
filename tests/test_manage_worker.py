import pytest
from unittest.mock import Mock, patch
from hamcrest import assert_that, equal_to, is_

from vk_channelify.manage_worker import (
    start,
    new,
    new_in_state_asked_vk_group_link,
    new_in_state_asked_channel_access,
    new_in_state_asked_channel_message,
    cancel_new,
    del_state,
    ASKED_VK_GROUP_LINK_IN_NEW,
    ASKED_CHANNEL_ACCESS_IN_NEW,
    ASKED_CHANNEL_MESSAGE_IN_NEW
)
from telegram.ext import ConversationHandler


class TestDelState:
    def test_deletes_user_state_if_exists(self):
        update = Mock()
        update.message.from_user.id = 12345
        users_state = {12345: {'data': 'value'}}

        del_state(update, users_state)

        assert_that(12345 not in users_state, is_(True))

    def test_does_nothing_if_state_not_exists(self):
        update = Mock()
        update.message.from_user.id = 12345
        users_state = {}

        del_state(update, users_state)

        assert_that(12345 not in users_state, is_(True))


class TestStart:
    def test_start_sends_welcome_message(self):
        bot = Mock()
        update = Mock()

        start(bot, update)

        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args[0][0]
        assert_that('/new' in call_args, is_(True))


class TestNew:
    @patch('vk_channelify.manage_worker.metrics')
    def test_new_starts_conversation(self, mock_metrics):
        bot = Mock()
        update = Mock()

        result = new(bot, update)

        assert_that(result, equal_to(ASKED_VK_GROUP_LINK_IN_NEW))
        update.message.reply_text.assert_called_once()


class TestNewInStateAskedVkGroupLink:
    def test_saves_vk_domain_and_asks_for_channel_access(self):
        bot = Mock()
        update = Mock()
        update.message.text = 'https://vk.ru/mygroup'
        update.message.from_user.id = 12345
        users_state = {}

        result = new_in_state_asked_vk_group_link(bot, update, users_state=users_state)

        assert_that(result, equal_to(ASKED_CHANNEL_ACCESS_IN_NEW))
        assert_that(users_state[12345]['vk_domain'], equal_to('mygroup'))
        assert_that(update.message.reply_text.call_count, equal_to(3))


class TestNewInStateAskedChannelAccess:
    def test_asks_for_channel_message(self):
        bot = Mock()
        update = Mock()

        result = new_in_state_asked_channel_access(bot, update)

        assert_that(result, equal_to(ASKED_CHANNEL_MESSAGE_IN_NEW))
        update.message.reply_text.assert_called_once()


class TestNewInStateAskedChannelMessage:
    @patch('vk_channelify.manage_worker.metrics')
    @patch('vk_channelify.manage_worker.Channel')
    @patch('vk_channelify.manage_worker.DisabledChannel')
    def test_creates_channel_successfully(self, mock_disabled_channel, mock_channel, mock_metrics):
        bot = Mock()
        update = Mock()
        update.message.from_user.id = 12345
        update.message.from_user.username = 'testuser'
        update.message.forward_from_chat.id = -100123456
        users_state = {12345: {'vk_domain': 'mygroup'}}
        db = Mock()
        db_session_maker = Mock(return_value=db)

        result = new_in_state_asked_channel_message(bot, update, db_session_maker=db_session_maker, users_state=users_state)

        assert_that(result, equal_to(ConversationHandler.END))
        db.add.assert_called_once()
        db.commit.assert_called_once()
        bot.send_message.assert_called_once()

    @patch('vk_channelify.manage_worker.metrics')
    @patch('vk_channelify.manage_worker.Channel')
    def test_rolls_back_on_error(self, mock_channel, mock_metrics):
        bot = Mock()
        update = Mock()
        update.message.from_user.id = 12345
        update.message.from_user.username = 'testuser'
        update.message.forward_from_chat.id = -100123456
        users_state = {12345: {'vk_domain': 'mygroup'}}
        db = Mock()
        db.commit.side_effect = Exception('DB Error')
        db_session_maker = Mock(return_value=db)

        new_in_state_asked_channel_message(bot, update, db_session_maker=db_session_maker, users_state=users_state)

        db.rollback.assert_called_once()
        update.message.reply_text.assert_called()


class TestCancelNew:
    @patch('vk_channelify.manage_worker.metrics')
    def test_cancel_ends_conversation(self, mock_metrics):
        bot = Mock()
        update = Mock()
        update.message.from_user.id = 12345
        users_state = {12345: {'vk_domain': 'mygroup'}}

        result = cancel_new(bot, update, users_state=users_state)

        assert_that(result, equal_to(ConversationHandler.END))
        assert_that(12345 not in users_state, is_(True))
