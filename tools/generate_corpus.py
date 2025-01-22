"""Regenerate reviewable directed cases with explicit expected outcomes."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framelatch.protocol import COUNTERS, encode


def main():
    cases = []

    def case(name, actions, accepted=(), **counts):
        cases.append({"name": name, "actions": actions,
                      "accepted": [p.hex() for p in accepted],
                      "counters": {key: counts.get(key, 0) for key in COUNTERS}})

    def stream(data):
        return {"bytes": data.hex()}

    good = encode(b"next")
    bad = encode(b"bad")
    case("bad_crc_then_recovery", [stream(bad[:-1] + bytes([bad[-1] ^ 1]) + good)],
         [b"next"], valid_frames=1, crc_errors=1)
    for length in (0, 17, 0xA5, 255):
        case(f"invalid_length_{length}", [stream(bytes([0xA5, length]) + good)],
             [b"next"], valid_frames=1, invalid_lengths=1)
    case("truncated_header", [stream(b"\xa5"), {"abort": True}], incomplete_frames=1)
    case("truncated_payload", [stream(bytes.fromhex("a5041122")), {"abort": True}],
         incomplete_frames=1)
    case("missing_crc", [stream(encode(b"x")[:-1]), {"abort": True}], incomplete_frames=1)
    payload = bytes.fromhex("a500a5ff")
    case("sync_inside_payload", [stream(encode(payload))], [payload], valid_frames=1)
    case("consecutive_frames", [stream(encode(b"one") + encode(b"two"))],
         [b"one", b"two"], valid_frames=2)
    frame = encode(b"stage")
    for name, prefix in (("search", 0), ("length", 1), ("payload_start", 2),
                         ("payload_middle", 4), ("crc", len(frame)-1),
                         ("pending_output", len(frame))):
        case(f"reset_{name}", [stream(frame[:prefix]), {"reset": True}, stream(good)],
             [b"next"], valid_frames=1)
    destination = ROOT / "corpus" / "frames.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps({"format": 1, "cases": cases}, indent=2) + "\n")
    print(f"Wrote {len(cases)} cases to {destination}")


if __name__ == "__main__":
    main()
