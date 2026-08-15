import time
from collections.abc import Callable
from functools import partial, wraps
from typing import Any

import structlog
import telegram
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker
from telegram import Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from vk_channelify import metrics
from vk_channelify.models import Channel, DisabledChannel

logger = structlog.get_logger(__name__)

(
    ASKED_VK_GROUP_LINK_IN_NEW,
    ASKED_CHANNEL_ACCESS_IN_NEW,
    ASKED_CHANNEL_MESSAGE_IN_NEW,
    ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG,
    ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG,
    ASKED_CHANNEL_ID_IN_RECOVER,
) = range(6)


def run_worker(
    telegram_token: str,
    db_session_maker: sessionmaker[Session],
    use_webhook: bool,
    webhook_domain: str = '',
    webhook_port: int | str = '',
) -> None:
    users_state: dict[int, dict[str, Any]] = {}

    application = Application.builder().token(telegram_token).build()

    application.add_error_handler(on_error)
    application.add_handler(CommandHandler('start', start))
    application.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler('new', new)],
            states={
                ASKED_VK_GROUP_LINK_IN_NEW: [
                    MessageHandler(
                        filters.Regex('^https://vk.ru/'),
                        partial(new_in_state_asked_vk_group_link, users_state=users_state),
                    )
                ],
                ASKED_CHANNEL_ACCESS_IN_NEW: [
                    MessageHandler(filters.Regex('^Я сделал$'), new_in_state_asked_channel_access)
                ],
                ASKED_CHANNEL_MESSAGE_IN_NEW: [
                    MessageHandler(
                        filters.FORWARDED,
                        partial(
                            new_in_state_asked_channel_message,
                            db_session_maker=db_session_maker,
                            users_state=users_state,
                        ),
                    )
                ],
            },
            allow_reentry=True,
            fallbacks=[CommandHandler('cancel', partial(cancel_new, users_state=users_state))],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler(
                    'filter_by_hashtag',
                    partial(filter_by_hashtag, db_session_maker=db_session_maker, users_state=users_state),
                )
            ],
            states={
                ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG: [
                    MessageHandler(
                        filters.TEXT,
                        partial(
                            filter_by_hashtag_in_state_asked_channel_id,
                            db_session_maker=db_session_maker,
                            users_state=users_state,
                        ),
                    )
                ],
                ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG: [
                    MessageHandler(
                        filters.TEXT,
                        partial(
                            filter_by_hashtag_in_state_asked_hashtags,
                            db_session_maker=db_session_maker,
                            users_state=users_state,
                        ),
                    )
                ],
            },
            allow_reentry=True,
            fallbacks=[CommandHandler('cancel', partial(cancel_filter_by_hashtag, users_state=users_state))],
        )
    )
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler('recover', partial(recover, db_session_maker=db_session_maker, users_state=users_state))
            ],
            states={
                ASKED_CHANNEL_ID_IN_RECOVER: [
                    MessageHandler(
                        filters.TEXT,
                        partial(
                            recover_in_state_asked_channel_id,
                            db_session_maker=db_session_maker,
                            users_state=users_state,
                        ),
                    )
                ]
            },
            allow_reentry=True,
            fallbacks=[CommandHandler('cancel', partial(cancel_recover, users_state=users_state))],
        )
    )

    if use_webhook:
        logger.info('Starting webhook', domain=webhook_domain, port=webhook_port)
        application.run_webhook(
            listen='0.0.0.0',
            port=webhook_port,
            url_path=telegram_token,
            webhook_url=f'https://{webhook_domain}/{telegram_token}',
        )
    else:
        logger.info('Starting long poll')
        application.run_polling()


def del_state(update: Update, users_state: dict[int, dict[str, Any]]) -> None:
    if update.message.from_user.id in users_state:
        del users_state[update.message.from_user.id]


def get_forwarded_chat_id(message: Message) -> int:
    origin = message.forward_origin
    if isinstance(origin, telegram.MessageOriginChannel):
        return origin.chat.id
    if isinstance(origin, telegram.MessageOriginChat):
        return origin.sender_chat.id
    raise ValueError('The message was not forwarded from a chat or channel')


