"""Build installation artifacts from a Vydra research workspace's frozen exports."""
import argparse
import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vydra_core"))
from model_profiles import PROFILES, sha256

NAMES = (
    "M1_L1_viral_vs_cellular", "M2_cellular_3_clases", "M3_viral_phage_vs_euk",
    "M4_viral_euk_978_clases", "M5_phage_structural_vs_non", "M6_structural_10_clases",
)
CHECKPOINTS = ("M1", "M2", "M3", "M4_primary_batch512", "M5", "M6")
ENCODERS = {8: "esm2_t6_8M_UR50D", 35: "esm2_t12_35M_UR50D", 150: "esm2_t30_150M_UR50D"}
SPLIT_HASH = "1fcf101694bec04d8d2153b8b4f7bdd0838120a8bb1544adfd017133b3943021"


def digest_expected(path, expected):
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"Source artifact checksum mismatch: {path}")
    return actual


def write_manifest(work, filename, files, **meta):
    (work / filename).write_text(json.dumps(dict(schema=1, **meta,
        files={str(file.relative_to(work)): sha256(file) for file in sorted(files)}), indent=2) + "\n")


def copy_vectors(destination, matrix, rows):
    data = np.lib.format.open_memmap(destination, mode="w+", dtype="float32",
                                     shape=(len(rows), matrix.shape[1]))
    for start in range(0, len(rows), 8192):
        block = matrix[rows[start:start + 8192]]
        if not np.isfinite(block).all() or not np.allclose(np.linalg.norm(block, axis=1), 1, atol=2e-4):
            raise ValueError("Invalid normalized source vectors")
        data[start:start + len(block)] = block
    data.flush()


