import os
from threading import Thread

from vk_channelify import models, telegram_worker, vk_worker

if __name__ == '__main__':
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    vk_token = os.getenv('VK_TOKEN')
    db_url = os.getenv('DATABASE_URL')
    vk_thread_delay = 15 * 60  # 15 minutes

    db = models.connect_db(db_url)
    telegram_thread = Thread(target=telegram_worker, args=(telegram_token, db))
    vk_thread = Thread(target=vk_worker, args=(vk_thread_delay, vk_token, telegram_token, db))

    telegram_thread.start()
    vk_thread.start()

    telegram_thread.join()
    vk_thread.join()
