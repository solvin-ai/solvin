# modules/routers_utils.py

def object_to_dict(obj):
    """
    A no-op for dicts, or pull out .dict() or .__dict__ for other objects.
    """
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "dict") and callable(obj.dict):
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return obj