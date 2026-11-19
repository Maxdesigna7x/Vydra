"""Convert frozen Vydra train exports into M4 and phage-only reference packages."""
import argparse
import json
import shutil
import tempfile
from pathlib import Path

import numpy as np

from build_model_profiles import copy_vectors, write_manifest
from model_profiles import PROFILES, verify_manifest


def convert(source_root, destination, profile):
    source = source_root / profile
    final = destination / profile
    if final.exists():
        verify_manifest(final, "m4_manifest.json", profile)
        return
    train = verify_manifest(source, "train_manifest.json", profile)
    matrix = np.load(source / "train_vectors.npy", mmap_mode="r", allow_pickle=False)
    meta = {key: train[key] for key in ("profile", "dimension", "split_sha256", "source_matrix_sha256")}
    with tempfile.TemporaryDirectory(dir=destination) as tmp:
        stage = Path(tmp) / profile
        stage.mkdir()
        if profile != "prostt5":
            base = verify_manifest(source, "manifest.json", profile)
            if any(base[key] != meta[key] for key in meta):
                raise ValueError("Mixed profile sources")
            for relative in base["files"]:
                if not relative.endswith("_prototype_positions.npy"):
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source / relative, target)
            for branch in ("Struct", "Non_Struct"):
                rows = np.load(source / f"{branch}_prototype_positions.npy", allow_pickle=False)
                copy_vectors(stage / f"{branch}_prototypes.npy", matrix, rows)
            write_manifest(stage, "manifest.json", [f for f in stage.rglob("*") if f.is_file()],
                           **meta, window=base["window"], overlap=base["overlap"],
                           pooling=base["pooling"], prototypes_from_train=False)
        with np.load(source / "train_M4.npz", allow_pickle=False) as data:
            rows, labels = data["rows"], data["labels"]
        if len(rows) != 195870 or labels.shape != rows.shape or len(np.unique(rows)) != len(rows):
            raise ValueError("Unexpected M4 training row inventory")
        order = np.argsort(rows)
        copy_vectors(stage / "m4_vectors.npy", matrix, rows[order])
        np.save(stage / "m4_targets.npy", labels[order], allow_pickle=False)
        classes = json.loads((source / "train_labels.json").read_text())["M4_viral_euk_978_clases"]
        if labels.min() < 0 or labels.max() >= len(classes):
            raise ValueError("M4 reference labels outside catalogue")
        (stage / "m4_classes.json").write_text(json.dumps(classes))
        write_manifest(stage, "m4_manifest.json", [stage / n for n in
                       ("m4_vectors.npy", "m4_targets.npy", "m4_classes.json")], **meta)
        stage.rename(final)
    print(f"Verified {final}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.destination).free < 5 * 2**30:
        raise OSError("Allow 5 GiB free for profile conversion")
    for profile in PROFILES:
        convert(args.source, args.destination, profile)
