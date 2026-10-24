"""Unit tests for faultshield.bulkhead."""

import threading
import time
import pytest

from faultshield.bulkhead import Bulkhead
from faultshield.exceptions import BulkheadFullError, ResilienceConfigurationError


def test_bulkhead_init_validation():
    with pytest.raises(ResilienceConfigurationError):
        Bulkhead(max_concurrent=0)
    with pytest.raises(ResilienceConfigurationError):
        Bulkhead(max_concurrent=5, max_queued=-1)
    with pytest.raises(ResilienceConfigurationError):
        Bulkhead(max_concurrent=5, queue_timeout=-0.5)


def test_bulkhead_concurrency_limit():
    bh = Bulkhead(max_concurrent=2, max_queued=0)
    barrier = threading.Barrier(3)
    results = []

    def worker(worker_id):
        def task():
            barrier.wait()
            time.sleep(0.05)
            results.append(worker_id)

        bh.execute(task)

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    t2.start()

    barrier.wait()  # Both workers acquired slots
    assert bh.active_calls == 2

    # A 3rd simultaneous call should be rejected immediately since max_queued=0
    with pytest.raises(BulkheadFullError):
        bh.execute(lambda: "rejected")

    t1.join()
    t2.join()
    assert bh.active_calls == 0
    assert len(results) == 2


def test_bulkhead_queue_wait_and_succeed():
    bh = Bulkhead(max_concurrent=1, max_queued=2, queue_timeout=0.5)
    order = []

    def task(task_id, sleep_time):
        def work():
            time.sleep(sleep_time)
            order.append(task_id)

        bh.execute(work)

    t1 = threading.Thread(target=task, args=("first", 0.08))
    t2 = threading.Thread(target=task, args=("second", 0.01))

    t1.start()
    time.sleep(0.02)  # Let t1 acquire slot
    t2.start()  # t2 enters queue

    t1.join()
    t2.join()

    assert order == ["first", "second"]
    assert bh.active_calls == 0
    assert bh.queued_calls == 0


def test_bulkhead_queue_timeout_expired():
    bh = Bulkhead(max_concurrent=1, max_queued=1, queue_timeout=0.03)

    started_event = threading.Event()

    def long_task():
        started_event.set()
        time.sleep(0.1)

    t1 = threading.Thread(target=lambda: bh.execute(long_task))
    t1.start()
    started_event.wait()

    # Second call queues, but queue_timeout (0.03s) expires before long_task (0.1s) finishes
    with pytest.raises(BulkheadFullError):
        bh.execute(lambda: "never_runs")

    t1.join()


def test_bulkhead_context_manager():
    bh = Bulkhead(max_concurrent=2)
    with bh:
        assert bh.active_calls == 1
    assert bh.active_calls == 0


def test_bulkhead_decorator():
    bh = Bulkhead(max_concurrent=2)

    @bh
    def compute(val):
        return val * 10

    assert compute(5) == 50
    assert hasattr(compute, "bulkhead")
