import logging


class RedactSecretsFilter(logging.Filter):
    def __init__(self, *secrets: str | None) -> None:
        super().__init__()
        self.secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, '<redacted>')
        record.msg = message
        record.args = ()
        return True
