class CheckError(Exception):
    pass


class CheckErrorWithCode(CheckError):

    def __init__(self, code):
        self.code = code
