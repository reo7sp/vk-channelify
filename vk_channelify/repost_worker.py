import datetime
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
    thread = Thread(target=run_worker_inside_thread,
                    args=(iteration_delay, vk_service_code, telegram_token, db_session_maker),
                    daemon=True)
    thread.start()
    return thread


def run_worker_inside_thread(iteration_delay, vk_service_code, telegram_token, db_session_maker):
    while True:
        start_time = datetime.datetime.now()
        logger.info('New iteration {}'.format(start_time))

        try:
            db = db_session_maker()
            run_worker_iteration(vk_service_code, telegram_token, db)
        except Exception as e:
            logger.error('Iteration was failed because of {}'.format(e))
            traceback.print_exc()
        finally:
            try:
                db.close()
            except Exception as e:
                logger.error('Iteration has failed db.close() because of {}'.format(e))
                traceback.print_exc()

        end_time = datetime.datetime.now()
        logger.info('Finished iteration {} ({})'.format(end_time, end_time - start_time))

        time.sleep(iteration_delay)


def run_worker_iteration(vk_service_code, telegram_token, db):
    bot = telegram.Bot(telegram_token)

    for channel in db.query(Channel):
        try:
            posts = fetch_group_posts(channel.vk_group_id, vk_service_code)

            for post in sorted(posts, key=lambda p: p['id']):
                if post['id'] <= channel.last_vk_post_id:
                    continue
                if not is_passing_hashtag_filter(channel.hashtag_filter, post):
                    continue

                post_url = 'https://vk.com/wall{}_{}'.format(post['owner_id'], post['id'])
                text = '{}\n\n{}'.format(post_url, post['text'])
                if len(text) > 4000:
                    text = text[0:4000] + '...'

                bot.send_message(channel.channel_id, text)

                try:
                    channel.last_vk_post_id = post['id']
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
        except telegram.error.TimedOut as e:
            logger.warning('Got telegram TimedOut error on channel {} (id: {})'.format(channel.vk_group_id, channel.channel_id))
        except VkWallAccessDeniedError as e:
            logger.warning('Disabling channel because of vk error: {}'.format(e))
            traceback.print_exc()
            disable_channel(channel, db, bot)


def fetch_group_posts(group, vk_service_code):
    time.sleep(0.35)

    group_id = extract_group_id_if_has(group)
    is_group_domain_passed = group_id is None

    if is_group_domain_passed:
        url = 'https://api.vk.com/method/wall.get?domain={}&count=10&access_token={}&v=5.131'.format(group, vk_service_code)
        r = requests.get(url)
    else:
        url = 'https://api.vk.com/method/wall.get?owner_id=-{}&count=10&access_token={}&v=5.131'.format(group_id, vk_service_code)
        r = requests.get(url)
    j = r.json()

    if 'response' not in j:
        logger.error('VK responded with {}'.format(j))
        error_code = int(j['error']['error_code'])
        if error_code in [15, 18, 19, 100]:
            raise VkWallAccessDeniedError(error_code, j['error']['error_msg'], j['error']['request_params'])
        else:
            raise VkError(error_code, j['error']['error_msg'], j['error']['request_params'])

    return j['response']['items']


def extract_group_id_if_has(group_name):
    domainless_group_prefixes = ['club', 'public']
    for prefix in domainless_group_prefixes:
        if group_name.startswith(prefix):
            group_id = group_name[len(prefix):]
            if group_id.isdigit():
                return group_id
    return None


def is_passing_hashtag_filter(hashtag_filter, post):
    if hashtag_filter is None:
        return True
    return any(hashtag.strip() in post['text'] for hashtag in hashtag_filter.split(','))


def disable_channel(channel, db, bot):
    logger.warning('Disabling channel {} (id: {})'.format(channel.vk_group_id, channel.channel_id))

    try:
        db.add(DisabledChannel(channel_id=channel.channel_id,
                               vk_group_id=channel.vk_group_id,
                               last_vk_post_id=channel.last_vk_post_id,
                               owner_id=channel.owner_id,
                               owner_username=channel.owner_username,
                               hashtag_filter=channel.hashtag_filter))
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
