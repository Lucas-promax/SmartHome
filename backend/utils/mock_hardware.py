import math
import random
import time


def read_environment() -> dict[str, float]:
    """Generate stable-looking demo temperature and humidity values."""
    tick = time.time() / 60
    temperature = 24.0 + math.sin(tick) * 1.8 + random.uniform(-0.2, 0.2)
    humidity = 48.0 + math.cos(tick / 2) * 8.0 + random.uniform(-1.0, 1.0)
    return {"temperature": round(temperature, 1), "humidity": round(humidity, 1)}
