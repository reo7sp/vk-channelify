import logging
import re

import pytest
import structlog

from vk_channelify.logging_utils import RedactSecrets, configure_logging


def test_redacts_secrets_from_structured_values() -> None:
    processor = RedactSecrets('telegram-secret', 'vk-secret')

    event = processor(
        None,
        'error',
        {
            'event': 'Request /bottelegram-secret/getUpdates failed',
            'details': {'vk_token': 'vk-secret'},
        },
    )

    assert event == {
        'event': 'Request /bot<redacted>/getUpdates failed',
        'details': {'vk_token': '<redacted>'},
    }


def test_configures_structlog_and_standard_logging(
    capsys: pytest.CaptureFixture[str],
) -> None:
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers.copy()
    original_level = root_logger.level

    try:
        configure_logging('secret')

        structlog.get_logger('structured').info('request completed', token='secret')
        logging.getLogger('standard').warning('request failed: %s', 'secret')

        output = capsys.readouterr().err
    finally:
        for handler in root_logger.handlers:
            handler.close()
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)
        root_logger.setLevel(original_level)
        structlog.reset_defaults()

    assert 'request completed' in output
    assert 'request failed: <redacted>' in output
    assert 'structured' in output
    assert 'standard' in output
    assert 'secret' not in output
    assert re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', output)
