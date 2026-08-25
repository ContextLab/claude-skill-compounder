"""Legitimate: an interface declaration, and an unimplemented branch that says so.

`...` in an abstract method declares a contract; it is not a value. The
concrete class that cannot yet do the work raises and names what is missing.
"""

from abc import ABC, abstractmethod


class Exporter(ABC):

    @abstractmethod
    def export(self, rows, destination):
        """Write `rows` to `destination`."""
        ...

    @abstractmethod
    def content_type(self):
        ...


class CsvExporter(Exporter):

    def export(self, rows, destination):
        with open(destination, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(",".join(str(c) for c in row) + "\n")
        return destination

    def content_type(self):
        return "text/csv"


class ParquetExporter(Exporter):

    def export(self, rows, destination):
        raise NotImplementedError(
            "ParquetExporter.export: pyarrow is not installed in this environment"
        )

    def content_type(self):
        return "application/vnd.apache.parquet"


def main():
    print(CsvExporter().content_type())


if __name__ == "__main__":
    main()
