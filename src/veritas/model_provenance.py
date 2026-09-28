"""Optional endpoint telemetry and request-bound Ed25519 revision attestations.

The custom veritas_* response fields require a cooperating server. An ordinary
model name or system_fingerprint is recorded, never treated as a signed revision.
"""

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field

from .io import canonical, digest
from .schema import StrictModel


class ResourceUsage(StrictModel):
    cpu_seconds: float | None = Field(default=None, ge=0)
    gpu_seconds: float | None = Field(default=None, ge=0)
    source: str = Field(min_length=1)


def record_response(config, data, payload, nonce, content, usage):
    usage.provenance = {
        "request_id": data.get("id"), "reported_model": data.get("model"),
        "system_fingerprint": data.get("system_fingerprint"),
        "sampling_seed_requested": config.sampling_seed,
        "sampling_seed_honored": None, "revision_verified": False,
    }
    if data.get("veritas_usage") is not None:
        resource = ResourceUsage.model_validate(data["veritas_usage"])
        usage.cpu_seconds, usage.gpu_seconds = resource.cpu_seconds, resource.gpu_seconds
        usage.resource_source = "provider_reported: " + resource.source
    if config.attestation is None:
        return
    signed = data.get("veritas_attestation")
    if not isinstance(signed, dict):
        raise ValueError("Required server revision attestation is missing")
    body = {key: value for key, value in signed.items() if key != "signature"}
    expected = {"revision": config.attestation.revision, "nonce": nonce,
                "request_sha256": digest(payload), "content_sha256": digest(content)}
    if body != expected:
        raise ValueError("Server attestation does not match revision/request/response")
    try:
        signature = base64.b64decode(signed["signature"], validate=True)
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(
            config.attestation.public_key_hex)).verify(signature, canonical(body))
    except Exception as exc:
        raise ValueError("Invalid server attestation signature") from exc
    usage.provenance.update(revision_verified=True, revision=body["revision"],
                            attestation=signed, attestation_sha256=digest(signed))
