# Protocol and interface

Frame bytes are `A5 length payload CRC`. Length is 1 through 16 inclusive.
CRC-8 uses polynomial `0x07`, initial value zero, no reflection, no final XOR,
and covers the length byte followed by the payload. `123456789` checks to `F4`.
Sync is excluded. Within a payload, `A5` is ordinary data.

The receiver consumes bytes on rising clock edges with `in_valid && in_ready`.
After accepting sync it expects length, exactly that many payload bytes, then
CRC. Invalid length and CRC bytes are consumed, never reused as sync, and
return the parser to sync search. In search, each accepted non-sync byte is
discarded. A payload is published only on an accepted matching CRC byte.

| Signal | Width | Meaning |
| --- | ---: | --- |
| `clk` | 1 | Rising-edge clock |
| `rst` | 1 | Active-high synchronous reset |
| `in_data` | 8 | Input byte |
| `in_valid`, `in_ready` | 1 each | Input transfer handshake |
| `in_abort` | 1 | Upstream timeout/truncation indication |
| `out_payload` | 128 | Byte 0 in bits 7:0; unused high bytes zero |
| `out_length` | 5 | Accepted payload length |
| `out_valid`, `out_ready` | 1 each | Output transfer handshake |
| Counter ports below | 32 each | Saturating event totals |

One completed payload is buffered. While `out_valid && !out_ready`, all
input is stalled and output payload, length, and valid remain unchanged.
When the sink is ready, it may consume that output and the receiver may
accept an input byte on the same edge. The output registers retain their
last values when valid is cleared; reset zeroes them. Values with valid low
do not represent a new output.

Reset has highest priority: it discards parser and pending output, clears
all counters and internal assembly, and suppresses input transfer.
Abort suppresses input transfer, clears parser assembly, and counts one
incomplete frame if sync had been accepted and CRC is still outstanding.
An idle abort has no counted effect; holding abort high counts a partial
frame once. Abort leaves the completed output alone, including during a
stall. A sink handshake remains possible during abort when reset is low.
There is no internal timeout: the upstream must assert abort on truncation.

| Counter | Increment event (on the rising edge) |
| --- | --- |
| `valid_frames` | Accepted CRC matches length + payload; counts publication, even if the sink stalls |
| `crc_errors` | Accepted CRC mismatches the computed CRC |
| `invalid_lengths` | Accepted length is zero or greater than 16 |
| `incomplete_frames` | Abort while waiting for length, payload, or CRC |
| `discarded_bytes` | Accepted non-`A5` byte while searching for sync |

Each increment saturates at `0xFFFFFFFF`. Rejected length/CRC bytes, bytes
inside frames, stalled input, and abort/reset edges are never counted as
discarded search bytes. Reset is not an incomplete-frame event.

The source must keep valid and data stable until its byte transfers, except
when it cancels the byte with reset or abort. The sink may change ready
between edges. No clocks, baud rates, board pins, or physical link are assumed.
