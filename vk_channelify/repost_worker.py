import asyncio
import datetime
import time
import traceback
from typing import Any
from threading import Thread

import logging
import requests
import telegram
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from vk_channelify.models.disabled_channel import DisabledChannel
from vk_channelify.vk_errors import VKError, VKWallAccessDeniedError
from .models import Channel
from . import metrics

logger = logging.getLogger(__name__)

VK_API_TIMEOUT_SECONDS = 30


def run_worker(
    iteration_delay: int,
    vk_service_code: str,
    telegram_token: str,
    db_session_maker: sessionmaker[Session],
) -> Thread:
    thread = Thread(target=run_worker_inside_thread,
                    args=(iteration_delay, vk_service_code, telegram_token, db_session_maker),
                    daemon=True)
    thread.start()
    return thread


def run_worker_inside_thread(
    iteration_delay: int,
    vk_service_code: str,
    telegram_token: str,
    db_session_maker: sessionmaker[Session],
) -> None:
    while True:
        db = None
        start_time = datetime.datetime.now()
        logger.info('New iteration {}'.format(start_time))
        metrics.repost_iterations_total.inc()

        try:
            db = db_session_maker()
            with metrics.repost_iteration_duration_seconds.time():
                asyncio.run(run_worker_iteration(vk_service_code, telegram_token, db))
        except Exception as e:
            logger.error('Iteration was failed because of {}'.format(e))
            traceback.print_exc()
            metrics.repost_errors_total.labels(error_type='iteration_failed', channel_id='', vk_group_id='').inc()
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception as e:
                    logger.error('Iteration has failed db.close() because of {}'.format(e))
                    traceback.print_exc()

        end_time = datetime.datetime.now()
        logger.info('Finished iteration {} ({})'.format(end_time, end_time - start_time))

        time.sleep(iteration_delay)


async def run_worker_iteration(
    vk_service_code: str, telegram_token: str, db: Session
) -> None:
    async with telegram.Bot(telegram_token) as bot:
        await run_worker_iteration_with_bot(vk_service_code, bot, db)


async def run_worker_iteration_with_bot(
    vk_service_code: str, bot: telegram.Bot, db: Session
) -> None:
    active_count = db.scalar(select(func.count()).select_from(Channel))
    disabled_count = db.scalar(select(func.count()).select_from(DisabledChannel))

    metrics.active_channels_gauge.set(active_count)
    metrics.disabled_channels_gauge.set(disabled_count)

    for channel in db.scalars(select(Channel)):
        try:
            log_id = '{} (id: {})'.format(channel.vk_group_id, channel.channel_id)
            metrics_kwargs = {
                'channel_id': channel.channel_id,
                'vk_group_id': channel.vk_group_id,
            }

            posts = fetch_group_posts(channel.vk_group_id, vk_service_code)
            posts_sent = 0

            for post in sorted(posts, key=lambda p: p['id']):
                if post['id'] <= channel.last_vk_post_id:
                    continue
                if not is_passing_hashtag_filter(channel.hashtag_filter, post):
                    continue

                post_url = 'https://vk.ru/wall{}_{}'.format(post['owner_id'], post['id'])
                text = '{}\n\n{}'.format(post_url, post['text'])
                if len(text) > 4000:
                    text = text[0:4000] + '...'

                try:
                    await bot.send_message(channel.channel_id, text)
                    metrics.telegram_api_requests_total.labels(method='send_message', status='success', **metrics_kwargs).inc()
                    posts_sent += 1
                    metrics.repost_posts_sent_total.labels(**metrics_kwargs).inc()
                except telegram.error.TelegramError as send_error:
                    metrics.telegram_api_requests_total.labels(method='send_message', status='error', **metrics_kwargs).inc()
                    raise send_error

                try:
                    channel.last_vk_post_id = post['id']
                    db.commit()
                except:
                    db.rollback()
                    raise

            if posts_sent:
                logger.info('Success sent {} posts on channel {}'.format(posts_sent, log_id))

        except telegram.error.BadRequest as e:
            if 'chat not found' in e.message.lower():
                logger.warning('Disabling channel {} because of telegram error: {}'.format(log_id, e))
                traceback.print_exc()
                metrics.repost_errors_total.labels(error_type='telegram_chat_not_found', **metrics_kwargs).inc()
                await disable_channel(channel, db, bot)
            else:
                metrics.repost_errors_total.labels(error_type='telegram_bad_request', **metrics_kwargs).inc()
                raise e

        except telegram.error.Forbidden as e:
            logger.warning('Disabling channel {} because of telegram error: {}'.format(log_id, e))
            traceback.print_exc()
            metrics.repost_errors_total.labels(error_type='telegram_unauthorized', **metrics_kwargs).inc()
            await disable_channel(channel, db, bot)

        except telegram.error.TimedOut as e:
            logger.warning('Got telegram TimedOut error on channel {}'.format(log_id))
            metrics.repost_errors_total.labels(error_type='telegram_timeout', **metrics_kwargs).inc()

        except requests.Timeout as e:
            logger.warning('Got VK timeout on channel {}: {}'.format(log_id, e))
            metrics.repost_errors_total.labels(error_type='vk_timeout', **metrics_kwargs).inc()
            raise

        except requests.ConnectionError as e:
            logger.warning('Got VK connection error on channel {}: {}'.format(log_id, e))
            metrics.repost_errors_total.labels(error_type='vk_connection_error', **metrics_kwargs).inc()
            raise

        except requests.RequestException as e:
            logger.warning('Got VK request error on channel {}: {}'.format(log_id, e))
            metrics.repost_errors_total.labels(error_type='vk_request_error', **metrics_kwargs).inc()
            raise

        except VKWallAccessDeniedError as e:
            logger.warning('Disabling channel {} because of vk error: {}'.format(log_id, e))
            traceback.print_exc()
            metrics.repost_errors_total.labels(error_type='vk_wall_access_denied', **metrics_kwargs).inc()
            await disable_channel(channel, db, bot)

        except VKError as e:
            logger.warning('Got VK API error on channel {}: {}'.format(log_id, e))
            metrics.repost_errors_total.labels(error_type='vk_api_error', **metrics_kwargs).inc()
            raise


