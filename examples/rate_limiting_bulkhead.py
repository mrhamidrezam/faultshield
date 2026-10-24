"""Example: Rate Limiter and Bulkhead Concurrency Control."""

import concurrent.futures
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from faultshield import Bulkhead, BulkheadFullError, RateLimiter, RateLimitExceededError

limiter = RateLimiter(rate=5.0, capacity=5.0)
bulkhead = Bulkhead(max_concurrent=3, max_queued=2, queue_timeout=0.2)


def process_item(item_id: int):
    try:
        with limiter:
            with bulkhead:
                time.sleep(0.05)
                return f"Processed {item_id}"
    except (RateLimitExceededError, BulkheadFullError) as e:
        return f"Throttled {item_id}: {type(e).__name__}"


if __name__ == "__main__":
    print("Dispatching 10 parallel tasks across rate-limited and bulkhead-isolated worker pool...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_item, i) for i in range(10)]
        for f in concurrent.futures.as_completed(futures):
            print(" ", f.result())
