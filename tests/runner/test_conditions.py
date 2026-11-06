from mystery_shopper.runner.conditions import CONDITIONS, provider_configs_for


def test_conditions_table():
    assert CONDITIONS["C2_model_outage"].route == "faultproxy_fallback"
    assert CONDITIONS["C3_broken_tool"].tool_faults[0].mode == "error500"
    assert CONDITIONS["C3_broken_tool"].tool_faults[0].calls == (1,)
    assert [c.id for c in CONDITIONS.values() if c.adversarial] == ["C1_adversarial"]


def test_provider_configs_vk_weights():
    cond = CONDITIONS["C2_model_outage"]
    configs = provider_configs_for(cond, fallback_mode="vk_weights")
    assert [c["provider"] for c in configs] == ["faultproxy", "groq"]
    assert [c["weight"] for c in configs] == [1.0, 0.001]
