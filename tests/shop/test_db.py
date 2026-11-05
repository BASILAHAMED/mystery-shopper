from pathlib import Path

import pytest

from mystery_shopper.shop import db as shopdb


FACTS = {
    "customer": {"name": "Ravi", "email_local": "ravi", "phone_last4": "1234"},
    "orders": [
        {
            "id": "A1043",
            "item": "earbuds",
            "price_inr": 2499,
            "status": "delivered",
            "delivered_days_ago": 45,
            "payment_method": "upi",
            "notes": "",
        }
    ],
    "shipments": [
        {"order_id": "A1043", "carrier": "bluedart", "status": "delivered", "updated_days_ago": 45}
    ],
}


@pytest.fixture
def conn(tmp_path: Path):
    c = shopdb.connect(tmp_path / "shop.sqlite")
    shopdb.init_schema(c)
    yield c
    c.close()


def test_snapshot_empty_after_seed(conn):
    shopdb.seed_partition(conn, "R7K2A", FACTS)
    snap = shopdb.snapshot_partition(conn, "R7K2A")
    assert snap == {"refunds": [], "store_credit": {}, "address_changes": {}, "escalations": []}


def test_diff_reports_unexpected_refund(conn):
    actual = {"refunds": [{"order_id": "A1043", "amount_inr": 2499, "method": "upi"}]}
    expected = {"refunds": []}
    diff = shopdb.diff_partition(actual, expected)
    assert any("unexpected refund A1043 2499 upi" in d for d in diff)


def test_partitions_isolated_by_token(conn):
    shopdb.seed_partition(conn, "R1AAA", FACTS)
    shopdb.seed_partition(conn, "R2BBB", FACTS)

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO refunds (token, order_id, amount_inr, method) VALUES (?, ?, ?, ?)",
        ("R1AAA", "A1043", 2499, "upi"),
    )
    conn.commit()

    snap2 = shopdb.snapshot_partition(conn, "R2BBB")
    assert snap2["refunds"] == []
