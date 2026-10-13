# Phage Cluster Metadata

`cluster_taxonomy_summary.csv` is the biological dictionary used by the local CLI and GUI for phage predictions after FAISS cluster assignment.

## Source

The file is generated from:

```text
data/metadata/phage_sequence_metadata.csv
data/03_splits_clustering/FAISS_clustering/Struct_id_cluster_map.csv
data/03_splits_clustering/FAISS_clustering/Non_Struct_id_cluster_map.csv
data/03_splits_clustering/FAISS_clustering/recommended_thresholds_config.json
```

The source metadata comes from the clean phage FASTA files:

```text
data/02_clean_fasta/phage_struct/*.fasta
data/02_clean_fasta/phage_non_struct/phage_non_struct.fasta
```

## Regeneration

From the repository root:

```bash
python scripts/parse_phage_fasta_metadata.py \
  --out data/metadata/phage_sequence_metadata.csv

python scripts/evaluate_current_faiss_cluster_taxonomy.py \
  --metadata data/metadata/phage_sequence_metadata.csv \
  --out-dir results/faiss_biological_calibration \
  --threshold-config data/03_splits_clustering/FAISS_clustering/recommended_thresholds_config.json

cp results/faiss_biological_calibration/current_threshold_cluster_taxonomy_summary.csv \
  vydra_core/artifacts/cluster_taxonomy_summary.csv
```

## Meaning

These rows are Vydra cluster annotations, not externally curated class labels.
Each row summarizes one FAISS cluster within a phage branch/class:

```text
dataset_type
class_name
cluster_id
```

The table includes dominant taxonomy fields, purity/coverage, representative
sequence metadata, compact lists of values observed in the cluster, and sequence
length statistics.

The UI reports this as cluster-level context. It should not be interpreted as a
direct taxonomic validation of the query sequence.

## Nearest-reference metadata

`prototype_sequence_metadata.csv.gz` supplies source annotations for the exact
deployed prototype IDs. It is joined by dataset, class and sequence ID and is
separate from this cluster dictionary. Generate it with
`python scripts/export_prototype_metadata.py`; distribute the CSV and
`prototype_metadata_provenance.json` with the bundle. The latter records source
hashes and missing annotations. Missing fields are retained as unavailable.

Inference retrieves up to five prototypes across the predicted class, including
alternative clusters, while preserving the previous nearest-cluster assignment.
The HTML prioritizes these individual references; the cluster representative and
summary remain secondary context. See the
[evidence guide](../../docs/EVIDENCIA_BIOLOGICA_Y_EXPORTACION.md).
