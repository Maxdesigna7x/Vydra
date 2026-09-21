# Viral_Euk Class Metadata

This directory includes `viral_euk_class_metadata.csv`, the class-level metadata used by
the Docker/Hugging Face Space when a query is classified as `viral/euk/<class>`.

## Source

The CSV is exported from the official VirDetect-AI supplementary workbook:

```text
data/originals/Viral_Euk/Supplementary_Tables_VirDetect-AI_v3.xlsx
```

Worksheet:

```text
Table S1 - Description of the 980 eukaryotic viral classes in VirDetect-AI
```

Reference:

```text
VirDetect-AI: a residual and convolutional neural network-based metagenomic tool
for eukaryotic viral protein identification.
Briefings in Bioinformatics, 2025, 26(1), bbaf001.
DOI: https://doi.org/10.1093/bib/bbaf001
```

## Regeneration

From the repository root:

```bash
python scripts/export_virdetect_ai_class_metadata.py \
  --xlsx data/originals/Viral_Euk/Supplementary_Tables_VirDetect-AI_v3.xlsx \
  --out results/viral_euk_class_metadata/virdetect_ai_table_s1_class_metadata.csv

cp results/viral_euk_class_metadata/virdetect_ai_table_s1_class_metadata.csv \
  Vydra_Docker_HF/artifacts/viral_euk_class_metadata.csv
```

## Columns

The exported CSV keeps the Table S1 class dictionary in a backend-friendly schema:

```text
class_number
cluster_rep_sequence_accession
family_label_ncbi_2021
families_in_class_2021
family_label_ncbi_2023
sequences_per_class
sequences_percent
max_length
mean_length
std_length
kmers_per_class
kmers_percent
protein_description
protein_function_class
host
molecule_type
genus
```

`class_number` is the lookup key for the `M4_viral_euk_978_clases` prediction. The
model predicts classes `0` through `977`; the source table also includes the two
VirDetect-AI negative classes `978` and `979` for completeness.

## Runtime Use

`inference_gradio.py` loads this CSV at startup. When a prediction follows the
`viral -> eukariota -> <class>` route, the UI shows this official Table S1 context:

- representative accession;
- NCBI 2021/2023 family labels;
- families present in the class;
- sequence and k-mer counts;
- sequence length summary;
- protein description and function class;
- host, molecule type, and genus.

This is class-level context from the VirDetect-AI class dictionary, not a new
taxonomic validation of the query sequence.
