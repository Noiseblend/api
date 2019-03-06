from typing import Any, Callable


def transform_keys(obj: Any, transform: Callable[[str], str]) -> Any:
    if isinstance(obj, (list, tuple, set)):
        return [transform_keys(item, transform) for item in obj]

    if isinstance(obj, dict):
        transformed = {}
        for key, value in obj.items():
            if isinstance(obj[key], dict):
                value = transform_keys(obj[key], transform)
            elif isinstance(obj[key], (list, tuple, set)):
                value = [transform_keys(item, transform) for item in obj[key]]
            transformed[transform(key)] = value
        return transformed

    return obj
