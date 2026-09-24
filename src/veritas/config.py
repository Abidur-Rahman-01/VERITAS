from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from .schema import ActionClass, StrictModel


class ModelConfig(StrictModel):
    backend: Literal["openai_compatible", "ollama", "transformers"] = "openai_compatible"
    base_url: str = "http://127.0.0.1:8000/v1"
    name: str = "local-policy"
    api_key_env: str = "VERITAS_API_KEY"
    max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=180, gt=0)
    temperature: float = Field(default=0, ge=0, le=2)


class SandboxConfig(StrictModel):
    image: str = "veritas-sandbox:local"
    platform: str | None = None
    memory: str = "4g"
    cpus: float = Field(default=2, gt=0)
    timeout_seconds: int = Field(default=60, gt=0)
    max_output_chars: int = Field(default=16000, ge=100)


class RunConfig(StrictModel):
    max_steps: int = Field(default=30, gt=0)
    history_chars: int = Field(default=30000, gt=1000)
    verification_budget: float = Field(default=10, ge=0)
    verification_cost: float = Field(default=0.02, gt=0)
    false_alarm_cost: float = Field(default=0.1, ge=0)
    budget_unit: str = "verifier_call_credit"
    policy: str = "rcvov"
    threshold: float = 0
    dynamic_lambda: float = Field(default=0.0, ge=0)
    audit_all: bool = False
    allow_uncalibrated: bool = False
    score_critic: bool = True
    recovery_mode: Literal["checkpoint", "restart"] = "checkpoint"


class Config(StrictModel):
    seed: int = 42
    model: ModelConfig = Field(default_factory=ModelConfig)
    critic: ModelConfig = Field(default_factory=ModelConfig)
    verifier: ModelConfig = Field(default_factory=ModelConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    run: RunConfig = Field(default_factory=RunConfig)
    probes: list[list[str]] = Field(default_factory=list)
    impact: dict[ActionClass, float] = Field(
        default_factory=lambda: {
            ActionClass.READ: 0.1,
            ActionClass.EDIT: 0.4,
            ActionClass.ENV: 0.75,
            ActionClass.DB: 0.9,
            ActionClass.API: 1.0,
            ActionClass.FINAL: 0.6,
        }
    )


def load_config(path, override=None):
    def merge(a, b):
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                merge(a[k], v)
            else:
                a[k] = v
        return a

    obj = yaml.safe_load(Path(path).read_text())
    for extra in [override] if isinstance(override, (str, Path)) else override or []:
        obj = merge(obj, yaml.safe_load(Path(extra).read_text()))
    config = Config.model_validate(obj)
    if set(config.impact) != set(ActionClass) or any(
        not 0 <= v <= 1 for v in config.impact.values()
    ):
        raise ValueError("impact must define all action classes with weights in [0,1]")
    if config.run.budget_unit != "verifier_call_credit":
        raise ValueError("Only fixed verifier-call credit budgets are implemented")
    return config
