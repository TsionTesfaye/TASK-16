import enum


class CustomerPhonePreference(str, enum.Enum):
    CALLS_ONLY = "calls_only"
    STANDARD_CALLS = "standard_calls"
