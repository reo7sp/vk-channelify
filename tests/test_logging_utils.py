import logging

from hamcrest import assert_that, equal_to

from vk_channelify.logging_utils import RedactSecretsFilter


def test_redacts_secrets_from_log_record() -> None:
    record = logging.LogRecord(
        name='test', level=logging.ERROR, pathname=__file__, lineno=1,
        msg='Request /bot%s/getUpdates failed; vk=%s',
        args=('telegram-secret', 'vk-secret'), exc_info=None
    )

    assert_that(RedactSecretsFilter('telegram-secret', 'vk-secret').filter(record), equal_to(True))
    assert_that(record.getMessage(), equal_to('Request /bot<redacted>/getUpdates failed; vk=<redacted>'))
