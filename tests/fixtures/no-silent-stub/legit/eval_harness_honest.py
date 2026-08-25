"""Legitimate: an evaluation whose actual answers come from the system under test.

It scores 66.7%, because the system under test gets one row wrong. That is the
tell: an honest harness reports the score it measured. The self-scoring stub in
`stubs/self_scoring_eval.py` reports 100.0% on a harder dataset without ever
calling anything.
"""

DATASET = [
    {"question": "2 + 2?", "expected_answer": "4"},
    {"question": "3 * 3?", "expected_answer": "9"},
    {"question": "10 - 7?", "expected_answer": "2"},
]


def system_under_test(question):
    left, op, right = question.rstrip("?").split()
    values = {"+": int(left) + int(right), "*": int(left) * int(right),
              "-": int(left) - int(right)}
    return str(values[op])


def score(dataset):
    hits = 0
    for row in dataset:
        actual_answer = system_under_test(row["question"])
        is_correct = actual_answer == row["expected_answer"]
        hits += int(is_correct)
    return 100.0 * hits / len(dataset)


def main():
    print(f"accuracy: {score(DATASET):.1f}%")


if __name__ == "__main__":
    main()
