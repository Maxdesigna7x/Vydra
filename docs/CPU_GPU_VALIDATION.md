# CPU and GPU inference validation

Validated on 2026-10-10 with Python 3.10 and the local pinned ProstT5 encoder, MLP weights, and reference banks.

- Distributed suite: 31 tests passed in the CUDA environment, including CPU/GPU search parity and automatic selection without CUDA or GPU FAISS APIs.
- CPU-only FAISS check: `faiss-cpu` 1.13.2 loaded from an isolated package directory, with `CUDA_VISIBLE_DEVICES` empty. No GPU FAISS APIs were present and PyTorch reported CUDA unavailable.
- Full FASTA inference under that CPU-only configuration succeeded in Automatic mode, including embedding generation, classifiers, structural reference assignment, and the interactive report.
- The same two FASTA proteins completed with explicit CUDA. Hierarchical predictions and assigned cluster IDs agreed: cellular/eukaryota and viral/phage/structural/major_tail (cluster 9). Reference similarity was 0.68847692 on CPU versus 0.68855238 on GPU; encoder precision differs between CPU float32 and GPU float16.
- All 11 real structural/non-structural reference indexes were loaded and searched using CPU FAISS without CUDA.
- Installation diagnostics succeeded without CUDA. Explicit CUDA correctly fails when CUDA or GPU FAISS is unavailable.
- Additional local regression checks: 8 GPU contract/search tests and 5 encoder memory tests passed.

These small checks validate execution paths and reference search, not broad biological equivalence, CPU throughput, or minimum RAM. CPU runs use the same model weights and thresholds; numeric differences may affect borderline predictions. The complete Conda CPU environment specification has not been recreated as part of these checks.

## RAM measurements

Measured with `/usr/bin/time -v`, offline, batch size 1, two short FASTA proteins (one cellular and one structural phage), including encoder loading, classification, and structural reference assignment. Reports were disabled. Both processes exited successfully.

| Backend | Peak process RSS (KiB) | Peak process RSS (GiB) |
|---|---:|---:|
| CPU, CUDA unavailable, faiss-cpu | 7,901,796 | 7.54 |
| CUDA, GPU FAISS | 8,353,056 | 7.97 |

These are process memory measurements on a 32 GB host, not minimum-machine certifications. They exclude other applications and do not bound long-sequence activation memory, very large inputs, or loading all reference branches. The README therefore distinguishes an estimated practical minimum of 16 GB from the recommended 32 GB and does not claim a universal absolute minimum.
