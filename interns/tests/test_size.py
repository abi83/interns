import unittest

from interns.size import roll_up_size


class RollUpSizeTests(unittest.TestCase):
    def test_table(self):
        cases = [
            (("Low", "Low", "Low", "Low"), "XS"),
            (("Low", "Mid", "Low", "Low"), "S"),
            (("Mid", "Low", "Low", "Mid"), "S"),
            (("High", "Low", "Low", "Low"), "M"),
            (("High", "Mid", "Mid", "Mid"), "L"),
            (("High", "High", "Low", "Low"), "L"),
            (("High", "High", "High", "Low"), "XL"),
        ]
        for scores, expected in cases:
            with self.subTest(scores=scores):
                self.assertEqual(roll_up_size(*scores), expected)

    def test_case_insensitive(self):
        self.assertEqual(roll_up_size("low", "MID", "HIGH", "Low"), "M")

    def test_invalid_score(self):
        with self.assertRaisesRegex(ValueError, "Not a Low|Mid|High score"):
            roll_up_size("Low", "Medium", "Low", "Low")


if __name__ == "__main__":
    unittest.main()
