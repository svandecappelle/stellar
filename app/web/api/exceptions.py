from __future__ import absolute_import


class RequestException(Exception):
    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv

    def __str__(self):
        return self.message

    def __repr__(self):
        return "<{}: {}>".format(self.__class__.__name__, str(self))


class APIException(Exception):
    def __init__(self, error_code, status_code, metadata=None, message=None):
        self.status_code = status_code
        self.metadata = metadata
        self.message = message

    def __str__(self):
        try:
            return self.message
        except Exception as e:
            from app.log import get_logger
            get_logger().critical(e)
            return repr(self)

    def as_dict(self, include_request_id=False):
        flat = dict()
        flat['status_code'] = self.status_code
        flat['metadata'] = self.metadata
        flat['error_code'] = self.error_code
        flat['message'] = self.message
        if include_request_id:
            from app.log import get_request_id
            flat['request_id'] = get_request_id()
        return flat

    def __repr__(self):
        return "<{}: {}>".format(self.__class__.__name__, self.error_code)


class ServerError(RequestException):
    """"""
    status_code = 500


class InvalidRequest(RequestException):
    status_code = 400


class CombinationsExceed(Exception):
    """
    Generic exception for number of combinations that's exceeded
    Raise it with the specific message:
        raise ErrorResponse("combination exceeded")
    """


class ErrorResponse(RequestException):
    """
    Generic exception for http codes.
    Raise it with the specific code:
        raise ErrorResponse("err description", 4XX)
    """
    pass


class NotModified(RequestException):
    """"""
    status_code = 304


class NotFoundError(RequestException):
    """"""
    status_code = 404


class MissingParameters(RequestException):
    """"""
    status_code = 400


class MissingMandatoryParameters(RequestException):
    """"""
    status_code = 400


class InvalidParameters(RequestException):
    """"""
    status_code = 404


class ConflictError(RequestException):
    """"""
    status_code = 409


class PermissionDeniedError(RequestException):
    """"""
    status_code = 403


class DeprecatedError(RequestException):
    """"""
    status_code = 410
