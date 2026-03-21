import time
from .lprint import lprint

class Sleeper:
    def __init__(self, tick, user=None):
        self._start = time.time_ns()
        self.tick = tick
        self.user=user
    
    def sleep(self):
        sleep_time = self.tick - (time.time_ns() - self._start)/1e9
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            buffer = f'warning: tick time out {sleep_time}s'
            if self.user is not None:
                buffer += f", caller is {self.user.__class__.__name__}"
            lprint(self, buffer)

    def sleep_half(self):
        sleep_time = self.tick - (time.time_ns() - self._start)/1e9
        half_sleep_time = sleep_time/2
        if sleep_time > 0:
            time.sleep(half_sleep_time)
        else:
            buffer = f'warning: tick time out {sleep_time}s'
            if self.user is not None:
                buffer += f", caller is {self.user.__class__.__name__}"
            lprint(self, buffer)