import functools
from collections import OrderedDict
from inspect import isawaitable


def async_lru(size=100, evict_callback=None, cache=None):
    if cache is None:
        cache = OrderedDict()

    def decorator(fn):
        @functools.wraps(fn)
        async def memoizer(*args, **kwargs):
            key = str((args, kwargs))
            try:
                result = cache.pop(key)
                cache[key] = result
            except KeyError:
                if len(cache) >= size:
                    _, evicted = cache.popitem(last=False)
                    if evict_callback:
                        result = evict_callback(evicted)
                        if isawaitable(result):
                            await result
                result = await fn(*args, **kwargs)
                if args or kwargs:
                    if not isinstance(result, dict) or not result.get("__NOCACHE__"):
                        cache[key] = result
            return result

        return memoizer

    return decorator
