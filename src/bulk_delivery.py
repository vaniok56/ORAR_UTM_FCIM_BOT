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
from zoneinfo import ZoneInfo

BULK_SEND_RATE = 25.0
BULK_MAX_IN_FLIGHT = 6
TELEGRAM_BROADCAST_WARNING_RATE = 30.0
LOCAL_TZ = ZoneInfo('Europe/Chisinau')

batch_metrics = ContextVar('batch_metrics', default=None)


def format_local_time(value):
    if value is None:
        return 'n/a'
    local = value.astimezone(LOCAL_TZ)
    return f'{local:%H:%M:%S}.{local.microsecond // 1000:03d}'


def validate_settings(log):
    if not math.isfinite(BULK_SEND_RATE) or BULK_SEND_RATE <= 0:
        raise ValueError('BULK_SEND_RATE must be finite and positive')
    if not isinstance(BULK_MAX_IN_FLIGHT, int) or isinstance(BULK_MAX_IN_FLIGHT, bool) or BULK_MAX_IN_FLIGHT < 1:
        raise ValueError('BULK_MAX_IN_FLIGHT must be a positive integer')
    if BULK_SEND_RATE > TELEGRAM_BROADCAST_WARNING_RATE:
        log(f'Bulk send rate {BULK_SEND_RATE}/s exceeds Telegram approximate free broadcast guidance; flood waits may occur', 'warning')


def estimated_batch_seconds(recipient_count):
    return max(0, recipient_count) / BULK_SEND_RATE


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
        started = asyncio.get_running_loop().time()
        if guard is not None and not guard():
            return None, None, None
        now = asyncio.get_running_loop().time()
        next_start = started + 1 / BULK_SEND_RATE
        if next_start < now:
            next_start = now + 1 / BULK_SEND_RATE
        self.next_start = next_start
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
        self.notify()


async def run_bulk(items, send, kind, log, *, success_kind=None, estimate=None):
    metrics = {'attempts': 0, 'first': None, 'first_wall': None, 'flood_waits': [],
               'sent': 0, 'skipped': 0, 'failed': 0}
    iterator = iter(items)
    token = batch_metrics.set(metrics)

    async def worker():
        for item in iterator:
            try:
                result = await send(item)
            except Exception as error:
                log(f'{kind} recipient failed: {type(error).__name__}', 'error')
                result = None
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
        completed_mono = asyncio.get_running_loop().time()
        start_wall = metrics['first_wall']
        elapsed = completed_mono - metrics['first'] if metrics['first'] is not None else 0.0
        completed_wall = (start_wall + datetime.timedelta(seconds=elapsed)
                          if start_wall is not None else datetime.datetime.now(datetime.timezone.utc))
        rate = metrics['attempts'] / elapsed if elapsed else 0.0
        delta = ''
        if estimate is not None and start_wall is not None:
            delta = f" ({elapsed - estimate:+.2f})"
        waits = metrics['flood_waits']
        flood = str(len(waits))
        if waits:
            flood += f" ({sum(waits):.1f}s)"
        batch_kind = success_kind or kind
        log(f"{batch_kind} batch | {len(items)} recipients | start {format_local_time(start_wall)} | "
            f"end {format_local_time(completed_wall)} | elapsed {elapsed:.2f}s{delta} | rate {rate:.2f}/s", 'info')
        log(f"{batch_kind} results | sent {metrics['sent']} | skipped {metrics['skipped']} | "
            f"failed {metrics['failed']} | flood {flood}", 'info')
    return metrics
