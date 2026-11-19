# Model profiles in Vydra

ProstT5 is the default. The GUI **Embedding model** selector and the CLI **--model** option also support ESM‑2 8M, 35M, and 150M. Select **MLP** for the trained decision heads, or **FAISS** to classify the same hierarchy by nearest train reference. Both options retain the historical phage groups and use the selected encoder's vectors for reference evidence.

| Profile | Encoder weights | GPU encoder speed | Embedding dimensions | Installed trained banks and weights¹ |
| --- | ---: | ---: | ---: | ---: |
| ProstT5 | 5.64 GB | 1× | 1024 | Existing install; ≈4.4 GiB for the optional FAISS classifier |
| ESM‑2 8M | 31 MB | ≈97× | 320 | ≈1.5 GiB |
| ESM‑2 35M | 136 MB | ≈31× | 480 | ≈2.3 GiB |
| ESM‑2 150M | 595 MB | ≈8.5× | 640 | ≈3.4 GiB |

¹ ESM full profiles include their encoder, six MLPs, train matrix, reference maps and group annotations. Install only the profiles you want. The 150M had the closest global test accuracy to ProstT5 among the ESM profiles, while the 8M is the lightest. There is no single best model for every branch and sequence length.

Speed represents the median of the six throughput ratios at 75, 150, 256, 512, 768 and 1022 residues on one RTX 3060 (12 GiB), using the maximum stable batch per encoder and length. The figures exclude load, file I/O, MLP and FAISS. Short runs, CPU, and other length distributions have different speed. See the [per-length benchmark CSV](model_profile_benchmark.csv) for the underlying batch sizes and timings. Do not use these ratios to predict complete run time.

On the frozen grouped internal test, exact path accuracy with MLP was 92.08% for ProstT5, 85.95% for 8M, 88.40% for 35M and 91.66% for 150M. These are evaluation results for the tested pipelines, not confidence for an individual prediction. The length-stratified review found that ESM-2 could outperform ProstT5 on long proteins despite its lower global accuracy; the differences depended on length, head and classifier.

## Install and use

Use the standard [Vydra installation](../README.md) and install the **zstd** command. The [model profiles release](https://github.com/Maxdesigna7x/Vydra/releases/tag/model-profiles-v1) provides verified archives. The installer downloads only the selected profile and checks the archive and extracted artifacts before activating it.

```bash
python scripts/install_model_profile.py esm2-8m
./vydra predict --model esm2-8m --fasta proteins.fasta --offline --format json
./vydra predict --model esm2-8m --classifier faiss --fasta proteins.fasta --offline --format json
./vydra gui
```

Repeat the installer with **esm2-35m** or **esm2-150m** for the other models. Installing **prostt5** through this installer adds its optional train bank. The existing ProstT5 encoder and group references still use **vydra download-model** and **vydra download-artifacts**. A completely new ESM installation uses its own references. The GUI updates model availability when reloaded. If the system disk is tight, set **VYDRA_PROFILE_ROOT** to a mounted data disk and pass **--downloads** to the installer for staging. Free space is needed for both archive parts and extraction. The default root is **~/.local/share/vydra/profiles**, with parts under **~/.cache/vydra/profile-downloads**. Installed profiles work offline. Outputs with checkpoints can be resumed by repeating the same command with **--resume**. Keep the same input, model profile, classifier and device. The checkpoint verifies that identity before reusing saved vectors and predictions. **--embedding** remains available for the legacy ProstT5 input format.

## Reference identity and output

MLP confidence is the head's softmax score. FAISS writes the nearest train neighbor cosine in the same per-head score fields. Read **classifier** in the metadata to distinguish them. These scores are not calibrated for comparison across profiles. Reference cosine and group annotation have their usual separate fields. The output and report metadata identify **model_profile** and **classifier**; profile manifests record checksums and the frozen split. An ESM input uses full, overlapping windows of 1022 residues with a 255 residue overlap. Residue pooling excludes special and padding tokens.

The extended bundle stores one training matrix per profile plus M1–M6 row/label mappings. FAISS processes each level in batches with a single active classification index. Group retrieval uses 25,891 structural and 217,235 non-structural representatives taken from the same frozen train groups used by ProstT5. The retained group membership and annotations are inherited; vectors are specific to the encoder.

For maintainers, [build_model_profiles.py](../scripts/build_model_profiles.py) builds reduced or full profiles from a research checkout and the frozen canonical matrix exports. Reduced profiles need only the encoder, MLPs and prototypes, and support MLP with group retrieval. Full profiles are the published bundles. Package sources are the frozen grouped split, canonical embeddings, selected checkpoint per head and representative maps. [ESM‑2 license](ESM2-LICENSE.txt).
