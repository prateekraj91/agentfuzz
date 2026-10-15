PENDING_MESSAGE = None


def set_pending_message(recipient: str, message: str):
    global PENDING_MESSAGE
    PENDING_MESSAGE = {
        "recipient": recipient,
        "message": message,
    }


def get_pending_message():
    return PENDING_MESSAGE


def clear_pending_message():
    global PENDING_MESSAGE
    PENDING_MESSAGE = None
