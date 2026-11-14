import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from summarize import summarize  # noqa: E402


class SummarizeTest(unittest.TestCase):
    def test_exact_value_uses_final_time(self):
        result = summarize([(0.0, 1.0), (1.0, 0.5)], k=math.log(2))
        self.assertAlmostEqual(result["exact_y"], 0.5)
        self.assertAlmostEqual(result["abs_error"], 0.0)


if __name__ == "__main__":
    unittest.main()