def build(args):
    root = args.research
    exp = root / "experiments/esm_superexperimental_20261117"
    split = root / "results/virdetect_compatible_20261021/split"
    manifest = json.loads((split / "split_manifest.json").read_text())
    digest_expected(split / "record_partition.csv", SPLIT_HASH)
    classes_path = split / manifest["class_map"]["path"]
    digest_expected(classes_path, manifest["class_map"]["sha256"])
    labels = json.loads(classes_path.read_text())["tasks"]
    mapping = {name: [str(c["label"]) for c in labels[name[:2]]["classes"]] for name in NAMES}
    artifacts = root / "vydra_core/artifacts"
    profile = args.model
    dimension = PROFILES[profile]["dimension"]
    esm = profile != "prostt5"
    if esm:
        m = int(profile.removeprefix("esm2-").removesuffix("m"))
        slug = f"esm2_{m}m"
        source = args.archive / slug
        source_matrix = source / "embeddings_l2.npy"
        source_sha = digest_expected(source_matrix, (source / "archive.sha256").read_text().split()[0])
    else:
        if not args.full or not args.prost_matrix:
            raise ValueError("ProstT5 requires --full and --prost-matrix")
        source_matrix = args.prost_matrix
        source_sha = digest_expected(source_matrix, "df85c83ed043afa7d450f668c2f6343734ae87db1d15e57a04f61b06a82b41be")
    matrix = np.load(source_matrix, mmap_mode="r", allow_pickle=False)
    if matrix.shape != (1422461, dimension) or matrix.dtype != np.float32:
        raise ValueError("Unexpected source vector matrix")
    def train_rows(head):
        filename = f"indices_{head}_train.npy"
        digest_expected(split / filename, manifest["outputs_sha256"][filename])
        return np.load(split / filename, allow_pickle=False)
    all_rows = np.sort(train_rows("M1"))
    phage = train_rows("M5")
    canonical = Path(manifest["source_stage2_dir"]).parent / "01_corpus/canonical_manifest.csv"
    if not canonical.is_file():
        canonical = args.canonical_manifest
    digest_expected(canonical, "a5d923185c8e65fd19989dfc18260aedc589b83ae607894faddd7d2ce60e0b02")
    target = args.destination
    target.mkdir(parents=True, exist_ok=True)
    dest = target / profile
    if dest.exists():
        raise FileExistsError(f"Destination exists: {dest}")
    minimum = 2**30 + dimension * 4 * (len(all_rows) if args.full else 243126)
    if shutil.disk_usage(target).free < minimum:
        raise OSError(f"Insufficient free space in {target}; require {minimum:,} bytes")
    with tempfile.TemporaryDirectory(dir=target) as temporary:
        work = Path(temporary) / profile
        work.mkdir()
        meta = dict(profile=profile, dimension=dimension, split_sha256=SPLIT_HASH,
                    source_matrix_sha256=source_sha)
        if esm:
            encoder = exp / "weights" / ENCODERS[m]
            digest_expected(encoder / "model.safetensors", (encoder / "model.safetensors.sha256").read_text().split()[0])
            shutil.copytree(encoder, work / "encoder", ignore=shutil.ignore_patterns("*.sha256", "*.log"))
            (work / "heads").mkdir()
            training = exp / "training" / slug
            summary = {r["run_name"]: r for r in json.loads((training / "summary.json").read_text())}
            for name, checkpoint in zip(NAMES, CHECKPOINTS):
                file = training / "models" / f"{checkpoint}.pt"
                metadata = summary[checkpoint]
                if metadata["status"] != "completed":
                    raise ValueError(f"Training incomplete: {checkpoint}")
                digest_expected(file, metadata["checkpoint_sha256"])
                shutil.copy2(file, work / "heads" / f"{name[:2]}.pt")
            (work / "labels.json").write_text(json.dumps(mapping))
            shared = ("cluster_taxonomy_summary.csv", "prototype_sequence_metadata.csv.gz",
                      "viral_euk_class_metadata.csv", "recommended_thresholds_config.json")
            proto = {}
            for branch in ("Struct", "Non_Struct"):
                src = artifacts / f"{branch}_prototype_bank.csv"
                with src.open(newline="") as stream:
                    proto[branch] = list(csv.DictReader(stream))
            requested = {int(r["row_index"]): (r["record_key"], r["seq_id"], r["sequence_sha256"])
                         for records in proto.values() for r in records}
            with canonical.open(newline="") as stream:
                for index, r in enumerate(csv.DictReader(stream)):
                    expected = requested.get(index)
                    if expected and expected != (r["record_key"], r["seq_id"], r["sequence_sha256"]):
                        raise ValueError(f"Mismatched representative identity at row {index}")
            with (artifacts / "canonical_train_metadata.csv").open(newline="") as stream:
                original = {int(r["row_index"]): (r["class_name"], int(r["cluster_id"]))
                            for r in csv.DictReader(stream) if int(r["row_index"]) in requested}
            allowed = set(phage.tolist())
            for branch, records in proto.items():
                rows = np.array([int(r["row_index"]) for r in records], dtype=np.int64)
                if len(set(rows.tolist())) != len(rows) or any(
                    row not in allowed or r["split"] != "train" or int(r["cluster_id"]) < 0
                    or original.get(row) != (r["class_name"], int(r["cluster_id"]))
                    for row, r in zip(rows.tolist(), records)
                ):
                    raise ValueError(f"Representative outside frozen train membership: {branch}")
                shutil.copy2(artifacts / f"{branch}_prototype_bank.csv", work)
                if not args.full:
                    copy_vectors(work / f"{branch}_prototypes.npy", matrix, rows)
                else:
                    positions = np.searchsorted(all_rows, rows)
                    if np.any(positions >= len(all_rows)) or not np.array_equal(all_rows[positions], rows):
                        raise ValueError("Representative missing from shared train matrix")
                    np.save(work / f"{branch}_prototype_positions.npy", positions, allow_pickle=False)
            for file in shared:
                shutil.copy2(artifacts / file, work)
            write_manifest(work, "manifest.json", [f for f in work.rglob("*") if f.is_file()],
                           **meta, window=1022, overlap=255, prototypes_from_train=args.full,
                           pooling="mean_residues_excluding_specials_then_mean_windows_l2")
        if args.full:
            copy_vectors(work / "train_vectors.npy", matrix, all_rows)
            files = [work / "train_vectors.npy", work / "train_labels.json"]
            (work / "train_labels.json").write_text(json.dumps(mapping))
            label_dir = Path(manifest["source_stage2_dir"])
            for name in NAMES:
                head = name[:2]
                rows = train_rows(head)
                positions = np.searchsorted(all_rows, rows)
                if np.any(positions >= len(all_rows)) or not np.array_equal(all_rows[positions], rows):
                    raise ValueError(f"{head} contains a reference outside the M1 training matrix")
                y = np.load(label_dir / f"labels_{head}.npy", allow_pickle=False)[rows]
                if np.any((y < 0) | (y >= len(mapping[name]))):
                    raise ValueError(f"Invalid {head} references")
                file = work / f"train_{head}.npz"
                np.savez(file, rows=positions.astype("int32"), labels=y.astype("int16"))
                files.append(file)
            write_manifest(work, "train_manifest.json", files, **meta)
        work.rename(dest)
    print(dest, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--canonical-manifest", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--model", choices=PROFILES, required=True)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--prost-matrix", type=Path)
    build(parser.parse_args())
