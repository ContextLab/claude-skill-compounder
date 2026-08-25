"""A real silent stub the mechanical scan cannot see, kept here on purpose.

There is no marker comment, no credential guard, no cache lookup, and no
ignored parameter. `region` is read, the arithmetic is real, and the unknown
branch returns a number that is the right type, the right magnitude, and
completely invented. Only the distinguishing question catches this one:
a caller receiving 0.0725 has no way to learn it was a guess.

The test suite asserts that this file is NOT flagged. That assertion is the
measured ceiling of the scan, and the reason phase 2 of the skill is a
question rather than a grep.
"""

RATES = {"NH": 0.0, "CA": 0.0725, "NY": 0.08875}
BLENDED_US_AVERAGE = 0.0725


def sales_tax(subtotal, region):
    rate = RATES.get(region)
    if rate is None:
        rate = BLENDED_US_AVERAGE
    return round(subtotal * rate, 2)


def main():
    print(sales_tax(100.0, "CA"))
    print(sales_tax(100.0, "Bavaria"))


if __name__ == "__main__":
    main()
