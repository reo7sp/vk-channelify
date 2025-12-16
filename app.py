import os

import logging
from prometheus_client import start_http_server

from vk_channelify import models, run_manage_worker, run_repost_worker


if __name__ == '__main__':
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    vk_token = os.getenv('VK_TOKEN')
    db_url = os.getenv('DATABASE_URL')
    use_webhook = bool(int(os.getenv('USE_WEBHOOK', False)))
    webhook_domain = os.getenv('WEBHOOK_DOMAIN', '127.0.0.1')
    webhook_port = int(os.getenv('WEBHOOK_PORT', os.getenv('PORT', 80)))
    vk_thread_delay = int(os.getenv('REPOST_DELAY', 15 * 60))  # 15 minutes
    metrics_port = int(os.getenv('METRICS_PORT', 9090))

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        start_http_server(metrics_port)
        logger.info('Prometheus metrics server started on port {}'.format(metrics_port))
    except Exception as e:
        logger.warning('Failed to start Prometheus metrics server: {}'.format(e))

    db_session_maker = models.make_session_maker(db_url)
    telegram_updater = run_manage_worker(telegram_token, db_session_maker, use_webhook, webhook_domain, webhook_port)
    repost_thread = run_repost_worker(vk_thread_delay, vk_token, telegram_token, db_session_maker)

    telegram_updater.idle()
