import threading

# Thread-local storage: each thread gets its own isolated TestContext instance
_thread_local = threading.local()


class TestContext:
    """
    Thread-safe context container for storing test attributes.

    Each thread/parallel worker gets its own isolated instance via thread-local
    storage, preventing cross-instance data leakage during parallel execution.
    """

    def __init__(self):
        self.__dict__['_data'] = {}

    def __getattr__(self, item):
        return self._data.get(item)

    def __setattr__(self, key, value):
        self._data[key] = value

    def clear(self):
        """Reset all data in the current thread's context."""
        self._data.clear()

    def as_dict(self):
        """Return a shallow copy of the current context data."""
        return dict(self._data)


def get_context() -> TestContext:
    """
    Return the TestContext instance for the current thread.

    Each parallel worker/thread receives its own isolated context,
    so set_attribute in one thread does NOT affect another thread.
    """
    if not hasattr(_thread_local, 'context'):
        _thread_local.context = TestContext()
    return _thread_local.context


class _ContextProxy:
    """
    A transparent module-level proxy that delegates all attribute access,
    assignment, and deletion to the current thread's TestContext instance.

    This allows callers to continue using:
        context.my_attr = "value"
        print(context.my_attr)
        context.clear()
    with zero code changes, while being fully thread-safe under parallel execution.
    """

    # Names that belong to the proxy itself and must NOT be forwarded
    _PROXY_ATTRS = frozenset({'_PROXY_ATTRS'})

    def __getattr__(self, item):
        return getattr(get_context(), item)

    def __setattr__(self, key, value):
        if key in _ContextProxy._PROXY_ATTRS:
            object.__setattr__(self, key, value)
        else:
            setattr(get_context(), key, value)

    def __delattr__(self, item):
        delattr(get_context(), item)

    def __repr__(self):
        return f"<ContextProxy thread={threading.current_thread().name} data={get_context().as_dict()}>"


# ✅ Module-level proxy — callers use `context.attr` as before; fully thread-safe
context = _ContextProxy()