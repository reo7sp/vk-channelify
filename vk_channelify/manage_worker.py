import traceback
from functools import partial

import logging
import telegram
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CommandHandler, Updater, ConversationHandler, Filters, MessageHandler, RegexHandler

from . import models
from .models import Channel, DisabledChannel

logger = logging.getLogger(__name__)

ASKED_VK_GROUP_LINK_IN_NEW, ASKED_CHANNEL_ACCESS_IN_NEW, ASKED_CHANNEL_MESSAGE_IN_NEW, \
ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG, ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG, \
ASKED_CHANNEL_ID_IN_RECOVER = list(range(6))


def run_worker(telegram_token, db, use_webhook, webhook_domain='', webhook_port=''):
    users_state = dict()

    updater = Updater(telegram_token)

    dp = updater.dispatcher
    dp.add_error_handler(on_error)
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler('new', new)],
        states={
            ASKED_VK_GROUP_LINK_IN_NEW: [
                RegexHandler('^https://vk.com/', partial(new_in_state_asked_vk_group_link, users_state=users_state))
            ],
            ASKED_CHANNEL_ACCESS_IN_NEW: [
                RegexHandler('^Я сделал$', new_in_state_asked_channel_access)
            ],
            ASKED_CHANNEL_MESSAGE_IN_NEW: [
                MessageHandler(Filters.forwarded, partial(new_in_state_asked_channel_message, db=db, users_state=users_state))
            ]
        },
        allow_reentry=True,
        fallbacks=[CommandHandler('cancel', partial(cancel_new, users_state=users_state))]
    ))
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler('filter_by_hashtag', partial(filter_by_hashtag, db=db))],
        states={
            ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG: [
                MessageHandler(Filters.text, partial(filter_by_hashtag_in_state_asked_channel_id, db=db, users_state=users_state))
            ],
            ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG: [
                MessageHandler(Filters.text, partial(filter_by_hashtag_in_state_asked_hashtags, db=db, users_state=users_state))
            ]
        },
        allow_reentry=True,
        fallbacks=[CommandHandler('cancel', partial(cancel_filter_by_hashtag, users_state=users_state))]
    ))
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler('recover', partial(recover, db=db, users_state=users_state))],
        states={
            ASKED_CHANNEL_ID_IN_RECOVER: [
                MessageHandler(Filters.text, partial(recover_in_state_asked_channel_id, db=db, users_state=users_state))
            ]
        },
        allow_reentry=True,
        fallbacks=[CommandHandler('cancel', cancel_recover)]
    ))

    if use_webhook:
        logger.debug('Starting webhook at {}:{}'.format(webhook_domain, webhook_port))
        updater.start_webhook(webhook_domain, webhook_port, telegram_token)
    else:
        logger.debug('Starting long poll')
        updater.start_polling()

    return updater


def del_state(update, users_state):
    if update.message.from_user.id in users_state:
        del users_state[update.message.from_user.id]


def on_error(bot, update, error):
    logger.error('Update "{}" caused error "{}"'.format(update, error))
    traceback.print_exc()
    if update is not None:
        update.message.reply_text('Внутренняя ошибка')
        update.message.reply_text('{}: {}'.format(type(error).__name__, str(error)))
        update.message.reply_text('Сообщите @reo7sp')


def catch_exceptions(func):
    def wrapper(bot, update, *args, **kwargs):
        try:
            return func(bot, update, *args, **kwargs)
        except Exception as e:
            on_error(bot, update, e)

    return wrapper


@catch_exceptions
def start(bot, update):
    update.message.reply_text('Команда /new настроит новый канал. В канал будут пересылаться посты из группы ВК')
    update.message.reply_text('По вопросам пишите @reo7sp')


@catch_exceptions
def new(bot, update):
    update.message.reply_text('Отправьте ссылку на группу ВК')
    return ASKED_VK_GROUP_LINK_IN_NEW


