"""Taxonomy 6: an evaluation that scores itself against its own input.

Modeled on anthropics/claude-code#54682, where rows were inserted with
`claude_answer = expected_answer` (a literal column copy) and `is_correct`
set programmatically. The harness reports a perfect score and no blind
evaluation ever happened.
"""

BACKFILL_SQL = """
INSERT INTO eval_runs (question, claude_answer, is_correct)
SELECT question, expected_answer AS claude_answer, TRUE FROM question_bank
"""

DATASET = [
    {"question": "capital of France?", "expected_answer": "Paris"},
    {"question": "2 + 2?", "expected_answer": "4"},
    {"question": "author of Dubliners?", "expected_answer": "James Joyce"},
    {"question": "boiling point of water at 1 atm, in C?", "expected_answer": "100"},
]


def score(dataset):
    rows = []
    for row in dataset:
        actual_answer = row["expected_answer"]
        is_correct = True
        rows.append({"question": row["question"], "actual": actual_answer,
                     "is_correct": is_correct})
    hits = sum(1 for r in rows if r["is_correct"])
    return 100.0 * hits / len(rows)


def main():
    print(f"accuracy: {score(DATASET):.1f}%")


if __name__ == "__main__":
    main()
