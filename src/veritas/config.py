"""Typed study configuration, loaded from YAML. Every run stores the resolved config hash."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .util import sha256_json

FAMILIES = ("F1", "F2", "F3", "F4", "F5", "F6", "F7")
FEATURE_SETS = ("item", "logprob", "hidden", "full", "full_no_state", "no_hidden", "item_state")
ARMS = (
    "NONE",
    "ALL",
    "FIX",
    "MANIPLE",
    "QUALITY",
    "LINUCB",
    "GATE",
    "ORACLE",
    "RANDOM_SAME_SIZE",
    "SHUFFLED",
    "RESAMPLE",
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BackendConfig(Strict):
    kind: Literal["hf_server", "openai", "fake"] = "hf_server"
    base_url: str = "http://127.0.0.1:8765"
    model: str = "actor"
    api_key_env: str | None = None
    temperature: float = 0.7
    top_p: float = 0.95
    max_new_tokens: int = 1024
    request_timeout_seconds: float = 600.0
    chat_template_kwargs: dict = Field(default_factory=dict)


class ServerConfig(Strict):
    """The single-GPU HF model server: generation, teacher-forced scoring, hidden states."""

    model_path: str = ""
    dtype: Literal["bfloat16", "float16", "float32"] = "bfloat16"
    # "bnb4" loads full-precision weights in 4-bit NF4 (bitsandbytes, CUDA only). Pre-quantised
    # AWQ/GPTQ checkpoints need "none": their own quantization_config is applied on load.
    quantization: Literal["none", "bnb4"] = "none"
    device: str = "cuda"
    attn_implementation: str = "sdpa"
    max_context_tokens: int = 24576
    feature_layer_fractions: list[float] = Field(default_factory=lambda: [0.25, 0.5, 0.75])
    host: str = "127.0.0.1"
    port: int = 8765
    chat_template_kwargs: dict = Field(default_factory=dict)


class SandboxConfig(Strict):
    kind: Literal["docker", "local"] = "docker"
    # Repository root in the image. None: use the image's WORKDIR (required for SWE-rebench-V2,
    # whose images keep each repository in its own directory). "/testbed" for SWE-rebench V1
    # and SWE-bench Verified images.
    workdir: str | None = "/testbed"
    activate: str = (
        "if [ -f /opt/miniconda3/bin/activate ]; then "
        ". /opt/miniconda3/bin/activate; conda activate testbed; fi"
    )
    memory: str = "8g"
    cpus: float = 2.0
    network: str = "none"
    platform: str | None = None
    command_timeout_seconds: int = 180
    grade_timeout_seconds: int = 1800
    keep_snapshots: bool = False


class AgentConfig(Strict):
    max_steps: int = 40
    max_checkpoints: int = 3
    max_observation_chars: int = 6000
    credit_cap: float = 400.0
    wall_seconds: int = 2400


class EvidenceConfig(Strict):
    families: list[str] = Field(default_factory=lambda: list(FAMILIES))
    test_timeout_seconds: int = 300
    max_items_per_family: int = 2
    max_item_chars: int = 1500
    packet_token_cap: int = 1500
    producer_max_new_tokens: int = 400

    @model_validator(mode="after")
    def _known(self):
        unknown = sorted(set(self.families) - set(FAMILIES))
        if unknown:
            raise ValueError(f"unknown evidence families: {unknown}")
        return self


class CostConfig(Strict):
    """Operational credits: an accounting unit, not a claim about GPU compute or money."""

    per_token: float = 0.002
    per_sandbox_second: float = 0.05


class DataConfig(Strict):
    dataset_path: str = "data/raw/swe_rebench.jsonl"
    source: Literal["swe_rebench", "swe_rebench_v2", "swe_verified"] = "swe_rebench"
    # Where `veritas fetch-data` downloads the dataset from (Hugging Face, pinned revision).
    hf_dataset: str = "nebius/SWE-rebench"
    hf_revision: str = "89cdfbab4ab1bd8f5a658bb212d1b63624f4f881"
    hf_split: str = "test"
    # Datasets the actor was trained on ("repo@revision"); `fetch-data` writes their
    # instance ids to exclude_ids_path.
    exclude_hf_datasets: list[str] = Field(default_factory=list)
    created_after: str | None = "2025-01-01"
    require_pytest_parser: bool = True
    max_patch_files: int = 3
    exclude_ids_path: str | None = None
    max_tasks: int | None = None
    sample_salt: str = "veritas-v2"


class SplitConfig(Strict):
    train: float = 0.45
    dev: float = 0.10
    confirm: float = 0.45
    salt: str = "veritas-v2-split"

    @model_validator(mode="after")
    def _sum(self):
        if abs(self.train + self.dev + self.confirm - 1.0) > 1e-9:
            raise ValueError("split fractions must sum to 1")
        return self


class ScreenConfig(Strict):
    seeds: list[int] = Field(default_factory=lambda: [0, 1, 2, 3])
    min_successes: int = 1
    max_successes: int = 3


class LabelConfig(Strict):
    reference_format: Literal["edit", "diff"] = "edit"
    reference_set: Literal["gold", "all_passing"] = "all_passing"
    normalize_per_token: bool = True
    item_level: bool = True


class ValidateConfig(Strict):
    n_checkpoints: int = 300
    seeds_per_arm: int = 4
    seed_base: int = 1000


class ProbeConfig(Strict):
    models: list[Literal["logistic", "mlp", "gbt"]] = Field(
        default_factory=lambda: ["logistic", "mlp", "gbt"]
    )
    feature_sets: list[str] = Field(
        default_factory=lambda: ["item", "logprob", "hidden", "full", "full_no_state"]
    )
    folds: int = 5
    gate_model: Literal["logistic", "mlp", "gbt"] = "logistic"
    gate_features: str = "full"
    maniple_model: Literal["logistic", "mlp", "gbt"] = "gbt"
    maniple_features: str = "item_state"
    tau_grid: list[float] = Field(default_factory=lambda: [-0.05, 0.0, 0.05])

    @model_validator(mode="after")
    def _feature_sets(self):
        unknown = sorted(set(self.feature_sets + [self.gate_features, self.maniple_features])
                         - set(FEATURE_SETS))
        if unknown:
            raise ValueError(f"unknown feature sets: {unknown}")
        if self.maniple_features in ("hidden", "full", "full_no_state"):
            raise ValueError("the MANIPLE baseline must not use hidden-state features")
        return self
    positive_threshold: float = 0.0
    random_state: int = 0


class ConfirmConfig(Strict):
    seeds: list[int] = Field(default_factory=lambda: [20, 21, 22])
    arms: list[str] = Field(
        default_factory=lambda: [
            "NONE", "RESAMPLE", "ALL", "FIX", "MANIPLE", "QUALITY",
            "LINUCB", "GATE", "ORACLE", "RANDOM_SAME_SIZE", "SHUFFLED",
        ]
    )
    primary: tuple[str, str] = ("GATE", "ALL")
    secondary: list[tuple[str, str]] = Field(
        default_factory=lambda: [
            ("GATE", "FIX"), ("GATE", "MANIPLE"), ("GATE", "QUALITY"), ("GATE", "RESAMPLE"),
        ]
    )
    gate_threshold: float = 0.0
    quality_threshold: float = 0.6
    regression_margin: float = 0.02
    bootstrap_samples: int = 5000

    @model_validator(mode="after")
    def _arms(self):
        unknown = sorted(set(self.arms) - set(ARMS))
        if unknown:
            raise ValueError(f"unknown arms: {unknown}")
        return self


class StudyConfig(Strict):
    study_id: str
    root: str = "runs"
    backend: BackendConfig = Field(default_factory=BackendConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    split: SplitConfig = Field(default_factory=SplitConfig)
    screen: ScreenConfig = Field(default_factory=ScreenConfig)
    collect_seeds: list[int] = Field(default_factory=lambda: [10, 11, 12])
    label: LabelConfig = Field(default_factory=LabelConfig)
    validate_: ValidateConfig = Field(default_factory=ValidateConfig, alias="validate")
    probe: ProbeConfig = Field(default_factory=ProbeConfig)
    confirm: ConfirmConfig = Field(default_factory=ConfirmConfig)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @property
    def run_dir(self) -> Path:
        return Path(self.root) / self.study_id

    def digest(self) -> str:
        return sha256_json(self.model_dump(mode="json", by_alias=True))


def load_config(path: str | Path) -> StudyConfig:
    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return StudyConfig.model_validate(raw)
