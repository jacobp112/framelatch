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


@cocotb.test()
async def crc_rejection(dut):
    b = Bench(dut)
    await b.start()
    dut.scenario.value = 2
    frame = bytearray(encode(b"bad"))
    frame[-1] ^= 1
    await b.send(frame)
    await b.drain()
    assert b.accepted == []
    assert b.model.counts["crc_errors"] == 1
    await b.send(encode(b"recovered"))
    await b.drain()
    assert b.accepted == [b"recovered"]
    b.save("crc_rejection")


@cocotb.test()
async def incomplete_frame(dut):
    b = Bench(dut)
    await b.start()
    dut.scenario.value = 3
    await b.send(bytes.fromhex("a5041122"))
    await b.cycle(abort=True, valid=True, data=0xA5)
    await b.cycle(abort=True)
    assert b.model.counts["incomplete_frames"] == 1
    await b.send(encode(b"next"))
    await b.drain()
    assert b.accepted == [b"next"]
    b.save("incomplete_frame")


@cocotb.test()
async def output_backpressure(dut):
    b = Bench(dut)
    await b.start()
    dut.scenario.value = 4
    first, second = b"held", b"released"
    await b.send(encode(first)[:-1])
    await b.cycle(data=encode(first)[-1], valid=True, ready=False)
    for _ in range(200):
        assert not await b.cycle(data=0xA5, valid=True, ready=False)
    # Abort cancels the stalled source byte, not the validated output.
    await b.cycle(abort=True, ready=False)
    await b.cycle(abort=True, ready=True)
    assert b.accepted == [first]
    await b.send(encode(second))
    await b.drain()
    assert b.accepted == [first, second]
    assert b.model.counts["incomplete_frames"] == 0
    b.save("output_backpressure")


@cocotb.test()
async def malformed_corpus(dut):
    b = Bench(dut)
    await b.start()
    corpus = json.loads((ROOT / "corpus" / "frames.json").read_text())
    for index, case in enumerate(corpus["cases"]):
        await b.cycle(reset=True)
        b.accepted.clear()
        dut.scenario.value = index + 10
        for action in case["actions"]:
            if "bytes" in action:
                await b.send(bytes.fromhex(action["bytes"]))
            elif "reset" in action:
                await b.cycle(reset=True, abort=True, valid=True, data=0xA5)
                b.accepted.clear()
            elif "abort" in action:
                await b.cycle(abort=True)
            elif "stall" in action:
                for _ in range(action["stall"]):
                    await b.cycle(ready=False)
        await b.drain()
        assert [p.hex() for p in b.accepted] == case["accepted"], case["name"]
        assert b.model.counts == case["counters"], case["name"]
    b.save("malformed_corpus")


@cocotb.test()
async def all_lengths_and_crc_faults(dut):
    b = Bench(dut)
    await b.start()
    expected = []
    for length in range(1, 17):
        payload = bytes((i * 37 + length) & 255 for i in range(length))
        frame = encode(payload)
        await b.send(frame)
        expected.append(payload)
        for bit in range(8):
            corrupt = frame[:-1] + bytes([frame[-1] ^ (1 << bit)])
            await b.send(corrupt)
        for byte_index in range(2, 2 + length):
            corrupt = bytearray(frame)
            corrupt[byte_index] ^= 1
            await b.send(corrupt)
    await b.drain()
    assert b.accepted == expected
    assert b.model.counts["crc_errors"] == 128 + sum(range(1, 17))
    b.save("all_lengths_and_crc_faults")


@cocotb.test()
async def every_invalid_length(dut):
    b = Bench(dut)
    await b.start()
    for length in [0, *range(17, 256)]:
        await b.send(bytes([0xA5, length]))
    await b.drain()
    assert b.accepted == []
    assert b.model.counts["invalid_lengths"] == 240
    assert b.model.counts["discarded_bytes"] == 0
    b.save("every_invalid_length")


@cocotb.test()
async def all_input_byte_values(dut):
    b = Bench(dut)
    await b.start()
    expected = []
    for byte in range(256):
        payload = bytes([byte])
        await b.send(encode(payload))
        expected.append(payload)
    await b.drain()
    assert b.accepted == expected
    assert b.model.counts["valid_frames"] == 256
    b.save("all_input_byte_values")


