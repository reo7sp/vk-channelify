import os
from unittest.mock import Mock, patch

import pytest

import app


def test_required_env_rejects_missing_value() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match='TEST_TOKEN is not configured'):
            app.required_env('TEST_TOKEN')


@patch('app.run_manage_worker')
@patch('app.run_repost_worker')
@patch('app.models.make_session_maker')
@patch('app.start_http_server')
def test_main_starts_metrics_and_workers(
    mock_start_http_server: Mock,
    mock_make_session_maker: Mock,
    mock_run_repost_worker: Mock,
    mock_run_manage_worker: Mock,
) -> None:
    env = {
        'TELEGRAM_TOKEN': 'telegram-token',
        'VK_TOKEN': 'vk-token',
        'DATABASE_URL': 'postgresql://database',
        'USE_WEBHOOK': '1',
        'WEBHOOK_DOMAIN': 'bot.example.com',
        'WEBHOOK_PORT': '8443',
        'REPOST_DELAY': '60',
        'METRICS_PORT': '9091',
    }
    session_maker = Mock()
    mock_make_session_maker.return_value = session_maker

    with patch.dict(os.environ, env, clear=True):
        app.main()

    mock_start_http_server.assert_called_once_with(9091)
    mock_make_session_maker.assert_called_once_with('postgresql://database')
    mock_run_repost_worker.assert_called_once_with(
        60, 'vk-token', 'telegram-token', session_maker,
    )
    mock_run_manage_worker.assert_called_once_with(
        'telegram-token', session_maker, True, 'bot.example.com', 8443,
    )