def fetch_group_posts(group: str, vk_service_code: str) -> list[dict[str, Any]]:
    time.sleep(0.35)

    group_id = extract_group_id_if_has(group)
    is_group_domain_passed = group_id is None

    if is_group_domain_passed:
        url = 'https://api.vk.ru/method/wall.get?domain={}&count=10&access_token={}&v=5.131'.format(group, vk_service_code)
    else:
        url = 'https://api.vk.ru/method/wall.get?owner_id=-{}&count=10&access_token={}&v=5.131'.format(group_id, vk_service_code)

    try:
        r = requests.get(url, timeout=VK_API_TIMEOUT_SECONDS)
        r.raise_for_status()
    except requests.RequestException:
        metrics.vk_api_requests_total.labels(method='wall.get', status='error', vk_group_id=group).inc()
        raise

    j = r.json()

    if 'response' not in j:
        logger.error('VK responded with {}'.format(j))
        metrics.vk_api_requests_total.labels(method='wall.get', status='error', vk_group_id=group).inc()

        error_code = int(j['error']['error_code'])
        if error_code in [15, 18, 19, 100]:
            raise VKWallAccessDeniedError(error_code, j['error']['error_msg'], j['error']['request_params'])
        else:
            raise VKError(error_code, j['error']['error_msg'], j['error']['request_params'])

    metrics.vk_api_requests_total.labels(method='wall.get', status='success', vk_group_id=group).inc()

    return j['response']['items']


def extract_group_id_if_has(group_name: str) -> str | None:
    domainless_group_prefixes = ['club', 'public']
    for prefix in domainless_group_prefixes:
        if group_name.startswith(prefix):
            group_id = group_name[len(prefix):]
            if group_id.isdigit():
                return group_id

    return None


def is_passing_hashtag_filter(
    hashtag_filter: str | None, post: dict[str, Any]
) -> bool:
    if hashtag_filter is None:
        return True

    return any(hashtag.strip() in post['text'] for hashtag in hashtag_filter.split(','))


async def disable_channel(channel: Channel, db: Session, bot: telegram.Bot) -> None:
    log_id = '{} (id: {})'.format(channel.vk_group_id, channel.channel_id)
    metrics_kwargs = {
        'channel_id': channel.channel_id,
        'vk_group_id': channel.vk_group_id,
    }

    logger.warning('Disabling channel {}'.format(log_id))
    metrics.channels_disabled_total.labels(**metrics_kwargs).inc()

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
        await bot.send_message(channel.owner_id, 'Канал https://vk.ru/{} отключен'.format(channel.vk_group_id))
        await bot.send_message(channel.owner_id, 'Так как не удается отправить в него сообщение')
        await bot.send_message(channel.owner_id, 'ID канала {}'.format(channel.channel_id))
        await bot.send_message(channel.owner_id, 'Чтобы восстановить канал, вызовите команду /recover')
    except telegram.error.TelegramError:
        logger.warning('Cannot send recover message to {} (id: {})'.format(channel.owner_username, channel.owner_id))
        traceback.print_exc()
