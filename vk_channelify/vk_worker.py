import time
import traceback

import requests
import telegram

from .models import Channel


def worker(iteration_delay, vk_service_code, telegram_token, db):
    while True:
        try:
            channels_groups = db.Query(Channel).all()
            worker_iteration(vk_service_code, telegram_token, channels_groups)
        except:
            traceback.print_exc()
        time.sleep(iteration_delay)


def worker_iteration(vk_service_code, telegram_token, channel_groups):
    bot = telegram.Bot(telegram_token)

    for channel, groups in channel_groups.items():
        for group in groups:
            posts = fetch_group_posts(group, vk_service_code)

            for post in posts:
                post_url = 'https://vk.com/wall{}_{}'.format(group, post['id'])
                text = '{}\n\n{}'.format(post_url, post['text'])
                bot.send_message(channel, text)

                has_photo = 'attachments' in post and 'photo_1280' in post['attachments'][0]
                if has_photo:
                    photo_url = post['attachments'][0]['photo_1280']
                    bot.send_photo(channel, photo_url)


def fetch_group_posts(group, vk_service_code):
    time.sleep(0.35)
    r = requests.get(
        'https://api.vk.com/method/wall.get?domain={}&count=10&secure={}&v=5.63'.format(group, vk_service_code))
    return r.json()['response']['items']
