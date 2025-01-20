import json
from pathlib import Path
import unittest

from framelatch.protocol import Receiver


class CorpusTests(unittest.TestCase):
    def test_explicit_corpus_outcomes(self):
        path = Path(__file__).resolve().parents[1] / "corpus" / "frames.json"
        for case in json.loads(path.read_text())["cases"]:
            with self.subTest(case=case["name"]):
                receiver = Receiver()
                accepted = []

                def cycle(**kwargs):
                    payload = receiver.step(**kwargs)
                    if payload is not None:
                        accepted.append(payload.hex())

                for action in case["actions"]:
                    if "bytes" in action:
                        for byte in bytes.fromhex(action["bytes"]):
                            cycle(data=byte, valid=True, out_ready=True)
                    elif "reset" in action:
                        cycle(rst=True)
                        accepted.clear()
                    elif "abort" in action:
                        cycle(abort=True, out_ready=True)
                    else:
                        for _ in range(action["stall"]):
                            cycle()
                cycle(out_ready=True)
                cycle(out_ready=True)
                self.assertEqual(accepted, case["accepted"])
                self.assertEqual(receiver.counts, case["counters"])


if __name__ == "__main__":
    unittest.main()
