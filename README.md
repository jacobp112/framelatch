# FrameLatch

A synthesizable framed byte-stream receiver that releases payloads only after CRC validation.

Protocol: `A5 | length (1–16) | payload | CRC-8`. CRC covers length and payload using polynomial `0x07`, initial value `0x00`, no reflection or final XOR.

The receiver has a one-frame output buffer, ready/valid flow control, an
upstream abort input, and five saturating error/event counters. See
[the protocol specification](docs/PROTOCOL.md) for edge timing and counter rules.

The Python reference uses polynomial division over the complete message,
independent of the incremental CRC implementation in the RTL.

Run reference tests from this directory with Python 3.10 or newer:

```powershell
py -m unittest discover -s tests -v
```

With Icarus Verilog and Yosys on PATH:

```powershell
New-Item -ItemType Directory -Force build | Out-Null
iverilog -g2012 -Wall -s framelatch -o build/compile.vvp rtl/framelatch.sv
yosys -Q -T -l build/synthesis.log -p 'read_verilog -sv rtl/framelatch.sv; hierarchy -check -top framelatch; synth -top framelatch; check -assert; stat'
```

Cocotb verification, saved malformed cases, a simulation demo, selected
waveforms, and the final verification report are the next project checkpoint.
