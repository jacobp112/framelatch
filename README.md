# FrameLatch

A synthesizable framed byte-stream receiver that releases payloads only after CRC validation.

Protocol: `A5 | length (1–16) | payload | CRC-8`. CRC covers length and payload using polynomial `0x07`, initial value `0x00`, no reflection or final XOR.

The receiver has a one-frame output buffer, ready/valid flow control, an
upstream abort input, and five saturating error/event counters. See
[the protocol specification](docs/PROTOCOL.md) for edge timing and counter rules.

## Setup

Python 3.10 or newer and Icarus Verilog are required for simulation. Yosys
provides the generic synthesis check. No board or physical byte source is
needed: cocotb drives bytes and sink readiness directly.

On Windows, install an OSS CAD Suite and use its PowerShell environment.
Replace the suite path below with your installation directory. Use native
Python for the virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$cadSuite = 'C:\tools\oss-cad-suite'
. "$cadSuite\environment.ps1"
.\.venv\Scripts\python.exe tools/run.py demo
```

On Linux, with Python, `python3-venv`, Icarus Verilog, and Yosys installed:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python tools/run.py demo
```

The demo generates valid and malformed frames, runs the RTL, and prints:

```text
Accepted payloads:
  4672616d654c61746368  b'FrameLatch'
  a500ff  b'\xa5\x00\xff'
Error/event counters: {"crc_errors": 1, "discarded_bytes": 3, "incomplete_frames": 1, "invalid_lengths": 2, "valid_frames": 2}
```

Run commands from the repository root. In the commands below, Windows users
can replace `python` with `.\.venv\Scripts\python.exe`.

| Command | Result |
| --- | --- |
| `python tools/run.py unit` | Six Python reference/corpus tests; no simulator required |
| `python tools/run.py test` | Reference tests plus all 12 cocotb tests |
| `python tools/run.py test --seed 7` | Reproducible alternative randomized stream |
| `python tools/run.py demo` | Simulated frames, accepted payloads, final counters |
| `python tools/run.py waves` | Four selected FST recordings and result JSON files |
| `python tools/run.py synth` | Icarus compile and Yosys synthesis/check |
| `python tools/run.py all` | Tests, demo, waveform generation, synthesis |
| `python tools/inspect_waveforms.py` | Check saved FST handshakes/counters with `fst2vcd` |

Each simulation writes JUnit XML, its FST recording, and test result JSON
under `build/`. The runner rejects failed, missing, or unexpectedly skipped
selected tests even when the simulator returns exit code zero.

Optional strict RTL lint on Linux:

```sh
verilator --lint-only --Wall --top-module framelatch rtl/framelatch.sv
```

On Windows OSS CAD Suite, invoke the native binary and set its include root:

```powershell
$env:VERILATOR_ROOT = "$cadSuite\share\verilator"
& "$cadSuite\bin\verilator_bin.exe" --lint-only --Wall --top-module framelatch rtl/framelatch.sv
```

## Files and verification

- `rtl/framelatch.sv`: synthesizable receiver with one completed-frame buffer.
- `framelatch/protocol.py`: encoder and cycle oracle. Its CRC uses polynomial
  division over the complete message, independent of the RTL's incremental CRC.
- `sim/`: cocotb driver/scoreboard and HDL output/reset assertions.
- `corpus/frames.json`: 23 named cases with explicit expected payloads/counters.
- `tests/`: standard CRC check, encoder bounds, 4,096 reference round trips,
  and corpus outcomes.
- [Selected waveforms](docs/waveforms/README.md): four small traces and a
  GTKWave signal preset.

The tests compare every cycle's readiness, output registers, valid bit, and
counters against the reference. They cover all valid lengths, all 240 invalid
lengths, all byte values, CRC faults, resets at every frame prefix, aborts,
back-to-back frames, source gaps, and sink stalls. Counter saturation is
tested by depositing near-overflow values in simulation.

To encode a frame independently:

```python
from framelatch import encode
frame = encode(b"hello")
```

Regenerate the directed corpus with `python tools/generate_corpus.py`, then
run `python tools/run.py test` to verify its explicit outcomes.
