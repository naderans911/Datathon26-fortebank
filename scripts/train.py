"""Train the temporal violation scorer from cached features + timestamp labels.

    python scripts/extract_features.py DATA_DIR
    python scripts/train.py LABELS_FILE [--types config/event_types.json]

event_types.json (optional, filled after looking at the clips):
    {"video_stem": {"11": "leave_workplace", "40": "phone_in_cash_zone"}}
Type names must exist in config/violation_types.json.

Leave-videos-out cross-validation picks the threshold: zero missed violation
videos first (the bank says a miss is unacceptable), then fewest false alarms.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.ml.dataset import load_labels, norm_stem  # noqa: E402
from backend.app.ml.scorer import SCORER_FILE, build_matrix, peaks, smooth  # noqa: E402


def make_model(kind: str, C: float = 1.0, pca: int = 16):
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    reduce = [PCA(n_components=pca, random_state=0)] if pca else []
    if kind == "hgb":
        from sklearn.ensemble import HistGradientBoostingClassifier
        return make_pipeline(*reduce, HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                                                     class_weight="balanced", random_state=0))
    return make_pipeline(StandardScaler(), *reduce, LogisticRegression(C=C, class_weight="balanced", max_iter=3000))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", type=Path)
    ap.add_argument("--types", type=Path, default=ROOT / "config" / "event_types.json")
    ap.add_argument("--pos-tol", type=float, default=4.0, help="frames within +-N s of a label are positive")
    ap.add_argument("--ignore-tol", type=float, default=6.0, help="frames in (pos, ignore] are dropped")
    ap.add_argument("--model", choices=["lr", "hgb"], default="lr")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--C", type=float, default=1.0, help="inverse regularisation for --model lr")
    ap.add_argument("--pca", type=int, default=16, help="PCA components before the classifier (0 = off)")
    args = ap.parse_args()

    labels = load_labels(args.labels)
    types = json.loads(args.types.read_text(encoding="utf-8")) if args.types.is_file() else {}
    cache = sorted((ROOT / "cache" / "features").glob("*.json"))
    videos = []
    for path in cache:
        data = json.loads(path.read_text(encoding="utf-8"))
        stem = norm_stem(data["video"])
        if stem not in labels:
            print(f"skip {stem}: no label row")
            continue
        ts = data["timestamps"]
        X = build_matrix(data["features"], ts)
        stamps = labels[stem]
        dist = np.array([min((abs(t - s) for s in stamps), default=1e9) for t in ts])
        y = (dist <= args.pos_tol).astype(int)
        keep = ~((dist > args.pos_tol) & (dist <= args.ignore_tol))
        nearest = [min(stamps, key=lambda s: abs(s - t)) if stamps else None for t in ts]
        videos.append({"stem": stem, "X": X, "y": y, "keep": keep, "ts": ts, "stamps": stamps, "nearest": nearest})
    if len(videos) < 4:
        sys.exit("Need at least 4 labelled videos with cached features")
    print(f"{len(videos)} videos, {sum(bool(v['stamps']) for v in videos)} with violations")

    # ---- leave-videos-out CV -------------------------------------------------
    from sklearn.model_selection import GroupKFold
    groups = np.arange(len(videos))
    oof = [None] * len(videos)
    folds = GroupKFold(n_splits=min(args.folds, len(videos)))
    for train_idx, test_idx in folds.split(groups, groups=groups):
        Xtr = np.vstack([videos[i]["X"][videos[i]["keep"]] for i in train_idx])
        ytr = np.concatenate([videos[i]["y"][videos[i]["keep"]] for i in train_idx])
        if ytr.min() == ytr.max():
            continue
        model = make_model(args.model, args.C, args.pca).fit(Xtr, ytr)
        for i in test_idx:
            oof[i] = smooth(model.predict_proba(videos[i]["X"])[:, 1], 1)

    def evaluate(thr: float) -> dict:
        tp = fn = fp = tn = 0
        errors, extra = [], 0
        for v, prob in zip(videos, oof):
            if prob is None:
                continue
            events = peaks(prob, v["ts"], thr)
            flagged = bool(events)
            if v["stamps"]:
                tp += flagged
                fn += not flagged
                for s in v["stamps"]:
                    if events:
                        errors.append(min(abs(v["ts"][e["peak"]] - s) for e in events))
                extra += sum(1 for e in events if min(abs(v["ts"][e["peak"]] - s) for s in v["stamps"]) > 5)
            else:
                fp += flagged
                tn += not flagged
        return {"thr": round(thr, 3), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
                "video_acc": (tp + tn) / max(tp + tn + fp + fn, 1),
                "median_time_err": float(np.median(errors)) if errors else None,
                "spurious_events_in_violation_videos": extra}

    grid = [evaluate(t) for t in np.arange(0.05, 0.96, 0.025)]
    best_fn = min(g["fn"] for g in grid)
    candidates = [g for g in grid if g["fn"] == best_fn]
    best = min(candidates, key=lambda g: (g["fp"], g["spurious_events_in_violation_videos"], -g["thr"]))
    # Small safety margin towards recall for an unseen camera angle.
    threshold = max(0.05, best["thr"] - 0.05)
    print("CV grid (thr, fn, fp, acc, time_err):")
    for g in grid[::4]:
        print(f"  {g['thr']:.2f}  fn={g['fn']} fp={g['fp']} acc={g['video_acc']:.2f} err={g['median_time_err']}")
    print("Chosen:", best, "-> deployed threshold", round(threshold, 3))

    # ---- final fit -------------------------------------------------------------
    X = np.vstack([v["X"][v["keep"]] for v in videos])
    y = np.concatenate([v["y"][v["keep"]] for v in videos])
    model = make_model(args.model, args.C, args.pca).fit(X, y)

    type_model, type_names = None, []
    rows, names = [], []
    for v in videos:
        mapping = {float(k): t for k, t in types.get(v["stem"], {}).items()}
        for row, label, nearest in zip(v["X"], v["y"], v["nearest"]):
            if label and nearest is not None:
                name = mapping.get(float(nearest)) or next((t for k, t in mapping.items() if abs(k - nearest) <= 1.5), None)
                if name:
                    rows.append(row)
                    names.append(name)
    if len(set(names)) >= 2:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        type_model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=3000, class_weight="balanced"))
        type_model.fit(np.vstack(rows), names)
        type_names = sorted(set(names))
        print("Type head classes:", {n: names.count(n) for n in type_names})
    default_rule = names and max(set(names), key=names.count) or None

    import joblib
    (ROOT / "models").mkdir(exist_ok=True)
    joblib.dump({"model": model, "threshold": threshold, "type_model": type_model,
                 "default_type": default_rule, "pos_tol": args.pos_tol, "kind": args.model},
                ROOT / "models" / SCORER_FILE)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "train_report.json").write_text(json.dumps(
        {"chosen": best, "threshold": threshold, "grid": grid, "types": type_names, "default_type": default_rule},
        indent=1), encoding="utf-8")
    print(f"Saved models/{SCORER_FILE}")


if __name__ == "__main__":
    main()
