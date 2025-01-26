# Selected traces

These small FST files are real Icarus simulation recordings, with a 10 ns
clock period and 1 ps timestamp resolution. Each JSON file records the
accepted payloads, final counters, and total cycles from the same run.

| Trace | Duration | What to inspect |
| --- | ---: | --- |
| `successful_frame.fst` | 120 ns | `10 A5 00 FF` is assembled; output valid appears only after matching CRC |
| `crc_rejection.fst` | 260 ns | CRC error increments for `bad`; only `recovered` transfers |
| `incomplete_frame.fst` | 180 ns | Abort drops a partial payload; repeated abort counts once; `next` transfers |
| `output_backpressure.fst` | 2250 ns | `held` stays valid during 200 stalled input cycles and an abort; `released` follows |

From the repository root, open a trace with the curated signal order:

```text
gtkwave docs/waveforms/output_backpressure.fst docs/waveforms/signals.gtkw
```

Zoom to fit the entire recording. State values are search=0, length=1,
payload=2, CRC=3. Hex output payloads place the earliest byte at the right
because payload byte 0 occupies bits 7:0. Signals can be unknown before the
first synchronous reset edge at 5 ns.

For a text view, `fst2vcd docs/waveforms/successful_frame.fst` writes VCD to
standard output. Verify all four saved files without a graphical viewer:

```text
python tools/inspect_waveforms.py
```

That command decodes the recordings, checks actual output handshakes and
zero-fill, verifies data stability on stalled output edges, and compares
recorded counters and durations with the companion JSON files. `fst2vcd`
is provided by GTKWave and the OSS CAD Suite.

Regenerate the selections with `python tools/run.py waves`. Other simulation
traces remain under ignored `build/`; only these four selections are tracked.
