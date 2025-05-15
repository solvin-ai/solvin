# modules/detect_repo_utils.py

def parse_jdk_version(version_str):

    """
    Converts a version string like "1.8" or "11" to an integer value.

    Examples:
    parse_jdk_version("1.8") returns 8
    parse_jdk_version("11") returns 11
    
    If conversion fails, returns None.
    """

    try:
        version_str = version_str.strip()
        if version_str.startswith("1."):
            parts = version_str.split('.')
            if len(parts) >= 2:
                return int(parts[1])
        else:
            # For non "1.x" versions:
            return int(version_str.split('.')[0])
    except Exception:
        return None
