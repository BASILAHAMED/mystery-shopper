from mystery_shopper.shop.faults import ToolFault, ToolFaultSchedule


def test_decide_first_call_only():
    schedule = ToolFaultSchedule([ToolFault("get_order", "error500", (1,))])
    assert schedule.decide("get_order", 1) == "error500"
    assert schedule.decide("get_order", 2) is None


def test_wildcard_never_matches_verify_identity():
    schedule = ToolFaultSchedule([ToolFault("*", "error500", "all")])
    assert schedule.decide("verify_identity", 1) is None
    assert schedule.decide("get_order", 1) == "error500"
