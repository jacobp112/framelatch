"""Cycle scoreboard, adversarial streams, and named waveform scenarios."""

import json
import os
import random
from pathlib import Path

import cocotb
from cocotb.triggers import Timer

from framelatch.protocol import COUNTERS, MAX_COUNT, Receiver, encode

ROOT = Path(__file__).resolve().parents[1]


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.model = Receiver()
        self.accepted = []
        self.cycles = 0
        self.blocked_byte = None
        self.stalled_output = None

    async def cycle(self, data=0, valid=False, ready=True, abort=False, reset=False):
        d = self.dut
        d.clk.value = 0
        d.rst.value = int(reset)
        d.in_abort.value = int(abort)
        d.in_valid.value = int(valid)
        d.in_data.value = data
        d.out_ready.value = int(ready)
        await Timer(5, unit="ns")
        if self.blocked_byte is not None and not (reset or abort):
            assert valid and data == self.blocked_byte, "source broke ready/valid"
        expected_ready = self.model.ready(rst=reset, abort=abort, out_ready=ready)
        assert int(d.in_ready.value) == expected_ready, f"in_ready cycle {self.cycles}"
        if self.cycles:
            assert int(d.out_valid.value) == (self.model.pending is not None)
        if self.stalled_output is not None:
            assert (int(d.out_payload.value), int(d.out_length.value),
                    int(d.out_valid.value)) == self.stalled_output
        if self.model.pending is not None and ready and not reset:
            actual = int(d.out_payload.value).to_bytes(16, "little")
            length = int(d.out_length.value)
            assert actual[:length] == self.model.pending, "invalid or reordered output"
            assert actual[length:] == bytes(16 - length), "unused bytes not zero"
            self.accepted.append(actual[:length])
        transferred = self.model.step(data=data, valid=valid, out_ready=ready,
                                      abort=abort, rst=reset)
        if transferred is not None:
            assert self.accepted[-1] == transferred
        self.blocked_byte = data if valid and not expected_ready and not (reset or abort) else None
        self.stalled_output = None
        d.clk.value = 1
        await Timer(5, unit="ns")
        self.cycles += 1
        assert int(d.out_valid.value) == (self.model.pending is not None), "unexpected output publication"
        assert int(d.out_payload.value) == self.model.output_payload, "payload changed without validation"
        assert int(d.out_length.value) == self.model.output_length
        for counter in COUNTERS:
            assert int(getattr(d, counter).value) == self.model.counts[counter], counter
        if int(d.out_valid.value) and not ready and not reset:
            self.stalled_output = (int(d.out_payload.value), int(d.out_length.value), 1)
        return bool(valid and expected_ready)

    async def start(self):
        await self.cycle(reset=True)
        await self.cycle()

    async def send(self, stream, rng=None):
        for byte in stream:
            if rng:
                for _ in range(rng.randrange(3)):
                    await self.cycle(ready=rng.random() < 0.6)
            for attempt in range(1000):
                ready = True if rng is None else rng.random() < 0.6
                if await self.cycle(data=byte, valid=True, ready=ready):
                    break
            else:
                raise AssertionError("input deadlock")

    async def drain(self):
        for _ in range(3):
            await self.cycle()
        assert self.model.pending is None

    def save(self, name):
        output = Path(os.environ.get("FRAMELATCH_RESULTS", "build"))
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{name}.json").write_text(json.dumps({
            "accepted_payloads": [p.hex() for p in self.accepted],
            "counters": self.model.counts, "cycles": self.cycles,
        }, indent=2) + "\n")


@cocotb.test()
async def successful_frame(dut):
    b = Bench(dut)
    await b.start()
    dut.scenario.value = 1
    payload = bytes.fromhex("10a500ff")
    await b.send(encode(payload))
    await b.drain()
    assert b.accepted == [payload]
    assert b.model.counts["valid_frames"] == 1
    b.save("successful_frame")