@cocotb.test()
async def reset_and_abort_priority(dut):
    b = Bench(dut)
    await b.start()
    frame = encode(b"stage")
    # Before sync, after sync, after length, every payload byte, before CRC,
    # and with a validated output pending. Reset must cancel everything.
    for prefix in range(len(frame) + 1):
        await b.send(frame[:prefix])
        await b.cycle(reset=True, abort=True, valid=True, data=0xA5, ready=True)
        assert b.model.counts == dict.fromkeys(COUNTERS, 0)
        await b.drain()
    for prefix in range(1, len(frame)):
        await b.send(frame[:prefix])
        previous = b.model.counts["incomplete_frames"]
        await b.cycle(abort=True, valid=True, data=0x11)
        await b.cycle(abort=True)
        assert b.model.counts["incomplete_frames"] == previous + 1
    await b.send(encode(b"alive"))
    await b.drain()
    assert b.accepted == [b"alive"]
    b.save("reset_and_abort_priority")


@cocotb.test()
async def counter_saturation(dut):
    b = Bench(dut)
    await b.start()
    # Deposit near-overflow values rather than simulate 2^32 events.
    for counter in COUNTERS:
        getattr(dut.uut, counter).value = MAX_COUNT - 1
        b.model.counts[counter] = MAX_COUNT - 1
    await Timer(1, unit="ns")
    for _ in range(2):
        await b.send(b"\x11")
        await b.send(b"\xa5\x00")
        frame = encode(b"\x00")
        await b.send(frame[:-1] + bytes([frame[-1] ^ 1]))
        await b.send(b"\xa5")
        await b.cycle(abort=True)
        await b.send(encode(b"ok"))
    await b.drain()
    assert all(value == MAX_COUNT for value in b.model.counts.values())
    await b.cycle(reset=True)
    b.save("counter_saturation")


@cocotb.test()
async def randomized_streams(dut):
    b = Bench(dut)
    await b.start()
    rng = random.Random(int(os.environ.get("FRAMELATCH_SEED", "1931")))
    for iteration in range(500):
        kind = rng.randrange(7)
        payload = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 17)))
        frame = encode(payload)
        if kind == 0:
            await b.send(bytes([rng.choice([0, 1, 0xFF, 0xA4])]), rng)
        elif kind == 1:
            await b.send(bytes([0xA5, rng.choice([0, 17, 0xA5, 255])]), rng)
        elif kind == 2:
            await b.send(frame[:-1] + bytes([frame[-1] ^ rng.randrange(1, 256)]), rng)
        elif kind == 3:
            await b.send(frame[:rng.randrange(1, len(frame))], rng)
            await b.cycle(abort=True, ready=rng.random() < 0.5)
        elif kind == 4:
            await b.send(frame[:rng.randrange(len(frame) + 1)], rng)
            await b.cycle(reset=True, abort=True, ready=rng.random() < 0.5)
        else:
            await b.send(frame, rng)
    await b.drain()
    b.save("randomized_streams")


@cocotb.test()
async def demo(dut):
    b = Bench(dut)
    await b.start()
    dut.scenario.value = 100
    await b.send(bytes.fromhex("001122"))
    await b.send(encode(b"FrameLatch"))
    await b.send(bytes.fromhex("a500a511"))
    bad = encode(b"reject")
    await b.send(bad[:-1] + bytes([bad[-1] ^ 1]))
    await b.send(bytes.fromhex("a5041122"))
    await b.cycle(abort=True)
    last = encode(bytes.fromhex("a500ff"))
    await b.send(last[:-1])
    await b.cycle(data=last[-1], valid=True, ready=False)
    for _ in range(25):
        await b.cycle(ready=False)
    await b.drain()
    assert b.accepted == [b"FrameLatch", bytes.fromhex("a500ff")]
    assert b.model.counts == dict(zip(COUNTERS, [2, 1, 2, 1, 3]))
    b.save("demo")
