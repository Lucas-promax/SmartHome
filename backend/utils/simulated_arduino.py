"""In-process serial replacement; emits the stock firmware's text protocol."""
import queue
import time


class SimulatedArduino:
    def __init__(self, *args, **kwargs):
        self.queue = queue.Queue()
        self.level = 2
        self.light = False
        self.fan = False
        self.auto_enabled = True
        self.door = False
        self.garage = False
        self.last_sample = 0

    def snapshot(self):
        level = [8, 25, 70, 140, 255][self.level] if self.light else 0
        return (f'[Light] On: {str(self.light).lower()} Brightness: {level}\n'
                f'[Fan] Running: {str(self.fan).lower()} Auto: {str(self.auto_enabled).lower()} AutoOnAt: 25.0C\n'
                f'[Door] Main: {"OPEN" if self.door else "CLOSED"} Garage: {"OPEN" if self.garage else "CLOSED"}\n').encode()

    def write(self, data):
        for c in data.decode('ascii'):
            if c in 'lABC':
                self.light = True
                self.level = {'l': 2, 'A': 0, 'B': 2, 'C': 4}[c]
            elif c == 'L': self.light = False
            elif c in '+-':
                self.light = True
                self.level = max(0, min(4, self.level + (1 if c == '+' else -1)))
            elif c in 'vV': self.auto_enabled = c == 'v'
            elif c in 'fF': self.fan = c == 'f'
            elif c in 'dD': self.door = c == 'd'
            elif c in 'gG': self.garage = c == 'g'
            self.queue.put(self.snapshot())
        return len(data)

    def read(self, size):
        if time.monotonic() - self.last_sample >= 2:
            self.last_sample = time.monotonic()
            if self.auto_enabled: self.fan = False
            return b'Temp: 25.0 Humi: 50.0 Light: BRIGHT\n' + self.snapshot()
        try:
            return self.queue.get(timeout=.1)
        except queue.Empty:
            return b''

    def close(self):
        pass
