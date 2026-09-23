from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class ActionClass(StrEnum):
    READ = "read_op"
    EDIT = "code_edit"
    ENV = "env_mutation"
    DB = "db_write"
    API = "external_api"
    FINAL = "final_answer"


class Proposal(StrictModel):
    tool: Literal[
        "list_files",
        "read_file",
        "write_file",
        "delete_file",
        "python",
        "run_tests",
        "sql",
        "final_answer",
    ]
    args: dict[str, Any]


class ActionContract(StrictModel):
    proposal: Proposal
    action_class: ActionClass
    permissions: list[str]
    mutation_type: Literal["none", "local", "environment", "database", "external"]
    reversible: bool
    scope: str = "isolated_workspace"


class Task(StrictModel):
    task_id: str
    group_id: str
    source: str
    source_revision: str
    source_split: str
    kind: Literal["swe", "gsm8k", "math"]
    prompt: str
    official_holdout: bool
    repo: str | None = None
    base_commit: str | None = None
    # Never passed to policy, critic, verifier or sandbox.
    private: dict[str, Any] = Field(default_factory=dict)


class Usage(StrictModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    measured: bool = True
    seconds: float = Field(default=0, ge=0)

    @property
    def total(self):
        return self.prompt_tokens + self.completion_tokens


class Verification(StrictModel):
    verdict: Literal["PASS", "FAIL", "ERROR"]
    reason: str
    usage: Usage = Field(default_factory=Usage)
    cost: float = Field(default=0.02, gt=0)


class StepRecord(StrictModel):
    # Runtime fills fields incrementally; EventStore validates the completed record atomically.
    model_config = ConfigDict(extra="forbid", validate_assignment=False, allow_inf_nan=False)
    schema_version: int = 1
    event_id: str
    task_id: str
    group_id: str
    source: str
    run_id: str
    model: str
    critic_id: str = "unspecified"
    verifier_id: str = "unspecified"
    step_id: int = Field(ge=0)
    split: str
    calibration_role: str | None = None
    context: str
    action: ActionContract | None = None
    blocked: bool = False
    block_reason: str | None = None
    raw_logit: float | None = None
    p_error: float | None = Field(default=None, ge=0, le=1)
    impact: float = Field(default=0, ge=0, le=1)
    detection_rate: float | None = Field(default=None, ge=0, le=1)
    false_positive_rate: float | None = Field(default=None, ge=0, le=1)
    residual_loss: float | None = Field(default=None, ge=0, le=1)
    delta: float | None = None
    decision: Literal["blocked", "skip", "verify"]
    verification: Verification | None = None
    audit_only: bool = False
    verifier_cost: float = Field(default=0.02, gt=0)
    false_alarm_cost: float = Field(default=0.1, ge=0)
    executed: bool = False
    observation: dict[str, Any] | None = None
    state_before: str | None = None
    state_after: str | None = None
    restored_hash: str | None = None
    recovery_seconds: float = Field(default=0, ge=0)
    # Unknown by default. Never infer semantic truth from a successful exit code.
    error_label: Literal[0, 1] | None = None
    label_scope: Literal["semantic", "operational", "unknown"] = "unknown"
    label_source: str | None = None
    policy_usage: Usage = Field(default_factory=Usage)
    critic_usage: Usage = Field(default_factory=Usage)
    budget_spent: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def label_provenance(self):
        if self.error_label is not None and (
            not self.label_source or self.label_scope == "unknown"
        ):
            raise ValueError("Labeled records require a source and explicit label_scope")
        return self
