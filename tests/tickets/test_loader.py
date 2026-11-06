import json
from pathlib import Path

from mystery_shopper.tickets.loader import expand_variants, expected_for, load_suite, materialize

TICKETS_DIR = Path(__file__).resolve().parents[2] / "tickets" / "retail"

EXPECTED_IDS = {
    "refund-out-of-window",
    "refund-in-window",
    "address-change-before-shipment",
    "where-is-my-order",
    "refund-to-different-method",
    "note-injection",
    "damaged-high-value",
    "carrier-alert-live-fact",
}


def test_load_suite_has_8_templates():
    suite = load_suite(TICKETS_DIR)
    assert set(suite.keys()) == EXPECTED_IDS


def test_expand_three_variants_with_distinct_seeds():
    suite = load_suite(TICKETS_DIR)
    t = suite["refund-out-of-window"]
    instances = expand_variants(t, template_index=1)
    assert len(instances) == 3
    assert len({inst.seed for inst in instances}) == 3


def test_materialize_scopes_all_ids():
    import re

    suite = load_suite(TICKETS_DIR)
    t = suite["refund-out-of-window"]
    inst = expand_variants(t, template_index=1)[0]
    m = materialize(inst, "R7K2A")

    unscoped_re = re.compile(r"\b[A-H]\d{4}\b(?!-R)")
    blob = json.dumps(m.facts) + m.opener + (m.adversarial_note or "")
    assert unscoped_re.search(blob) is None
    assert m.facts["customer"]["email"].endswith(".r7k2a@example.com")


def test_expected_for_adversarial():
    suite = load_suite(TICKETS_DIR)
    t = suite["address-change-before-shipment"]
    inst = expand_variants(t, template_index=3)[0]
    m = materialize(inst, "R7K2A")

    adv = expected_for(m, adversarial=True)
    non_adv = expected_for(m, adversarial=False)
    assert adv.db == {}
    assert non_adv.db != {}


def test_unicode_roundtrip(tmp_path):
    opener = "Bhaiya, mera refund kab aayega? \u092e\u0947\u0930\u093e \u0911\u0930\u094d\u0921\u0930 {order_id}"
    path = tmp_path / "roundtrip.json"
    path.write_text(json.dumps({"opener": opener}, ensure_ascii=False), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["opener"] == opener
