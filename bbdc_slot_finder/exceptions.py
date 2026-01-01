from bbdc_slot_finder.logger import logger


class NameError(Exception):
    def __init__(self, *args: object) -> None:
        logger.warning("User not exists.")
        super().__init__(*args)


class TokenExpireError(Exception):
    def __init__(self, msg="Token expired"):
        print(f"Suspected token expire: {msg}")
        logger.warning(f"Suspected token expire: {msg}.")
        super().__init__(msg)  # Call the base Exception class' initializer
        self.msg = msg


class SessionStopError(Exception):
    pass
