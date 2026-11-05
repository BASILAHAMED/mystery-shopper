"""Settings loaded from the environment, plus run-token helpers."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MS_", env_file=".env", extra="ignore")

    bifrost_url: str = "http://127.0.0.1:8080"
    shop_url: str = "http://127.0.0.1:8765"
    proxy_url: str = "http://127.0.0.1:8766"

    agent_model: str = "shopmodel"
    sim_model: str = "groq/openai/gpt-oss-120b"

    fallback_mode: str = "vk_weights"
    k: int = 5
    concurrency: int = 4
    budget_usd: float = 10.0
    run_vk_budget_usd: float = 0.05

    reply_timeout_s: int = 90
    run_timeout_s: int = 300
    max_customer_turns: int = 12
    max_tool_steps: int = 10

    results_dir: Path = Path("results")
