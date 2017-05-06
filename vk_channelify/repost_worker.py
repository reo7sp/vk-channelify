import time
import traceback
from threading import Thread

import requests
import telegram

from vk_channelify.models.disabled_channel import DisabledChannel
from .models import Channel


def run_worker(iteration_delay, vk_service_code, telegram_token, db):
    thread = Thread(target=run_worker_inside_thread, args=(iteration_delay, vk_service_code, telegram_token, db), daemon=True)
    thread.start()
    return thread


def run_worker_inside_thread(iteration_delay, vk_service_code, telegram_token, db):
    while True:
        try:
            run_worker_iteration(vk_service_code, telegram_token, db)
        except:
            traceback.print_exc()
        time.sleep(iteration_delay)


def run_worker_iteration(vk_service_code, telegram_token, db):
    bot = telegram.Bot(telegram_token)

    for channel in db.query(Channel):
        try:
            posts = fetch_group_posts(channel.vk_group_id, vk_service_code)

            for post in posts[::-1]:
                if post['id'] > channel.last_vk_post_id and is_passing_hashtag_fitler(channel.hashtag_filter, post):
                    post_url = 'https://vk.com/wall{}_{}'.format(post['owner_id'], post['id'])
                    text = '{}\n\n{}'.format(post_url, post['text'])
                    bot.send_message(channel.channel_id, text)

            channel.last_vk_post_id = max(post['id'] for post in posts)
            db.commit()
        except (telegram.error.Unauthorized, KeyError):
            db.add(DisabledChannel(vk_group_id=channel.vk_group_id, last_vk_post_id=channel.last_vk_post_id,
                                   owner_id=channel.owner_id, owner_username=channel.owner_username))
            db.delete(channel)
            db.commit()


def fetch_group_posts(group, vk_service_code):
    time.sleep(0.35)
    r = requests.get(
        'https://api.vk.com/method/wall.get?domain={}&count=10&secure={}&v=5.63'.format(group, vk_service_code))
    return r.json()['response']['items']


def is_passing_hashtag_fitler(hashtag_filter, post):
    if hashtag_filter is None:
        return True
    return any(hashtag in post['text'] for hashtag in hashtag_filter.split(','))