async def on_error(update: object | None, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(
        'Telegram update failed',
        error=str(context.error),
        update=repr(update),
        exc_info=context.error,
    )
    metrics.telegram_api_requests_total.labels(
        method='get_updates', status='error', channel_id='', vk_group_id=''
    ).inc()

    if isinstance(update, telegram.Update) and update.effective_message is not None:
        await update.effective_message.reply_text('Внутренняя ошибка')
        await update.effective_message.reply_text('Сообщите @olezhes')


def observe_metrics(command_name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
            metrics.telegram_commands_total.labels(command=command_name).inc()
            start_time = time.time()
            try:
                result = await func(update, context, *args, **kwargs)
                duration = time.time() - start_time
                metrics.telegram_command_duration_seconds.labels(command=command_name).observe(duration)
                return result
            except Exception:
                duration = time.time() - start_time
                metrics.telegram_command_duration_seconds.labels(command=command_name).observe(duration)
                raise

        return wrapper

    return decorator


def make_db_session(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(*args: Any, db_session_maker: sessionmaker[Session], **kwargs: Any) -> Any:
        db = db_session_maker()
        try:
            return await func(*args, **kwargs, db=db)
        finally:
            db.close()

    return wrapper


@observe_metrics('start')
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Команда /new настроит новый канал. В канал будут пересылаться посты из группы ВК')


@observe_metrics('new')
async def new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    metrics.telegram_conversations_total.labels(type='new', status='started').inc()

    await update.message.reply_text('Отправьте ссылку на группу ВК')

    return ASKED_VK_GROUP_LINK_IN_NEW


async def new_in_state_asked_vk_group_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    users_state: dict[int, dict[str, Any]],
) -> int:
    vk_url = update.message.text
    vk_domain = vk_url.split('/')[-1]
    users_state[update.message.from_user.id] = dict()
    users_state[update.message.from_user.id]['vk_domain'] = vk_domain

    await update.message.reply_text('Отлично! Теперь:')
    await update.message.reply_text('1. Создайте новый канал. Можно использовать существующий')
    keyboard = [['Я сделал']]
    await update.message.reply_text(
        '2. Добавьте этого бота (@vk_channelify_bot) в администраторы канала',
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True),
    )

    return ASKED_CHANNEL_ACCESS_IN_NEW


async def new_in_state_asked_channel_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Хорошо. Перешлите любое сообщение из канала', reply_markup=ReplyKeyboardRemove())

    return ASKED_CHANNEL_MESSAGE_IN_NEW


@make_db_session
async def new_in_state_asked_channel_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db: Session,
    users_state: dict[int, dict[str, Any]],
) -> int:
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    channel_id = str(get_forwarded_chat_id(update.message))
    vk_group_id = users_state[user_id]['vk_domain']

    try:
        channel = Channel(channel_id=channel_id, vk_group_id=vk_group_id, owner_id=user_id, owner_username=username)
        db.add(channel)
        db.commit()
        metrics.telegram_conversations_total.labels(type='new', status='completed').inc()
    except Exception:
        db.rollback()
        metrics.telegram_conversations_total.labels(type='new', status='failed').inc()
        raise

    try:
        db.execute(delete(DisabledChannel).where(DisabledChannel.channel_id == channel_id))
        db.commit()
    except Exception:
        logger.warning(
            'Failed to delete disabled channel',
            channel_id=channel_id,
            exc_info=True,
        )

    await context.bot.send_message(channel_id, 'Канал работает с помощью @vk_channelify_bot')

    await update.message.reply_text('Готово!')
    await update.message.reply_text('Бот будет проверять группу каждые 15 минут')
    await update.message.reply_text('Настроить фильтр по хештегам можно командой /filter_by_hashtag')
    await update.message.reply_text('Команда /new настроит новый канал')

    del_state(update, users_state)

    return ConversationHandler.END


async def cancel_new(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    users_state: dict[int, dict[str, Any]],
) -> int:
    metrics.telegram_conversations_total.labels(type='new', status='cancelled').inc()

    await update.message.reply_text('Ладно', reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text('Команда /new настроит новый канал')

    del_state(update, users_state)

    return ConversationHandler.END


@make_db_session
@observe_metrics('filter_by_hashtag')
async def filter_by_hashtag(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db: Session,
    users_state: dict[int, dict[str, Any]],
) -> int:
    user_id = update.message.from_user.id

    metrics.telegram_conversations_total.labels(type='filter_by_hashtag', status='started').inc()

    users_state[user_id] = dict()
    users_state[user_id]['channels'] = dict()
    keyboard: list[list[str]] = []
    keyboard_row: list[str] = []
    channels = db.scalars(select(Channel).where(Channel.owner_id == str(user_id)).order_by(Channel.created_at.desc()))
    for channel in channels:
        try:
            channel_chat = await context.bot.get_chat(chat_id=channel.channel_id)
            users_state[user_id]['channels'][channel_chat.title] = channel.channel_id
            keyboard_row.append(channel_chat.title)
            if len(keyboard_row) == 2:
                keyboard.append(keyboard_row)
                keyboard_row = []
        except telegram.error.TelegramError:
            logger.warning(
                'Failed to get channel title',
                channel_id=channel.channel_id,
                exc_info=True,
            )
    if len(keyboard_row) != 0:
        keyboard.append(keyboard_row)

    await update.message.reply_text(
        'Выберите канал', reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )

    return ASKED_CHANNEL_ID_IN_FILTER_BY_HASHTAG


@make_db_session
async def filter_by_hashtag_in_state_asked_channel_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db: Session,
    users_state: dict[int, dict[str, Any]],
) -> int:
    user_id = update.message.from_user.id
    channel_title = update.message.text
    channel_id = str(users_state[user_id]['channels'][channel_title])
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise ValueError(f'Channel {channel_id} does not exist')
    users_state[user_id]['channel_id'] = channel_id

    if channel.hashtag_filter is not None:
        await update.message.reply_text('Текущий фильтр по хештегам:')
        await update.message.reply_text(channel.hashtag_filter)
    await update.message.reply_text('Напишите новые хештеги (разделяйте запятой):')

    return ASKED_HASHTAGS_IN_FILTER_BY_HASHTAG


