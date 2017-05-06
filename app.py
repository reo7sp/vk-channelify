import os

from vk_channelify import models, run_manage_worker, run_repost_worker

if __name__ == '__main__':
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    vk_token = os.getenv('VK_TOKEN')
    db_url = os.getenv('DATABASE_URL')
    vk_thread_delay = 15 * 60  # 15 minutes

    db = models.connect_db(db_url)
    telegram_updater = run_manage_worker(telegram_token, db)
    repost_thread = run_repost_worker(vk_thread_delay, vk_token, telegram_token, db)

    telegram_updater.idle()
