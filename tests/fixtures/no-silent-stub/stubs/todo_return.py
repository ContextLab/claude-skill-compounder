"""Taxonomy 5: a TODO on a live path that returns instead of raising."""


def related_articles(article_id, limit=5):
    # TODO: wire this up to the recommendation service
    return []


def render_sidebar(article_id):
    items = related_articles(article_id)
    return f"{len(items)} related articles"


def main():
    print(render_sidebar("a-42"))


if __name__ == "__main__":
    main()
