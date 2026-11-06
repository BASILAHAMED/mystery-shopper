"""Test conditions: route, fault schedule, and provider-config shaping."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mystery_shopper.faultproxy.app import ProxySchedule
from mystery_shopper.settings import Settings
from mystery_shopper.shop.faults import ToolFault


@dataclass(frozen=True)
class Condition:
    id: str
    route: Literal["real", "faultproxy_fallback", "faultproxy_only"]
    proxy_schedule: ProxySchedule | None
    tool_faults: tuple[ToolFault, ...]
    adversarial: bool


CONDITIONS: dict[str, Condition] = {
    "C0_clean": Condition("C0_clean", "real", None, (), False),
    "C1_adversarial": Condition("C1_adversarial", "real", None, (), True),
    "C2_model_outage": Condition(
        "C2_model_outage", "faultproxy_fallback", ProxySchedule("fail_all", status=503), (), False
    ),
    "C3_broken_tool": Condition(
        "C3_broken_tool", "real", None, (ToolFault("*", "error500", (1,)),), False
    ),
    "C2x_outage_no_fallback": Condition(
        "C2x_outage_no_fallback",
        "faultproxy_only",
        ProxySchedule("fail_first_n", n=2, status=503),
        (),
        False,
    ),
}


def provider_configs_for(cond: Condition, fallback_mode: str) -> list[dict]:
    allowed_models = [Settings().agent_model]

    if cond.route == "real":
        return [{"provider": "groq", "weight": 1.0, "allowed_models": allowed_models, "key_ids": ["*"]}]

    if cond.route == "faultproxy_fallback":
        if fallback_mode == "vk_weights":
            return [
                {"provider": "faultproxy", "weight": 1.0, "allowed_models": allowed_models, "key_ids": ["*"]},
                {"provider": "groq", "weight": 0.001, "allowed_models": allowed_models, "key_ids": ["*"]},
            ]
        return [{"provider": "faultproxy", "weight": 1.0, "allowed_models": allowed_models, "key_ids": ["*"]}]

    if cond.route == "faultproxy_only":
        return [{"provider": "faultproxy", "weight": 1.0, "allowed_models": allowed_models, "key_ids": ["*"]}]

    raise ValueError(f"unknown route: {cond.route}")
