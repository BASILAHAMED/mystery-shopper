from mystery_shopper.stats.metrics import bootstrap_ci, paired_diff, pass_hat_k


def _rec(agent, ticket_id, variant, condition, outcome):
    return type(
        "FakeRecord",
        (),
        {
            "spec": type("S", (), {"agent": agent, "ticket_id": ticket_id, "variant": variant, "condition": condition})(),
            "outcome": outcome,
        },
    )()


def test_pass_hat_k_values_5_of_5():
    records = [_rec("a", "t", 0, "C0_clean", "success") for _ in range(5)]
    assert pass_hat_k(records, k=5) == 1.0


def test_pass_hat_k_values_4_of_5_k5():
    records = [_rec("a", "t", 0, "C0_clean", "success") for _ in range(4)] + [
        _rec("a", "t", 0, "C0_clean", "fail")
    ]
    assert pass_hat_k(records, k=5) == 0.0


def test_pass_hat_k_values_4_of_5_k3():
    records = [_rec("a", "t", 0, "C0_clean", "success") for _ in range(4)] + [
        _rec("a", "t", 0, "C0_clean", "fail")
    ]
    assert pass_hat_k(records, k=3) == 0.4


def test_bootstrap_ci_deterministic():
    a = bootstrap_ci([1.0, 0.0, 1.0, 1.0, 0.0], seed=42)
    b = bootstrap_ci([1.0, 0.0, 1.0, 1.0, 0.0], seed=42)
    assert a == b


def test_bootstrap_ci_constant_ones():
    assert bootstrap_ci([1.0, 1.0, 1.0, 1.0]) == (1.0, 1.0)


def test_paired_diff_significance_true():
    a = {f"k{i}": 1.0 for i in range(20)}
    b = {f"k{i}": 0.0 for i in range(20)}
    mean_diff, (lo, hi), significant = paired_diff(a, b)
    assert significant is True


def test_paired_diff_significance_false_identical():
    a = {f"k{i}": 0.5 for i in range(20)}
    b = {f"k{i}": 0.5 for i in range(20)}
    mean_diff, (lo, hi), significant = paired_diff(a, b)
    assert significant is False
