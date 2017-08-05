class VkError(Exception):
    def __init__(self, code, message, request_params):
        super(VkError, self).__init__()
        self.code = code
        self.message = message
        self.request_params = request_params

    def __str__(self):
        return 'VkError {}: {} (request_params: {})'.format(self.code, self.message, self.request_params)


class VkWallAccessDeniedError(VkError):
    def __init__(self, code, message, request_params):
        super(VkWallAccessDeniedError, self).__init__(code, message, request_params)


class VkGroupDoesntExistError(VkError):
    def __init__(self, group):
        super(VkError, self).__init__()
        self.group = group

    def __str__(self):
        return 'VkError: Group {} doesnt exist'.format(self.group)
