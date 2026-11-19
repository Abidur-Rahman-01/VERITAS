"""Evidence records, the exact-hash validity rule, and the common packet renderer."""

from __future__ import annotations

from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from .util import sha256_json, utc_now

FAMILY_NAMES = {
    "F1": "failing-check",
    "F2": "traceback/error",
    "F3": "contrast-pair",
    "F4": "runtime-state",
    "F5": "localization finding",
    "F6": "suggestion/plan",
    "F7": "rubric",
}
OBSERVED_FAMILIES = ("F1", "F2", "F3", "F4")
NEUTRAL_PACKET = (
    "[HARNESS] Checkpoint {checkpoint}: no additional evidence. Continue working on the issue."
)
PACKET_HEADER = (
    "[HARNESS EVIDENCE] Checkpoint {checkpoint}. The harness collected the observations below "
    "about the current repository state. Items marked `model opinion` were written by a model "
    "and may be wrong. Use what helps; ignore the rest."
)

# Runtime-visible fields. Outcome-plane fields (e.g. bug_discriminative) live in label tables,
# never on the item, so they cannot reach a packet or a feature vector.


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = ""
    family: str
    source: str
    basis: Literal["observed", "model_opinion"]
    patch_hash: str
    environment_hash: str
    command: str = ""
    raw_artifact_hash: str = ""
    claim: str
    location: str = ""
    observed: str = ""
    expected_if_observed: str = ""
    affected_files: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    severity: float = 0.5
    status: Literal["current", "expired"] = "current"
    invalidated_reason: str = ""
    created_at: str = Field(default_factory=utc_now)
    cost_credits: float = 0.0
    task_id: str = ""
    checkpoint_id: str = ""

    def model_post_init(self, _context) -> None:
        if not self.evidence_id:
            body = self.model_dump(exclude={"evidence_id", "created_at", "status",
                                            "invalidated_reason", "cost_credits"})
            self.evidence_id = "ev-" + sha256_json(body)[:16]


class EvidenceBank:
    """Evidence is current only for the exact tree and environment hashes it was produced on."""

    def __init__(self) -> None:
        self.items: dict[str, EvidenceItem] = {}

    def add(self, item: EvidenceItem) -> EvidenceItem:
        self.items.setdefault(item.evidence_id, item)
        return self.items[item.evidence_id]

    def expire_except(self, tree_hash: str, environment_hash: str) -> int:
        expired = 0
        for item in self.items.values():
            if item.status != "current":
                continue
            if item.patch_hash != tree_hash:
                item.status, item.invalidated_reason = "expired", "patch changed"
                expired += 1
            elif item.environment_hash != environment_hash:
                item.status, item.invalidated_reason = "expired", "environment changed"
                expired += 1
        return expired

    def current(self, tree_hash: str, environment_hash: str) -> list[EvidenceItem]:
        return [
            item for item in self.items.values()
            if item.status == "current" and item.patch_hash == tree_hash
            and item.environment_hash == environment_hash
        ]


def render_item(index: int, item: EvidenceItem) -> str:
    basis = "observed" if item.basis == "observed" else "model opinion"
    lines = [f"### E{index} · {FAMILY_NAMES[item.family]} · {basis}", f"Claim: {item.claim}"]
    if item.location:
        lines.append(f"Location: {item.location}")
    if item.observed:
        lines.append(f"Observed:\n{item.observed}")
    if item.expected_if_observed:
        lines.append(f"Expected: {item.expected_if_observed}")
    return "\n".join(lines)


def render_packet(
    items: list[EvidenceItem],
    checkpoint: int,
    token_cap: int,
    count_tokens: Callable[[str], int],
) -> tuple[str, list[str], int]:
    """Common renderer for every arm: same header, same card format, same token cap.

    Items are added in the given order; an item that would exceed the cap is skipped. Returns the
    packet text, the ids actually included, and its token count. No items -> the neutral packet.
    """
    header = PACKET_HEADER.format(checkpoint=checkpoint)
    used = count_tokens(header)
    cards: list[str] = []
    included: list[str] = []
    for item in items:
        card = render_item(len(cards) + 1, item)
        tokens = count_tokens("\n\n" + card)
        if used + tokens > token_cap:
            continue
        cards.append(card)
        included.append(item.evidence_id)
        used += tokens
    # Tokenisation is not additive at boundaries: enforce the cap on the assembled text.
    while cards:
        text = header + "\n\n" + "\n\n".join(cards)
        total = count_tokens(text)
        if total <= token_cap:
            return text, included, total
        cards.pop()
        included.pop()
    text = NEUTRAL_PACKET.format(checkpoint=checkpoint)
    return text, [], count_tokens(text)