@make_db_session
async def filter_by_hashtag_in_state_asked_hashtags(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db: Session,
    users_state: dict[int, dict[str, Any]],
) -> int:
    user_id = update.message.from_user.id
    channel = db.get(Channel, users_state[user_id]['channel_id'])
    if channel is None:
        raise ValueError('Channel does not exist')

    try:
        channel.hashtag_filter = ','.join(h.strip() for h in update.message.text.split(','))
        db.commit()
        metrics.telegram_conversations_total.labels(type='filter_by_hashtag', status='completed').inc()
    except:
        db.rollback()
        metrics.telegram_conversations_total.labels(type='filter_by_hashtag', status='failed').inc()
        raise

    await update.message.reply_text('Сохранено!')

    del_state(update, users_state)

    return ConversationHandler.END


async def cancel_filter_by_hashtag(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    users_state: dict[int, dict[str, Any]],
) -> int:
    metrics.telegram_conversations_total.labels(type='filter_by_hashtag', status='cancelled').inc()

    await update.message.reply_text('Ладно', reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text('Настроить фильтр по хештегам можно командой /filter_by_hashtag')
    await update.message.reply_text('Команда /new настроит новый канал')

    del_state(update, users_state)

    return ConversationHandler.END


@make_db_session
@observe_metrics('recover')
async def recover(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db: Session,
    users_state: dict[int, dict[str, Any]],
) -> int:
    user_id = update.message.from_user.id

    metrics.telegram_conversations_total.labels(type='recover', status='started').inc()

    users_state[user_id] = dict()
    users_state[user_id]['channels'] = dict()
    keyboard: list[list[str]] = []
    keyboard_row: list[str] = []
    channels = db.scalars(
        select(DisabledChannel)
        .where(DisabledChannel.owner_id == str(user_id))
        .order_by(DisabledChannel.created_at.desc())
    )
    for channel in channels:
        title = f'{channel.vk_group_id} ({channel.channel_id})'
        users_state[user_id]['channels'][title] = channel.channel_id
        keyboard_row.append(title)
        if len(keyboard_row) == 2:
            keyboard.append(keyboard_row)
            keyboard_row = []
    if len(keyboard_row) != 0:
        keyboard.append(keyboard_row)

    if len(keyboard) == 0:
        await update.message.reply_text('Нет каналов, которые можно восстановить')
        del_state(update, users_state)

        return ConversationHandler.END
    else:
        await update.message.reply_text(
            'Выберите канал', reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )

        return ASKED_CHANNEL_ID_IN_RECOVER


@make_db_session
async def recover_in_state_asked_channel_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db: Session,
    users_state: dict[int, dict[str, Any]],
) -> int:
    user_id = update.message.from_user.id
    channel_title = update.message.text
    channel_id = str(users_state[user_id]['channels'][channel_title])
    disabled_channel = db.scalars(select(DisabledChannel).where(DisabledChannel.channel_id == channel_id)).one()

    try:
        db.add(
            Channel(
                channel_id=disabled_channel.channel_id,
                vk_group_id=disabled_channel.vk_group_id,
                last_vk_post_id=disabled_channel.last_vk_post_id,
                owner_id=disabled_channel.owner_id,
                owner_username=disabled_channel.owner_username,
                hashtag_filter=disabled_channel.hashtag_filter,
            )
        )
        db.delete(disabled_channel)
        db.commit()
        metrics.telegram_conversations_total.labels(type='recover', status='completed').inc()
    except:
        db.rollback()
        metrics.telegram_conversations_total.labels(type='recover', status='failed').inc()
        raise

    await update.message.reply_text('Готово!')
    await update.message.reply_text('Бот будет проверять группу каждые 15 минут')
    await update.message.reply_text('Настроить фильтр по хештегам можно командой /filter_by_hashtag')
    await update.message.reply_text('Команда /new настроит новый канал')

    del_state(update, users_state)

    return ConversationHandler.END


async def cancel_recover(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    users_state: dict[int, dict[str, Any]],
) -> int:
    metrics.telegram_conversations_total.labels(type='recover', status='cancelled').inc()

    await update.message.reply_text('Ладно', reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text('Команда /new настроит новый канал')

    del_state(update, users_state)

    return ConversationHandler.END
