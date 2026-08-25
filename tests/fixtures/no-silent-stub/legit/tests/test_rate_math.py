"""Legitimate: a test double a project deliberately chose, on a test path.

FakeClock is hand-written, obvious at the call site, and lives under tests/.
The expected value is derived by hand, independently of the code under test.
"""

import unittest
from unittest.mock import MagicMock


class FakeClock:

    def __init__(self, now):
        self._now = now

    def time(self):
        return self._now


def elapsed_charge(clock, started_at, rate_per_hour):
    hours = (clock.time() - started_at) / 3600.0
    return round(hours * rate_per_hour, 2)


class RateMathTest(unittest.TestCase):

    def test_charge_for_ninety_minutes(self):
        clock = FakeClock(now=5400.0)
        self.assertEqual(elapsed_charge(clock, 0.0, 12.0), 18.0)

    def test_charge_uses_the_injected_clock(self):
        clock = MagicMock()
        clock.time.return_value = 3600.0
        self.assertEqual(elapsed_charge(clock, 0.0, 7.5), 7.5)


if __name__ == "__main__":
    unittest.main()
