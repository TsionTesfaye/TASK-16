import enum


class ContactChannel(str, enum.Enum):
    LOGGED_MESSAGE = "logged_message"
    PHONE_CALL = "phone_call"
