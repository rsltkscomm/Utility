import os

def pytest_collection_modifyitems(config, items):
    shard_index = int(os.getenv("SHARD_INDEX", 1))
    total_shards = int(os.getenv("TOTAL_SHARDS", 1))

    items[:] = [
        item for i, item in enumerate(items)
        if i % total_shards == (shard_index - 1)
    ]