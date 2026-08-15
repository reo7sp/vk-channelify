class VKError(Exception):
    def __init__(
        self, code: int, message: str, request_params: list[dict[str, object]]
    ) -> None:
        super().__init__()
        self.code = code
        self.message = message
        self.request_params = request_params

    def __str__(self) -> str:
        return 'VKError {}: {} (request_params: {})'.format(self.code, self.message, self.request_params)


class VKWallAccessDeniedError(VKError):
    def __init__(
        self, code: int, message: str, request_params: list[dict[str, object]]
    ) -> None:
        super().__init__(code, message, request_params)