@catch_exceptions
def new_in_state_asked_vk_group_link(bot, update, users_state):
    vk_url = update.message.text
    vk_domain = vk_url.split('/')[-1]
    users_state[update.message.from_user.id] = dict()
    users_state[update.message.from_user.id]['vk_domain'] = vk_domain

    update.message.reply_text('Отлично! Теперь:')
    update.message.reply_text('1. Создайте новый канал. Можно использовать существующий')
    keyboard = [['Я сделал']]
    update.message.reply_text('2. Добавьте этого бота (@vk_channelify_bot) в администраторы канала',
                              reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ASKED_CHANNEL_ACCESS_IN_NEW


@catch_exceptions
def new_in_state_asked_channel_access(bot, update):
    update.message.reply_text('Хорошо. Перешлите любое сообщение из канала',
                              reply_markup=ReplyKeyboardRemove())
    return ASKED_CHANNEL_MESSAGE_IN_NEW


@catch_exceptions
def new_in_state_asked_channel_message(bot, update, db, users_state):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    channel_id = update.message.forward_from_chat.id
    vk_group_id = users_state[user_id]['vk_domain']

    channel = Channel(channel_id=channel_id, vk_group_id=vk_group_id, owner_id=user_id, owner_username=username)
    db.add(channel)
    db.commit()

    try:
        db.query(DisabledChannel).filter(DisabledChannel.channel_id == channel_id).delete()
    except:
        logger.warning('Cannot delete disabled channel of {}'.format(channel_id))
        traceback.print_exc()

    del users_state[user_id]

    bot.send_message(channel_id, 'Канал работает с помощью @vk_channelify_bot')

    update.message.reply_text('Готово!')
    update.message.reply_text('Бот будет проверять группу каждые 15 минут')
    update.message.reply_text('Настроить фильтр по хештегам можно командой /filter_by_hashtag')
    update.message.reply_text('Команда /new настроит новый канал')
    del_state(update, users_state)
    return ConversationHandler.END


@catch_exceptions
def cancel_new(bot, update, users_state):
    update.message.reply_text('Ладно', reply_markup=ReplyKeyboardRemove())
    update.message.reply_text('Команда /new настроит новый канал')
    del_state(update, users_state)
    return ConversationHandler.END


@catch_exceptions
def filter_by_hashtag(bot, update, db, users_state):
    user_id = update.message.from_user.id

    users_state[user_id] = dict()
    users_state[user_id]['channels'] = dict()
    keyboard = []
    keyboard_row = []
    for channel in db.query(Channel).filter(Channel.owner_id == str(user_id)).order_by(Channel.created_at.desc()):
        try:
            channel_chat = bot.get_chat(chat_id=channel.channel_id)
            users_state[user_id]['channels'][channel_chat.title] = channel.channel_id
            keyboard_row.append(channel_chat.title)
            if len(keyboard_row) == 2:
                keyboard.append(keyboard_row)
                keyboard_row = []
        except telegram.TelegramError:
            logger.warning('filter_by_hashtag: cannot get title of channel {}'.format(channel.channel_id))
            traceback.print_exc()
    if len(keyboard_row) != 0:
        keyboard.append(keyboard_row)

    update.message.reply_text('Выберите канал', reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))

    return ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG


@catch_exceptions
def filter_by_hashtag_in_state_asked_channel_id(bot, update, db, users_state):
    user_id = update.message.from_user.id
    channel_title = update.message.text
    channel_id = users_state[user_id]['channels'][channel_title]
    channel = db.query(Channel).get(channel_id)
    users_state[user_id]['channel'] = channel

    if channel.hashtag_filter is not None:
        update.message.reply_text('Текущий фильтр по хештегам:')
        update.message.reply_text(channel.hashtag_filter)
    update.message.reply_text('Напишите новые хештеги (разделяйте запятой):')

    return ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG


@catch_exceptions
def filter_by_hashtag_in_state_asked_hashtags(bot, update, db, users_state):
    user_id = update.message.from_user.id
    channel = users_state[user_id]['channel']

    channel.hashtag_filter = ','.join(h.strip() for h in update.message.text.split(','))
    db.commit()

    update.message.reply_text('Сохранено!')
    del_state(update, users_state)
    return ConversationHandler.END


@catch_exceptions
def cancel_filter_by_hashtag(bot, update, users_state):
    update.message.reply_text('Ладно', reply_markup=ReplyKeyboardRemove())
    update.message.reply_text('Настроить фильтр по хештегам можно командой /filter_by_hashtag')
    update.message.reply_text('Команда /new настроит новый канал')
    del_state(update, users_state)
    return ConversationHandler.END


@catch_exceptions
def recover(bot, update, db, users_state):
    user_id = update.message.from_user.id

    users_state[user_id] = dict()
    users_state[user_id]['channels'] = dict()
    keyboard = []
    keyboard_row = []
    for channel in db.query(DisabledChannel).filter(DisabledChannel.owner_id == str(user_id)).order_by(DisabledChannel.created_at.desc()):
        title = '{} ({})'.format(channel.vk_group_id, channel.channel_id)
        users_state[user_id]['channels'][title] = channel.channel_id
        keyboard_row.append(title)
        if len(keyboard_row) == 2:
            keyboard.append(keyboard_row)
            keyboard_row = []
    if len(keyboard_row) != 0:
        keyboard.append(keyboard_row)

    if len(keyboard) == 0:
        update.message.reply_text('Нет каналов, которые можно восстановить')
        return ConversationHandler.END
    else:
        update.message.reply_text('Выберите канал', reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
        return ASKED_CHANNEL_ID_IN_RECOVER


@catch_exceptions
def recover_in_state_asked_channel_id(bot, update, db, users_state):
    user_id = update.message.from_user.id
    channel_title = update.message.text
    channel_id = users_state[user_id]['channels'][channel_title]
    disabled_channel = db.query(DisabledChannel).filter(DisabledChannel.channel_id == channel_id).one()

    db.add(
        Channel(
            channel_id=disabled_channel.channel_id,
            vk_group_id=disabled_channel.vk_group_id,
            last_vk_post_id=disabled_channel.last_vk_post_id,
            owner_id=disabled_channel.owner_id,
            owner_username=disabled_channel.owner_username,
            hashtag_filter=disabled_channel.hashtag_filter
        )
    )
    db.delete(disabled_channel)
    db.commit()

    update.message.reply_text('Готово!')
    update.message.reply_text('Бот будет проверять группу каждые 15 минут')
    update.message.reply_text('Настроить фильтр по хештегам можно командой /filter_by_hashtag')
    update.message.reply_text('Команда /new настроит новый канал')

    return ConversationHandler.END


@catch_exceptions
def cancel_recover(bot, update):
    update.message.reply_text('Ладно', reply_markup=ReplyKeyboardRemove())
    update.message.reply_text('Команда /new настроит новый канал')
    return ConversationHandler.END
