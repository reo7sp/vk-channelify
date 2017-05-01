from functools import partial

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CommandHandler, Updater, ConversationHandler, Filters, MessageHandler, RegexHandler

from . import models


def worker(telegram_token, db):
    user_group_links = dict()

    updater = Updater(telegram_token)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler("new", new)],
        states={
            VK_GROUP_LINK: [RegexHandler('^https://vk.com/',
                                         partial(new_in_state_vk_group_link, user_group_links=user_group_links))],
            TG_CHANNEL_ACCESS: [RegexHandler('^I\'ve have done it$', new_in_state_tg_channel_access)],
            TG_CHANNEL_LINK: [MessageHandler(Filters.forwarded, partial(new_in_state_tg_channel_link, db=db, user_group_links=user_group_links))]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    ))

    updater.start_polling()
    return updater


VK_GROUP_LINK, TG_CHANNEL_ACCESS, TG_CHANNEL_LINK = range(3)


def start(bot, update):
    update.message.reply_text('Use /new to setup a new channel '
                              'which will be populated by posts in your specified VK group')


def new(bot, update):
    update.message.reply_text('Enter link to the VK group')
    return VK_GROUP_LINK


def new_in_state_vk_group_link(bot, update, user_group_links):
    vk_url = update.message.text
    vk_domain = vk_url.split('/')[-1]
    user_group_links[update.message.from_user.id] = vk_domain

    update.message.reply_text('Great! So now:')
    update.message.reply_text('1. Create a new channel. You can reuse existing channel')
    reply_keyboard = [['I\'ve have done it']]
    update.message.reply_text('2. Add this bot (@vk_channelify_bot) to administrators of the channel',
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return TG_CHANNEL_ACCESS


def new_in_state_tg_channel_access(bot, update):
    update.message.reply_text('Okay. Forward any message from your channel so I will remember it',
                              reply_markup=ReplyKeyboardRemove())
    return TG_CHANNEL_LINK


def new_in_state_tg_channel_link(bot, update, db, user_group_links):
    user_id = update.message.from_user.id
    channel_id = update.message.forward_from_chat.id
    vk_group_id = user_group_links[user_id]

    channel = models.Channel(channel_id=channel_id, vk_group_id=vk_group_id, owner_id=user_id)
    db.add(channel)
    db.commit()

    del user_group_links[user_id]

    bot.send_message(channel_id, 'This channel is powered by @vk_channelify_bot')

    update.message.reply_text('Done!')
    update.message.reply_text('Bot will check your VK group every 15 minutes')
    update.message.reply_text('Use /new to setup a new channel')
    return ConversationHandler.END


def cancel(bot, update, user_group_links):
    if update.message.from_user.id in user_group_links:
        del user_group_links[update.message.from_user.id]

    update.message.reply_text('Fine')
    update.message.reply_text('Use /new to setup a new channel')
    return ConversationHandler.END
