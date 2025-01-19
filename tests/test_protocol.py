import unittest

from framelatch.protocol import COUNTERS, MAX_COUNT, Receiver, crc8, encode


class ProtocolTests(unittest.TestCase):
    def test_crc_standard_check(self):
        self.assertEqual(crc8(b"123456789"), 0xF4)
        self.assertEqual(crc8(b""), 0)

    def test_encoder_bounds(self):
        for payload in (b"", bytes(17)):
            with self.assertRaises(ValueError):
                encode(payload)
        self.assertEqual(encode(b"\x00"), bytes.fromhex("a5010015"))

    def test_roundtrip_all_lengths_and_byte_values(self):
        for length in range(1, 17):
            for byte in range(256):
                payload = bytes([byte]) * length
                receiver = Receiver()
                for data in encode(payload):
                    self.assertIsNone(receiver.step(data=data, valid=True))
                self.assertEqual(receiver.pending, payload)
                self.assertEqual(receiver.output_length, length)
                self.assertEqual(receiver.output_payload, int.from_bytes(payload, "little"))
                self.assertEqual(receiver.step(out_ready=True), payload)
                self.assertIsNone(receiver.step(out_ready=True))

    def test_rejection_abort_and_recovery(self):
        receiver = Receiver()
        for byte in bytes.fromhex("11a500a511a50100ff"):
            receiver.step(data=byte, valid=True)
        self.assertEqual(receiver.counts["discarded_bytes"], 1)
        self.assertEqual(receiver.counts["invalid_lengths"], 2)
        self.assertEqual(receiver.counts["crc_errors"], 1)
        self.assertIsNone(receiver.pending)
        receiver.step(data=0xA5, valid=True)
        receiver.step(abort=True)
        receiver.step(abort=True)
        self.assertEqual(receiver.counts["incomplete_frames"], 1)

    def test_pending_stability_reset_priority_and_saturation(self):
        receiver = Receiver()
        for byte in encode(b"OK"):
            receiver.step(data=byte, valid=True)
        for _ in range(100):
            receiver.step(data=0x11, valid=True, abort=True)
            self.assertEqual(receiver.pending, b"OK")
        receiver.step(rst=True, abort=True, valid=True, out_ready=True)
        self.assertIsNone(receiver.pending)
        self.assertEqual(receiver.counts, dict.fromkeys(COUNTERS, 0))
        for counter in COUNTERS:
            receiver.counts[counter] = MAX_COUNT - 1
            receiver.bump(counter)
            receiver.bump(counter)
            self.assertEqual(receiver.counts[counter], MAX_COUNT)


if __name__ == "__main__":
    unittest.main()
