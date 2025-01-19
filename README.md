# FrameLatch

A synthesizable framed byte-stream receiver that releases payloads only after CRC validation.

Protocol: `A5 | length (1–16) | payload | CRC-8`. CRC covers length and payload using polynomial `0x07`, initial value `0x00`, no reflection or final XOR.

The project will include RTL, an independent Python reference, cocotb verification, a malformed-frame corpus, demonstration waveforms, and a verification report.
