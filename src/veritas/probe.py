"""Evidence-value predictors: repository-grouped cross-validation, calibration, frozen artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import matrix
from .stats import safe_spearman
from .util import sha256_file

MAX_COMPONENTS = 256


def _reducer(n_features: int, n_samples: int):
    if n_features <= 512:
        return []
    return [("pca", PCA(n_components=min(MAX_COMPONENTS, n_samples - 1), random_state=0))]


def make_classifier(kind: str, n_features: int, n_samples: int, seed: int):
    steps = [("scale", StandardScaler()), *_reducer(n_features, n_samples)]
    if kind == "logistic":
        steps.append(("clf", LogisticRegression(C=1.0, max_iter=5000, class_weight="balanced")))
    elif kind == "mlp":
        steps.append(("clf", MLPClassifier(hidden_layer_sizes=(128,), alpha=1e-3,
                                           early_stopping=True, max_iter=500, random_state=seed)))
    elif kind == "gbt":
        steps.append(("clf", HistGradientBoostingClassifier(max_iter=300, random_state=seed)))
    else:
        raise ValueError(kind)
    return Pipeline(steps)


def make_regressor(kind: str, n_features: int, n_samples: int, seed: int):
    steps = [("scale", StandardScaler()), *_reducer(n_features, n_samples)]
    if kind == "gbt":
        steps.append(("reg", HistGradientBoostingRegressor(max_iter=300, random_state=seed)))
    else:
        steps.append(("reg", Ridge(alpha=1.0)))
    return Pipeline(steps)


def pairwise_accuracy(groups: list[str], y: np.ndarray, score: np.ndarray) -> float | None:
    """Within-checkpoint ranking: share of item pairs with different labels ordered correctly."""
    by_group: dict[str, list[int]] = {}
    for i, g in enumerate(groups):
        by_group.setdefault(g, []).append(i)
    right = total = 0.0
    for idx in by_group.values():
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if y[i] == y[j]:
                    continue
                total += 1
                diff = (score[i] - score[j]) * (y[i] - y[j])
                right += 1.0 if diff > 0 else 0.5 if diff == 0 else 0.0
    return right / total if total else None


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    error = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if mask.any():
            error += mask.mean() * abs(y[mask].mean() - p[mask].mean())
    return float(error)


@dataclass
class CVResult:
    model: str
    feature_set: str
    oof_proba: np.ndarray
    oof_value: np.ndarray
    metrics: dict


def cross_validate(records: list[dict], values: np.ndarray, repos: list[str],
                   checkpoints: list[str], model: str, feature_set: str, folds: int,
                   threshold: float, seed: int) -> CVResult:
    X = matrix(records, feature_set)
    y = (values > threshold).astype(int)
    n_groups = len(set(repos))
    if n_groups < 2 or len(set(y)) < 2:
        raise ValueError("need >= 2 repositories and both label classes")
    splitter = GroupKFold(n_splits=min(folds, n_groups))
    proba = np.full(len(y), np.nan)
    value = np.full(len(y), np.nan)
    for train, test in splitter.split(X, y, groups=repos):
        if len(set(y[train])) < 2:
            continue
        clf = make_classifier(model, X.shape[1], len(train), seed).fit(X[train], y[train])
        proba[test] = clf.predict_proba(X[test])[:, 1]
        reg = make_regressor(model, X.shape[1], len(train), seed).fit(X[train], values[train])
        value[test] = reg.predict(X[test])
    ok = ~np.isnan(proba)
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(proba[ok], y[ok])
    calibrated = calibrator.predict(proba[ok])
    metrics = {
        "n": int(ok.sum()), "positives": int(y[ok].sum()),
        "auroc": float(roc_auc_score(y[ok], proba[ok])),
        "auprc": float(average_precision_score(y[ok], proba[ok])),
        "spearman_value": safe_spearman(value[ok], values[ok]),
        "pairwise_accuracy": pairwise_accuracy(
            [c for c, keep in zip(checkpoints, ok) if keep], values[ok], value[ok]
        ),
        "ece_calibrated": expected_calibration_error(y[ok], calibrated),
    }
    return CVResult(model, feature_set, proba, value, metrics)


def fit_artifact(records: list[dict], values: np.ndarray, model: str, feature_set: str,
                 threshold: float, seed: int, redundancy_lambda: float, oof_proba: np.ndarray,
                 path: str | Path) -> str:
    X = matrix(records, feature_set)
    y = (values > threshold).astype(int)
    clf = make_classifier(model, X.shape[1], len(y), seed).fit(X, y)
    reg = make_regressor(model, X.shape[1], len(y), seed).fit(X, values)
    ok = ~np.isnan(oof_proba)
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(oof_proba[ok], y[ok])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": model, "feature_set": feature_set, "classifier": clf, "regressor": reg,
        "calibrator": calibrator, "threshold": threshold,
        "redundancy_lambda": float(redundancy_lambda), "n_features": int(X.shape[1]),
    }, path)
    return sha256_file(path)


class Predictor:
    """A frozen artifact; refuses to load if its hash differs from the recorded one."""

    def __init__(self, path: str | Path, expected_sha256: str):
        actual = sha256_file(path)
        if actual != expected_sha256:
            raise ValueError(f"predictor artifact hash mismatch: {actual} != {expected_sha256}")
        self.sha256 = actual
        self.artifact = joblib.load(path)
        self.feature_set = self.artifact["feature_set"]
        self.redundancy_lambda = self.artifact["redundancy_lambda"]

    @property
    def needs_hidden(self) -> bool:
        return self.feature_set in ("hidden", "full", "full_no_state")

    def predict(self, records: list[dict]) -> tuple[np.ndarray, np.ndarray]:
        X = matrix(records, self.feature_set)
        if X.shape[1] != self.artifact["n_features"]:
            raise ValueError("feature dimension differs from the trained artifact")
        proba = self.artifact["calibrator"].predict(
            self.artifact["classifier"].predict_proba(X)[:, 1]
        )
        return np.asarray(proba), np.asarray(self.artifact["regressor"].predict(X))
