import enum


class CallAttemptStatus(str, enum.Enum):
    NOT_APPLICABLE = "not_applicable"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    VOICEMAIL = "voicemail"
    NO_ANSWER = "no_answer"
