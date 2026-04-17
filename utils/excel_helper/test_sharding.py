import os

def should_run_test(test_index):
    shard_index = int(os.getenv("SHARD_INDEX", 1))
    total_shards = int(os.getenv("TOTAL_SHARDS", 1))

    return test_index % total_shards == (shard_index - 1)