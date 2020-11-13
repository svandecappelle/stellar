class APIException(Exception):
    status_code = 500

    def __init__(self, status_code, message=None, metadata=None):
        self.status_code = status_code
        self.message = message
        self.metadata = metadata

    def __str__(self):
        return self.message

    @property
    def serialize(self):
        return {
            'status_code': self.status_code,
            'metadata': self.metadata,
            'message': self.message
        }

    def __repr__(self):
        return "<{}: {}>".format(self.__class__.__name__, self.status_code)


class ServerError(APIException):

    def __init__(self, message=None):
        super(ServerError, self).__init__(status_code=500, message=message)


class ConflictError(APIException):

    def __init__(self, message=None):
        super(ConflictError, self).__init__(status_code=409, message=message)


class BadRequestError(APIException):

    def __init__(self, message=None):
        super(BadRequestError, self).__init__(status_code=400, message=message)


class NotFoundError(APIException):

    def __init__(self, message=None):
        super(NotFoundError, self).__init__(status_code=404, message=message)


class PermissionDeniedError(APIException):

    def __init__(self, message=None):
        super(PermissionDeniedError, self).__init__(status_code=403, message=message)
