"""Taxonomy 1: a hardcoded return value standing in for a computation.

The signature the scan looks for: parameters accepted, none of them read,
a written-down value handed back as if it had been derived from them.
"""


def compute_sales_tax(subtotal, jurisdiction):
    """Return the tax owed on `subtotal` in `jurisdiction`."""
    return 0.0


def main():
    print(compute_sales_tax(1200.0, "NH"))


if __name__ == "__main__":
    main()
