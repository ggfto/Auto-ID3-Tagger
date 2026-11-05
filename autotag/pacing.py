"""Spaces out requests to a service whose rate limit is shared by all threads."""
import threading
import time


class Pacer:
    """
    Gives each request a time slot, adapting to the limit the service enforces.

    The limit is not published, so the interval grows when the service refuses
    requests and shrinks slowly while they succeed.
    """

    def __init__(self, start_interval, min_interval, max_interval, cooldown, clock=time.monotonic, sleep=time.sleep):
        self.interval = start_interval
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.cooldown = cooldown
        self.clock = clock
        self.sleep = sleep
        self.lock = threading.Lock()
        self.next_slot = 0.0
        self.cooling_until = 0.0

    def wait(self):
        """Blocks the calling thread until its slot."""
        with self.lock:
            now = self.clock()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        if slot > now:
            self.sleep(slot - now)

    def succeeded(self):
        with self.lock:
            self.interval = max(self.min_interval, self.interval * 0.9)

    def limited(self):
        """Slows every thread down. Refusals during a cooldown belong to the same event."""
        with self.lock:
            now = self.clock()
            if now < self.cooling_until:
                return
            self.interval = min(self.max_interval, self.interval * 1.25)
            self.cooling_until = now + self.cooldown
            self.next_slot = max(self.next_slot, self.cooling_until)
