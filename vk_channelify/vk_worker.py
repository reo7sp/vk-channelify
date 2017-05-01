import time
import traceback
from threading import Thread

import requests
import telegram

from vk_channelify.models.disabled_channel import DisabledChannel
from .models import Channel


def worker(iteration_delay, vk_service_code, telegram_token, db):
    thread = Thread(target=thread_worker, args=(iteration_delay, vk_service_code, telegram_token, db), daemon=True)
    thread.start()
    return thread


def thread_worker(iteration_delay, vk_service_code, telegram_token, db):
    while True:
        try:
            worker_iteration(vk_service_code, telegram_token, db)
        except:
            traceback.print_exc()
        time.sleep(iteration_delay)


def worker_iteration(vk_service_code, telegram_token, db):
    bot = telegram.Bot(telegram_token)

    for channel in db.query(Channel):
        try:
            posts = fetch_group_posts(channel.vk_group_id, vk_service_code)

            for post in posts[::-1]:
                if post['id'] > channel.last_vk_post_id:
                    post_url = 'https://vk.com/wall{}_{}'.format(post['owner_id'], post['id'])
                    text = '{}\n\n{}'.format(post_url, post['text'])
                    bot.send_message(channel.channel_id, text)

            channel.last_vk_post_id = max(post['id'] for post in posts)
            db.commit()
        except telegram.error.Unauthorized:
            db.add(DisabledChannel(vk_group_id=channel.vk_group_id))
            db.delete(channel)
            db.commit()


def fetch_group_posts(group, vk_service_code):
    time.sleep(0.35)
    r = requests.get(
        'https://api.vk.com/method/wall.get?domain={}&count=10&secure={}&v=5.63'.format(group, vk_service_code))
    return r.json()['response']['items']
