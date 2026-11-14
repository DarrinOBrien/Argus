"""Heart-rate packet parsing, using packets captured from a Polar H10. Runs on a laptop."""
import unittest

from argus import heart_rate


class HeartRateTests(unittest.TestCase):
    def test_polar_packets(self):
        self.assertEqual(heart_rate(bytes.fromhex("164dc402")), 77)  # 8-bit bpm with RR intervals
        self.assertEqual(heart_rate(bytes.fromhex("164ec1020403")), 78)
        self.assertEqual(heart_rate(bytes.fromhex("1701010000")), 257)  # 16-bit bpm flag

    def test_no_reading(self):
        self.assertIsNone(heart_rate(bytes.fromhex("1452")))  # contact supported but not detected
        self.assertIsNone(heart_rate(bytes.fromhex("1600")))  # zero bpm while the strap settles
        self.assertIsNone(heart_rate(b"\x16"))  # truncated packet


if __name__ == "__main__":
    unittest.main()
