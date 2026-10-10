# Local inference FAQ

### What does Vydra predict?

Vydra classifies protein sequences through a hierarchy: cellular or viral, then more specific categories. For structural phage proteins it predicts one of ten structural classes. It also provides reference context when available.

### Which input should I choose?

Provide amino-acid sequences in FASTA format. Select a single file or a folder to discover FASTA files recursively. DNA and RNA must first be translated into proteins using an appropriate gene-prediction workflow; Vydra does not translate them.

### Can I analyze multiple samples?

Yes. Keep separate FASTA files for each sample. Original files, folders, IDs, and headers are retained so results can be traced back to their source.

### Where should results be saved?

Choose a new or empty folder outside the input folder. Existing results are not overwritten. Keep original inputs, complete predictions, manifests, run metadata, and the model/reference versions for reproducibility.

### Are my models local?

All inference runs locally. Vydra checks its configured model, bundled files, and cache first. Allow model downloads only permits downloading missing files; it never sends proteins to an inference API. Disable it for fully offline use. Reference banks are installed separately.

### Do I need a GPU?

The current local inference implementation requires a CUDA GPU with GPU FAISS. The CPU setting moves embeddings and classifiers to CPU; FAISS still requires CUDA. Use Check installation to inspect the environment.

### What is batch size?

The number of sequences embedded together. Automatic is the default. A smaller batch may reduce GPU memory use. Runtime also depends on protein lengths, device capacity, and other workloads.

### What happens to invalid or long sequences?

The folder preprocessing records excluded sequences and reasons in secuencias_excluidas.csv; review it before interpreting results. Proteins longer than 2,048 amino acids use overlapping windows whose embeddings are averaged. Fragments can receive predictions but require cautious interpretation.

### What do progress and cancellation mean?

Model loading and embedding generation show their current phase. During classification, progress reports actual processed protein counts. Cancellation retains partial files; retry in a new output folder. Closing the browser tab leaves the job running; stopping the server cancels its active job.

### What files will I receive?

The local workflow writes complete CSV/JSONL predictions, a sequence manifest, exclusion records, summaries, and metadata. Generate inference report adds the interactive HTML report and its supporting exports. The HTML report is interactive and can be opened directly from completed runs.

### Are confidence, similarity, and taxonomy equivalent?

No. Classifier confidence expresses model preference at a particular step. Embedding similarity compares a protein to a reference prototype and is not sequence identity. Genus, family, and host labels describe reference context; they do not certify the taxonomy or host of your query.

### Do percentages measure organism abundance?

They count predicted proteins, not organisms, viral particles, or genomes. Interpret each percentage using its denominator. Conclusions about a genome, species, new virus, or experimental function require additional evidence.

### Does Vydra learn from my input?

Inference uses prepared weights and references. Analyzing a FASTA does not retrain the models or automatically add proteins to the reference banks.
