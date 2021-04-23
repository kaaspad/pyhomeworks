
class HomeworksException(Exception):
    pass


class HomeworksConnectionLost(HomeworksException):
    pass


class HomeworksAuthenticationException(HomeworksException):
    pass


class HomeworksNoCredentialsProvided(HomeworksAuthenticationException):
    pass


class InvalidCredentialsProvided(HomeworksAuthenticationException):
    pass