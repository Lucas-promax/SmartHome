"""LiveOV7670 ExampleUart protocol (version 0x10), ported from ImageCapture.

Unlike the Java viewer's damaged-pixel repair, discard incomplete/corrupt frames
and synchronize at the next valid frame header. Partial rows are preview-only;
feed() still returns exclusively complete, validated pictures.
"""
import numpy as np


class OV7670Parser:
    def __init__(self):
        self.buffer = bytearray()
        self.shape = None
        self.pixels = bytearray()
        self.frame_number = 0

    def feed(self, data: bytes) -> list:
        self.buffer.extend(data)
        frames = []
        while self.buffer:
            if self.buffer[0] == 0:
                if len(self.buffer) < 2:
                    break
                length = self.buffer[1]
                if len(self.buffer) < length + 3:
                    break
                packet = bytes(self.buffer[2:length + 3])
                del self.buffer[:length + 3]
                checksum = 0
                for b in packet[:-1]:
                    checksum ^= b
                if not length or checksum != packet[-1] or packet[0] & 0xF0 != 0x10:
                    self.shape = None
                    self.pixels.clear()
                    continue
                if packet[0] == 0x11:
                    self.shape = None
                    self.pixels.clear()
                    if length == 4:
                        w = packet[1] | ((packet[3] & 3) << 8)
                        h = packet[2] | ((packet[3] & 12) << 6)
                        fmt = packet[3] >> 4
                        if 1 <= w <= 640 and 1 <= h <= 480 and fmt in (1, 2):
                            self.shape = (h, w, fmt)
                            self.frame_number += 1
                elif packet[0] != 0x13:  # Debug commands do not contain pixels.
                    self.shape = None
                    self.pixels.clear()
                continue
            end = self.buffer.find(0)
            if end < 0:
                end = len(self.buffer)
            chunk = self.buffer[:end]
            del self.buffer[:end]
            if self.shape is None:
                continue
            self.pixels.extend(chunk)
            h, w, fmt = self.shape
            expected = h * w * (2 if fmt == 1 else 1)
            if len(self.pixels) >= expected:
                if len(self.pixels) == expected:
                    frame = self._decode(h, w, fmt)
                    if frame is not None:
                        frames.append(frame)
                self.shape = None
                self.pixels.clear()
        return frames

    def preview(self):
        """Return valid complete rows on a black canvas, never a capture frame."""
        if self.shape is None:
            return None
        h, w, fmt = self.shape
        stride = w * (2 if fmt == 1 else 1)
        rows = min(h, len(self.pixels) // stride)
        if not rows:
            return None
        image = self._decode(rows, w, fmt, self.pixels[:rows * stride])
        if image is None:
            return None
        canvas = np.zeros((h, w, 3) if fmt == 1 else (h, w), dtype=np.uint8)
        canvas[:rows] = image
        return canvas, rows, h

    def _decode(self, h, w, fmt, pixels=None):
        data = np.frombuffer(self.pixels if pixels is None else pixels, dtype=np.uint8)
        if fmt == 2:
            if np.any(data[::2] & 1) or np.any((data[1::2] & 1) != 1):
                return None
            return data.reshape(h, w).copy()
        high, low = data[::2], data[1::2]
        high_valid = ((high & 0x20) != 0) != ((high & 0x08) != 0)
        low_valid = ((low & 0x08) != 0) == ((low & 0x20) != 0)
        if not np.all(high_valid & low_valid):
            return None
        raw = (high.astype(np.uint16) << 8) | low
        # OpenCV expects BGR. Match Java's RGB565 bit expansion.
        return np.stack(((raw << 3) & 0xF8, (raw >> 3) & 0xFC,
                         (raw >> 8) & 0xF8), axis=-1).astype(np.uint8).reshape(h, w, 3)
