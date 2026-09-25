"""Version the implementations as well as model settings; never silently reuse stale calibration."""

from pathlib import Path

from .io import digest, file_hash


def implementation(names):
    return {name: file_hash(Path(__file__).with_name(name)) for name in names}


def critic_identity(config, critic=None):
    settings = (
        critic.metadata if hasattr(critic, "metadata") else config.critic.model_dump(mode="json")
    )
    return "v2:" + digest(
        {
            "settings": settings,
            "implementation": implementation(["models.py", "critic.py"]),
        }
    )


def verifier_identity(config):
    return "v2:" + digest(
        {
            "settings": config.verifier.model_dump(mode="json"),
            "probes": config.probes,
            "sandbox": config.sandbox.model_dump(mode="json"),
            "graph": config.graph.model_dump(mode="json") if config.run.policy == "graph" else None,
            "implementation": implementation(
                ["models.py", "verifier.py", "sandbox.py", "worker.py"]
                + (["graph.py", "graph_verifier.py"] if config.run.policy == "graph" else [])
            ),
        }
    )
