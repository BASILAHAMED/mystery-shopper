import random
import re

from mystery_shopper.tokens import new_token, scoped_email, scoped_id, token_in


def test_new_token_format():
    rng = random.Random(1)
    tokens = [new_token(rng) for _ in range(100)]
    for t in tokens:
        assert re.fullmatch(r"R[A-Z0-9]{4}", t), t

    rng2 = random.Random(1)
    tokens2 = [new_token(rng2) for _ in range(100)]
    assert tokens == tokens2


def test_scoped_ids_and_token_detection():
    assert scoped_id("A1043", "R7K2") == "A1043-R7K2"
    assert token_in("order A1043-R7K2 pls") == "R7K2"
    assert token_in("ravi.r7k2@example.com") == "R7K2"
    assert token_in("none") is None
    assert scoped_email("ravi", "R7K2") == "ravi.r7k2@example.com"
