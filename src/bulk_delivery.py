"""Shared pacing and batch execution for Telegram messages.

Normal replies take priority; bulk sends share the same rate and a concurrency
limit. Explicit flood waits pause the gate. Automatic batch estimates use the
settings below to center delivery around the requested target time.
"""

import asyncio
import datetime
import math
from collections import deque
from contextvars import ContextVar

BULK_SEND_RATE = 25.0
BULK_MAX_IN_FLIGHT = 6
BULK_EXTRA_SECONDS_PER_RECIPIENT = 0.008
TELEGRAM_BROADCAST_WARNING_RATE = 30.0

batch_metrics = ContextVar('batch_metrics', default=None)
recipient_retried = ContextVar('recipient_retried', default=False)


def validate_settings(log):
    if not math.isfinite(BULK_SEND_RATE) or BULK_SEND_RATE <= 0:
        raise ValueError('BULK_SEND_RATE must be finite and positive')
    if not isinstance(BULK_MAX_IN_FLIGHT, int) or isinstance(BULK_MAX_IN_FLIGHT, bool) or BULK_MAX_IN_FLIGHT < 1:
        raise ValueError('BULK_MAX_IN_FLIGHT must be a positive integer')
    if not math.isfinite(BULK_EXTRA_SECONDS_PER_RECIPIENT) or BULK_EXTRA_SECONDS_PER_RECIPIENT < 0:
        raise ValueError('BULK_EXTRA_SECONDS_PER_RECIPIENT must be finite and nonnegative')
    if BULK_SEND_RATE > TELEGRAM_BROADCAST_WARNING_RATE:
        log(f'Bulk send rate {BULK_SEND_RATE}/s exceeds Telegram approximate free broadcast guidance; flood waits may occur', 'warning')


def estimated_batch_seconds(recipient_count):
    return max(0, recipient_count) * (1 / BULK_SEND_RATE + BULK_EXTRA_SECONDS_PER_RECIPIENT)


def centered_start(target, recipient_count):
    if target.tzinfo is None or target.utcoffset() is None:
        raise ValueError('target must be timezone-aware')
    start = target.astimezone(datetime.timezone.utc) - datetime.timedelta(seconds=estimated_batch_seconds(recipient_count) / 2)
    return start.astimezone(target.tzinfo)


class SendGate:
    def __init__(self):
        self.next_start = 0.0
        self.paused_until = 0.0
        self.high = deque()
        self.low = deque()
        self.changed = asyncio.Event()
        self.bulk_slots = asyncio.Semaphore(BULK_MAX_IN_FLIGHT)

    def notify(self):
        self.changed.set()
        self.changed = asyncio.Event()

    def register(self, bulk, *, front=False):
        token = object()
        queue = self.low if bulk else self.high
        (queue.appendleft if front else queue.append)(token)
        self.notify()
        return token

    def remove(self, token, bulk):
        (self.low if bulk else self.high).remove(token)
        self.notify()

    def ready(self, token, bulk):
        queue = self.low if bulk else self.high
        now = asyncio.get_running_loop().time()
        delay = max(self.next_start, self.paused_until) - now
        if queue[0] is not token or (bulk and self.high):
            return False, None, self.changed
        if delay > 0:
            return False, delay, self.changed
        return True, None, self.changed

    def try_start(self, token, bulk, guard=None):
        # Admission and flood-pause updates are synchronous on the event loop.
        ready, delay, event = self.ready(token, bulk)
        if not ready:
            return False, delay, event
        if guard is not None and not guard():
            return None, None, None
        now = asyncio.get_running_loop().time()
        self.next_start = now + 1 / BULK_SEND_RATE
        self.remove(token, bulk)
        metrics = batch_metrics.get()
        if metrics is not None:
            metrics['attempts'] += 1
            if metrics['first'] is None:
                metrics['first'] = now
                metrics['first_wall'] = datetime.datetime.now(datetime.timezone.utc)
        return True, None, None

    async def wait(self, event, delay):
        try:
            await asyncio.wait_for(event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    def pause(self, seconds):
        self.paused_until = max(self.paused_until, asyncio.get_running_loop().time() + seconds)
        metrics = batch_metrics.get()
        if metrics is not None:
            metrics['flood_waits'].append(seconds)
            if not recipient_retried.get():
                metrics['retried'] += 1
                recipient_retried.set(True)
        self.notify()


async def run_bulk(items, send, kind, log, *, target=None, start=None):
    metrics = {'attempts': 0, 'first': None, 'first_wall': None, 'flood_waits': [],
               'sent': 0, 'skipped': 0, 'failed': 0, 'retried': 0}
    iterator = iter(items)
    token = batch_metrics.set(metrics)

    async def worker():
        for item in iterator:
            retry_token = recipient_retried.set(False)
            try:
                try:
                    result = await send(item)
                except Exception as error:
                    log(f'{kind} recipient failed: {type(error).__name__}', 'error')
                    result = None
            finally:
                recipient_retried.reset(retry_token)
            metrics['sent' if result is True else 'skipped' if result is False else 'failed'] += 1

    tasks = [asyncio.create_task(worker()) for _ in range(min(BULK_MAX_IN_FLIGHT, len(items)))]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        batch_metrics.reset(token)
        elapsed = (asyncio.get_running_loop().time() - metrics['first']) if metrics['first'] is not None else 0.0
        log(f"{kind} batch: target={target}; start={start}; estimated={estimated_batch_seconds(len(items)):.2f}s; "
            f"prepared={len(items)}; first={metrics['first_wall']}; completed={datetime.datetime.now(datetime.timezone.utc)}; elapsed={elapsed:.2f}s; "
            f"sent={metrics['sent']}; skipped={metrics['skipped']}; failed={metrics['failed']}; "
            f"attempts={metrics['attempts']}; starts/s={metrics['attempts'] / elapsed if elapsed else 0:.2f}; "
            f"sent/s={metrics['sent'] / elapsed if elapsed else 0:.2f}; flood_retried={metrics['retried']}; "
            f"flood_waits={metrics['flood_waits']}", 'info')
    return metrics
