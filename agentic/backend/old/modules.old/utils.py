# modules/utils.py

"""
General utility functions.

These functions provide common services (e.g. escaping and truncation of strings, logging helpers)
that are not specific to tool calls or turn management.
"""

from modules.logs import logger

def escape_special_chars(s):
    """
    Escapes special Unicode characters in a string.

    Parameters:
        s (str): Input string.

    Returns:
        str: The escaped string.
    """
    try:
        return s.encode("unicode_escape").decode("ascii")
    except Exception:
        return s

def truncate_string_for_log(s, max_length):
    """
    Truncates a string to a maximum length for logging purposes.

    Parameters:
        s (str): Input string.
        max_length (int): Maximum allowed length.

    Returns:
        str: Truncated string with an appended ellipsis if truncated.
    """
    s_escaped = escape_special_chars(s)
    if len(s_escaped) <= max_length:
        return s_escaped
    if s_escaped[max_length - 1] == "\\":
        return s_escaped[:max_length - 1] + "…"
    return s_escaped[:max_length - 3] + "…"

def truncate_text(text, max_length=20):
    """
    Truncates text for logging.

    Parameters:
        text (str): The text to truncate.
        max_length (int): Maximum length for the output.

    Returns:
        str: Truncated text.
    """
    if not isinstance(text, str):
        return text
    return truncate_string_for_log(text, max_length)

def truncate_args(args, max_length=20):
    """
    Recursively truncates all string values in a dictionary or list.

    Parameters:
        args: Data structure containing strings (dict, list, or str).
        max_length (int): Maximum allowed length for strings.

    Returns:
        The structure with all strings truncated.
    """
    if isinstance(args, dict):
        return {k: truncate_args(v, max_length) for k, v in args.items()}
    elif isinstance(args, list):
        return [truncate_args(item, max_length) for item in args]
    elif isinstance(args, str):
        return truncate_string_for_log(args, max_length)
    else:
        return args

def log_message_deletion(message_id, delete_reason, mode, message_logs=None):
    """
    Logs the deletion of a message.

    Parameters:
        message_id: The message identifier.
        delete_reason (str): Reason for deletion.
        mode (str): Mode in which deletion occurred.
        message_logs (list, optional): A list in which to append detailed log entries.
    """
    log_msg = (
        f"DETAILED DELETION: Message {message_id} marked as DELETED "
        f"(Mode: {mode}) – Reason: {delete_reason}"
    )
    logger.info(log_msg)
    if message_logs is not None:
        message_logs.append(log_msg)

if __name__ == "__main__":
    sample_text = "This is a sample string with weird \n characters and a very long sentence that will be truncated."
    print("Original text:")
    print(sample_text)
    print("\nTruncated text (max 40 chars):")
    print(truncate_text(sample_text, 40))
