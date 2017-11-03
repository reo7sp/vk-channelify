import time
import traceback
from threading import Thread

import logging
import requests
import telegram

from vk_channelify.models.disabled_channel import DisabledChannel
from vk_channelify.vk_errors import VkError, VkWallAccessDeniedError
from .models import Channel

logger = logging.getLogger(__name__)


def run_worker(iteration_delay, vk_service_code, telegram_token, db_session_maker):
    thread = Thread(target=run_worker_inside_thread, args=(iteration_delay, vk_service_code, telegram_token, db_session_maker),
                    daemon=True)
    thread.start()
    return thread


def run_worker_inside_thread(iteration_delay, vk_service_code, telegram_token, db_session_maker):
    while True:
        try:
            db = db_session_maker()
            run_worker_iteration(vk_service_code, telegram_token, db)
            db.close()
        except Exception as e:
            logger.error('Iteration was failed because of {}'.format(e))
            traceback.print_exc()
        time.sleep(iteration_delay)


def run_worker_iteration(vk_service_code, telegram_token, db):
    bot = telegram.Bot(telegram_token)

    for channel in db.query(Channel):
        try:
            posts = fetch_group_posts(channel.vk_group_id, vk_service_code)

            for post in posts[::-1]:
                if post['id'] > channel.last_vk_post_id and is_passing_hashtag_filter(channel.hashtag_filter, post):
                    post_url = 'https://vk.com/wall{}_{}'.format(post['owner_id'], post['id'])
                    text = '{}\n\n{}'.format(post_url, post['text'])
                    if len(text) > 4000:
                        text = text[0:4000] + '...'
                    bot.send_message(channel.channel_id, text)

                    try:
                        channel.last_vk_post_id = max(post['id'] for post in posts)
                        db.commit()
                    except:
                        db.rollback()
                        raise
        except telegram.error.BadRequest as e:
            if 'chat not found' in e.message.lower():
                logger.warning('Disabling channel because of telegram error: {}'.format(e))
                traceback.print_exc()
                disable_channel(channel, db, bot)
            else:
                raise e
        except telegram.error.Unauthorized as e:
            logger.warning('Disabling channel because of telegram error: {}'.format(e))
            traceback.print_exc()
            disable_channel(channel, db, bot)
        except VkWallAccessDeniedError as e:
            logger.warning('Disabling channel because of vk error: {}'.format(e))
            traceback.print_exc()
            disable_channel(channel, db, bot)


def fetch_group_posts(group, vk_service_code):
    time.sleep(0.35)

    if group.startswith('club'):
        group_id = group[len('club'):]
        if group_id.isdigit():
            is_group_domain_passed = False
        else:
            is_group_domain_passed = True
    else:
        group_id = None
        is_group_domain_passed = True

    if is_group_domain_passed:
        r = requests.get(
            'https://api.vk.com/method/wall.get?domain={}&count=10&access_token={}&v=5.63'.format(group, vk_service_code))
    else:
        r = requests.get(
            'https://api.vk.com/method/wall.get?owner_id=-{}&count=10&access_token={}&v=5.63'.format(group_id, vk_service_code))
    j = r.json()

    if 'response' in j:
        return j['response']['items']
    else:
        logger.error('VK responded with {}'.format(j))
        error_code = int(j['error']['error_code'])
        if error_code in [15, 18, 19, 100]:
            raise VkWallAccessDeniedError(error_code, j['error']['error_msg'], j['error']['request_params'])
        else:
            raise VkError(error_code, j['error']['error_msg'], j['error']['request_params'])


def is_passing_hashtag_filter(hashtag_filter, post):
    if hashtag_filter is None:
        return True
    return any(hashtag in post['text'] for hashtag in hashtag_filter.split(','))


def disable_channel(channel, db, bot):
    logger.warning('Disabling channel {}'.format(channel.vk_group_id))

    try:
        db.add(
            DisabledChannel(
                channel_id=channel.channel_id,
                vk_group_id=channel.vk_group_id,
                last_vk_post_id=channel.last_vk_post_id,
                owner_id=channel.owner_id,
                owner_username=channel.owner_username,
                hashtag_filter=channel.hashtag_filter
            )
        )
        db.delete(channel)
        db.commit()
    except:
        db.rollback()
        raise

    try:
        bot.send_message(channel.owner_id, 'Канал https://vk.com/{} отключен'.format(channel.vk_group_id))
        bot.send_message(channel.owner_id, 'Так как не удается отправить в него сообщение')
        bot.send_message(channel.owner_id, 'ID канала {}'.format(channel.channel_id))
        bot.send_message(channel.owner_id, 'Чтобы восстановить канал, вызовите команду /recover')
    except telegram.error.TelegramError:
        logger.warning('Cannot send recover message to {} (id: {})'.format(channel.owner_username, channel.owner_id))
        traceback.print_exc()
