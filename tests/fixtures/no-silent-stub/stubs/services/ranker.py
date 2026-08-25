"""Taxonomy 4: a test double left on a production path."""

from unittest.mock import MagicMock

search_client = MagicMock()
search_client.rank.return_value = ["doc-1", "doc-2", "doc-3"]


def rank_documents(query):
    return search_client.rank(query)


def main():
    print(rank_documents("quarterly revenue"))


if __name__ == "__main__":
    main()
