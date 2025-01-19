"""Independent reference: polynomial division and whole-frame CRC checking.

The RTL uses a byte-at-a-time shift-register CRC. This oracle instead forms
the complete message polynomial and divides by x^8 + x^2 + x + 1.
"""

from dataclasses import dataclass, field

COUNTERS = ("valid_frames", "crc_errors", "invalid_lengths",
            "incomplete_frames", "discarded_bytes")
MAX_COUNT = (1 << 32) - 1


def crc8(data: bytes) -> int:
    remainder = int.from_bytes(data, "big") << 8
    while remainder.bit_length() > 8:
        remainder ^= 0x107 << (remainder.bit_length() - 9)
    return remainder


def encode(payload: bytes) -> bytes:
    payload = bytes(payload)
    if not 1 <= len(payload) <= 16:
        raise ValueError("payload length must be 1..16 bytes")
    body = bytes([len(payload)]) + payload
    return b"\xa5" + body + bytes([crc8(body)])


@dataclass
class Receiver:
    """Cycle oracle with one pending output; counters increment on acceptance.

    step() returns the output transferred at this edge. pending is the output
    visible after this edge. Reset cancels any transfer; abort cancels input
    only and leaves an independently accepted output transfer intact.
    """

    state: str = "search"
    length: int = 0
    payload: bytearray = field(default_factory=bytearray)
    pending: bytes | None = None
    output_payload: int = 0
    output_length: int = 0
    counts: dict = field(default_factory=lambda: dict.fromkeys(COUNTERS, 0))

    def ready(self, *, rst=False, abort=False, out_ready=False):
        return not (rst or abort) and (self.pending is None or out_ready)

    def bump(self, name):
        self.counts[name] = min(MAX_COUNT, self.counts[name] + 1)

    def clear_parser(self):
        self.state = "search"
        self.length = 0
        self.payload.clear()

    def step(self, *, data=0, valid=False, out_ready=False, abort=False, rst=False):
        if rst:
            self.clear_parser()
            self.pending = None
            self.output_payload = self.output_length = 0
            self.counts = dict.fromkeys(COUNTERS, 0)
            return None
        input_transfer = valid and self.ready(abort=abort, out_ready=out_ready)
        transferred = self.pending if out_ready else None
        if out_ready:
            self.pending = None
        if abort:
            if self.state != "search":
                self.bump("incomplete_frames")
            self.clear_parser()
        elif input_transfer:
            if not 0 <= data <= 255:
                raise ValueError("input byte must be 0..255")
            if self.state == "search":
                if data == 0xA5:
                    self.clear_parser()
                    self.state = "length"
                else:
                    self.bump("discarded_bytes")
            elif self.state == "length":
                if not 1 <= data <= 16:
                    self.bump("invalid_lengths")
                    self.clear_parser()
                else:
                    self.length = data
                    self.state = "payload"
            elif self.state == "payload":
                self.payload.append(data)
                if len(self.payload) == self.length:
                    self.state = "crc"
            else:
                if data == crc8(bytes([self.length]) + self.payload):
                    self.pending = bytes(self.payload)
                    self.output_payload = int.from_bytes(self.pending, "little")
                    self.output_length = self.length
                    self.bump("valid_frames")
                else:
                    self.bump("crc_errors")
                self.clear_parser()
        return transferred
