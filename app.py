import os

import logging
from prometheus_client import start_http_server

from vk_channelify import models, run_manage_worker, run_repost_worker
from vk_channelify.logging_utils import RedactSecretsFilter


def required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError('{} is not configured'.format(name))
    return value


def main() -> None:
    telegram_token = required_env('TELEGRAM_TOKEN')
    vk_token = required_env('VK_TOKEN')
    db_url = required_env('DATABASE_URL')
    use_webhook = bool(int(os.getenv('USE_WEBHOOK', '0')))
    webhook_domain = os.getenv('WEBHOOK_DOMAIN', '127.0.0.1')
    webhook_port = int(os.getenv('WEBHOOK_PORT', os.getenv('PORT', 80)))
    vk_thread_delay = int(os.getenv('REPOST_DELAY', 15 * 60))  # 15 minutes
    metrics_port = int(os.getenv('METRICS_PORT', 9090))

    logging.basicConfig(level=logging.INFO)
    secrets_filter = RedactSecretsFilter(telegram_token, vk_token)
    for handler in logging.getLogger().handlers:
        handler.addFilter(secrets_filter)
    logger = logging.getLogger(__name__)

    try:
        start_http_server(metrics_port)
        logger.info('Prometheus metrics server started on port {}'.format(metrics_port))
    except Exception as e:
        logger.warning('Failed to start Prometheus metrics server: {}'.format(e))

    db_session_maker = models.make_session_maker(db_url)
    run_repost_worker(vk_thread_delay, vk_token, telegram_token, db_session_maker)
    run_manage_worker(telegram_token, db_session_maker, use_webhook, webhook_domain, webhook_port)


if __name__ == '__main__':
    main()
