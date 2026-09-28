"""Measured per-dataset figures; missing measurements are never plotted as zero."""
from pathlib import Path

from .io import digest


def plot_comparison(rows, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for dataset in sorted({r["dataset"] for r in rows}):
        group = [r for r in rows if r["dataset"] == dataset]
        labels = [
            f"{r.get('variant', '')} {r['model']} / {r['policy']}".strip() for r in group
        ]
        fig, axes = plt.subplots(2, 2, figsize=(14, max(8, len(group) * .55)))
        for ax, (field, title, scale) in zip(axes.flat, [
            ("success_rate", "Task success (%)", 100),
            ("tokens_per_task", "Tokens / task (online + audit; latest attempt)", 1),
            ("seconds_per_task", "Seconds / task (including grading)", 1),
            ("tokens_per_success", "Tokens / successful task", 1),
        ]):
            for index, row in enumerate(group):
                value = row.get(field)
                if value is None:
                    ax.text(0, index, "N/A — incomplete or unmeasured", va="center", fontsize=8)
                else:
                    ax.barh(index, value * scale, color="#3274a1")
            ax.set_yticks(range(len(labels)), labels, fontsize=8)
            ax.invert_yaxis()
            ax.set_title(title)
            ax.grid(axis="x", alpha=.2)
        fig.suptitle(f"{dataset} • paired runtime evaluation • no pooled benchmark rank")
        fig.tight_layout()
        stem = output / digest(dataset)[:12]
        fig.savefig(stem.with_suffix(".png"), dpi=160)
        fig.savefig(stem.with_suffix(".svg"))
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(12, max(4, len(group) * .45)))
        left = [0] * len(group)
        for role, color in [("policy", "#3274a1"), ("critic", "#e1812c"),
                            ("verifier", "#3a923a"), ("audit", "#9372b2")]:
            values = [r.get(f"known_{role}_tokens", 0) for r in group]
            ax.barh(range(len(group)), values, left=left, label=role, color=color)
            left = [a + b for a, b in zip(left, values)]
        ax.set_yticks(range(len(labels)), labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("Known tokens, latest attempts (partial totals may be incomplete)")
        ax.set_title(f"{dataset} • token consumption by runtime role")
        ax.legend()
        fig.tight_layout()
        fig.savefig(output / f"{digest(dataset)[:12]}-roles.png", dpi=160)
        fig.savefig(output / f"{digest(dataset)[:12]}-roles.svg")
        plt.close(fig)
