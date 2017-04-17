from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import CommandHandler, Updater, ConversationHandler, Filters, MessageHandler, RegexHandler

VK_GROUP_LINK, TG_CHANNEL_ACCESS, TG_CHANNEL_LINK = range(3)


def start(bot, update):
    update.message.reply_text('Use /new to setup a new channel'
                              'which will be populated by posts in your specified VK group')


def new(bot, update):
    update.message.reply_text('Enter link to the VK group')
    return VK_GROUP_LINK


def new_in_state_vk_group_link(bot, update):
    # TODO: save link

    reply_keyboard = [['I\'ve have done it']]
    update.message.reply_text('Great! So now:')
    update.message.reply_text('1. Create a new channel. You can reuse existing channel')
    update.message.reply_text('2. Add this bot to administrators of the channel',
                              reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return TG_CHANNEL_ACCESS


def new_in_state_tg_channel_access(bot, update):
    update.message.reply_text('Okay. Forward any message from your channel so I will remember it',
                              reply_markup=ReplyKeyboardRemove())
    return TG_CHANNEL_LINK


def new_in_state_tg_channel_link(bot, update):
    # TODO: save_link

    update.message.reply_text('Done!')
    return ConversationHandler.END


def cancel(bot, update):
    # TODO: cleanup

    update.message.reply_text('Fine')
    return ConversationHandler.END


def worker(telegram_token):
    updater = Updater(telegram_token)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(ConversationHandler(
        entry_points=[CommandHandler("new", new)],
        states={
            VK_GROUP_LINK: [RegexHandler('^https://vk.com/', new_in_state_vk_group_link)],
            TG_CHANNEL_ACCESS: [RegexHandler('^I\'ve have done it$', new_in_state_tg_channel_access)],
            TG_CHANNEL_LINK: [MessageHandler(Filters.forwarded, new_in_state_tg_channel_link)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    ))

    updater.start_polling()
    updater.idle()

