"""Decode saved FST traces and verify their output transactions and counters."""

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COUNTERS = ("valid_frames", "crc_errors", "invalid_lengths", "incomplete_frames", "discarded_bytes")
TRACES = ("successful_frame", "crc_rejection", "incomplete_frame", "output_backpressure")


def samples(text):
    """Yield timestamped snapshots of top-level signals from fst2vcd output."""
    scope, codes, values = [], {}, {}
    timestamp = 0
    started = False
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        if words[0] == "$scope":
            scope.append(words[2])
        elif words[0] == "$upscope":
            scope.pop()
        elif words[0] == "$var" and scope == ["framelatch_tb"]:
            codes[words[3]] = words[4]
        elif line.startswith("#"):
            if started:
                yield timestamp, values.copy()
            timestamp = int(line[1:])
            started = True
        elif started and line[0] in "01xz":
            if line[1:] in codes:
                values[codes[line[1:]]] = None if line[0] in "xz" else int(line[0])
        elif started and line[0] == "b":
            bits, code = words[0][1:], words[1]
            if code in codes:
                values[codes[code]] = None if any(bit in bits for bit in "xz") else int(bits, 2)
    if started:
        yield timestamp, values.copy()


def main():
    for name in TRACES:
        path = ROOT / "docs/waveforms" / f"{name}.fst"
        text = subprocess.check_output(["fst2vcd", str(path)], text=True)
        assert "$timescale\n\t1ps" in text.replace("\r", ""), "unexpected time unit"
        previous, transactions, stalls = None, [], 0
        for time_ps, current in samples(text):
            if previous and previous.get("clk") == 0 and current.get("clk") == 1:
                if not previous["rst"] and previous["out_valid"]:
                    if previous["out_ready"]:
                        length = previous["out_length"]
                        payload = previous["out_payload"].to_bytes(16, "little")
                        assert payload[length:] == bytes(16 - length)
                        transactions.append(payload[:length].hex())
                    else:
                        stalls += 1
                        assert current["out_valid"] == 1
                        assert current["out_payload"] == previous["out_payload"]
                        assert current["out_length"] == previous["out_length"]
            previous = current
        expected = json.loads(path.with_suffix(".json").read_text())
        assert transactions == expected["accepted_payloads"], path.name
        assert {name: current[name] for name in COUNTERS} == expected["counters"], path.name
        assert time_ps == expected["cycles"] * 10000, path.name
        print(f"{path.name}: {time_ps / 1000:g} ns, {len(transactions)} transfers, "
              f"{stalls} stalled output edges; counters match")


if __name__ == "__main__":
    main()
