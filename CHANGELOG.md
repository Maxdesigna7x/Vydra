# Changelog

## 0.4.0 — 2026-10-13

- Phage results now include up to five nearest prototypes, individual source
  annotations, and descriptive agreement/coverage summaries. The previous
  nearest-cluster assignment is preserved, including ties.
- Reports prioritize neighbor evidence and keep whole-cluster context as a
  separate view. Published M4 class metadata is displayed directly.
- CSV outputs use numbered neighbor columns; complete JSON/JSONL retain
  structured evidence. Generic and candidate functional descriptions are
  distinguished without rewriting the source annotation.
- Filtered FASTA export preserves original headers and residues across all
  matching table pages, using a compressed snapshot embedded in the offline HTML.
- Inference and total processing times are recorded in metadata, reports, and
  timing tables.
- `run_vydra_ui.sh` locates Conda, activates the chosen environment, and opens the
  local interface. CPU users can select `VYDRA_CONDA_ENV=vydra-cpu`.
- English and Spanish README guides now follow installation, GUI use,
  interpretation, exports, and troubleshooting. A results screenshot is included.

This update does not retrain models or replace reference embeddings/clusters.
Eukaryotic viruses retain M4 group classification; cellular proteins retain M2
classification. The model/reference downloads remain pinned to their existing
versions. Software regression and export tests do not establish biological accuracy.
