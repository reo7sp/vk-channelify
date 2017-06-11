import traceback
from functools import partial

import telegram
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CommandHandler, Updater, ConversationHandler, Filters, MessageHandler, RegexHandler

from vk_channelify.models import Channel
from . import models


def run_worker(telegram_token, db):
    users_state = dict()

    updater = Updater(telegram_token)

    dp = updater.dispatcher
    dp.add_error_handler(on_error)
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler('new', new)],
        states={
            ASKED_VK_GROUP_LINK_IN_NEW:
                [RegexHandler('^https://vk.com/', partial(new_in_state_asked_vk_group_link, users_state=users_state))],
            ASKED_CHANNEL_ACCESS_IN_NEW:
                [RegexHandler('^I\'ve have done it$', new_in_state_asked_channel_access)],
            ASKED_CHANNEL_MESSAGE_IN_NEW:
                [MessageHandler(Filters.forwarded, partial(new_in_state_asked_channel_message, db=db, users_state=users_state))]
        },
        allow_reentry=True,
        fallbacks=[CommandHandler('cancel', partial(cancel_new, users_state=users_state))]
    ))
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler('filter_by_hashtag', partial(filter_by_hashtag, db=db))],
        states={
            ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG: [
                MessageHandler(Filters.text, partial(filter_by_hashtag_in_state_asked_channel_id, db=db, users_state=users_state))],
            ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG: [
                MessageHandler(Filters.text, partial(filter_by_hashtag_in_state_asked_hashtags, db=db, users_state=users_state))]
        },
        allow_reentry=True,
        fallbacks=[CommandHandler('cancel', partial(cancel_filter_by_hashtag, users_state=users_state))]
    ))

    updater.start_polling()
    return updater


ASKED_VK_GROUP_LINK_IN_NEW, ASKED_CHANNEL_ACCESS_IN_NEW, ASKED_CHANNEL_MESSAGE_IN_NEW, \
ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG, ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG = range(5)


def del_state(update, users_state):
    if update.message.from_user.id in users_state:
        del users_state[update.message.from_user.id]


def on_error(bot, update, error):
    update.message.reply_text('Sorry, got an internal server error!')
    update.message.reply_text(str(error))
    update.message.reply_text('Send the message above to @reo7sp. Don\'t forget to say the time then the error occured')
    print('ERROR IN manage_worker.py: {}'.format(error))


def start(bot, update):
    update.message.reply_text('Use /new to setup a new channel '
                              'which will be populated by posts in your specified VK group')
    update.message.reply_text('Bot author: @reo7sp')


def new(bot, update):
    update.message.reply_text('Enter link to the VK group', reply_markup=ReplyKeyboardRemove())
    return ASKED_VK_GROUP_LINK_IN_NEW


def new_in_state_asked_vk_group_link(bot, update, users_state):
    vk_url = update.message.text
    vk_domain = vk_url.split('/')[-1]
    users_state[update.message.from_user.id] = vk_domain

    update.message.reply_text('Great! So now:')
    update.message.reply_text('1. Create a new channel. You can reuse existing channel')
    keyboard = [['I\'ve have done it']]
    update.message.reply_text('2. Add this bot (@vk_channelify_bot) to administrators of the channel',
                              reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ASKED_CHANNEL_ACCESS_IN_NEW


def new_in_state_asked_channel_access(bot, update):
    update.message.reply_text('Okay. Forward any message from your channel so I will remember it',
                              reply_markup=ReplyKeyboardRemove())
    return ASKED_CHANNEL_MESSAGE_IN_NEW


def new_in_state_asked_channel_message(bot, update, db, users_state):
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    channel_id = update.message.forward_from_chat.id
    vk_group_id = users_state[user_id]

    channel = models.Channel(channel_id=channel_id, vk_group_id=vk_group_id, owner_id=user_id, owner_username=username)
    db.add(channel)
    db.commit()

    del users_state[user_id]

    bot.send_message(channel_id, 'This channel is powered by @vk_channelify_bot')

    update.message.reply_text('Done!')
    update.message.reply_text('Bot will check your VK group every 15 minutes')
    update.message.reply_text('Apply hashtag filtering via /filter_by_hashtag command')
    update.message.reply_text('Use /new to setup a new channel')
    del_state(update, users_state)
    return ConversationHandler.END


def cancel_new(bot, update, users_state):
    update.message.reply_text('Fine', reply_markup=ReplyKeyboardRemove())
    update.message.reply_text('Use /new to setup a new channel')
    del_state(update, users_state)
    return ConversationHandler.END


def filter_by_hashtag(bot, update, db):
    user_id = update.message.from_user.id

    keyboard = []
    keyboard_row = []
    for channel in db.query(Channel).filter(Channel.owner_id == str(user_id)):
        try:
            channel_chat = bot.get_chat(chat_id=channel.channel_id)
            keyboard_row.append(channel_chat.title)
            if len(keyboard_row) == 2:
                keyboard.append(keyboard_row)
                keyboard_row = []
        except telegram.TelegramError:
            pass
    if len(keyboard_row) != 0:
        keyboard.append(keyboard_row)

    update.message.reply_text('Choose channel', reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))

    return ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG


def filter_by_hashtag_in_state_asked_channel_id(bot, update, db, users_state):
    user_id = update.message.from_user.id
    channel_id = update.message.text
    channel = db.query(Channel).get(channel_id)
    users_state[user_id] = channel

    if channel.hashtag_filter is not None:
        update.message.reply_text('Current hashtag filter:')
        update.message.reply_text(channel.hashtag_filter)
    update.message.reply_text('Write new hashtags (separate with comma):')

    return ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG


def filter_by_hashtag_in_state_asked_hashtags(bot, update, db, users_state):
    user_id = update.message.from_user.id
    channel = users_state[user_id]

    channel.hashtag_filter = ','.join(h.strip() for h in update.message.text.split(','))
    db.commit()

    update.message.reply_text('Saved!')
    del_state(update, users_state)
    return ConversationHandler.END


def cancel_filter_by_hashtag(bot, update, users_state):
    update.message.reply_text('Fine', reply_markup=ReplyKeyboardRemove())
    update.message.reply_text('Apply hashtag filtering via /filter_by_hashtag command')
    update.message.reply_text('Use /new to setup a new channel')
    del_state(update, users_state)
    return ConversationHandler.END
