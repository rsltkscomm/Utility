class TestContext:
    def __init__(self):
        self.__dict__['_data'] = {}

    def __getattr__(self, item):
        return self._data.get(item)

    def __setattr__(self, key, value):
        self._data[key] = value


# ✅ Global shared instance
context = TestContext()