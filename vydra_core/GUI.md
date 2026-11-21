# Local graphical interface

After installing the environment, the root launcher activates Conda and opens
the interface automatically:

```sh
./run_vydra_ui.sh
# CPU-only installation:
VYDRA_CONDA_ENV=vydra-cpu ./run_vydra_ui.sh
```

The default environment is `vydra`. Use `VYDRA_CONDA_ROOT=/path/to/conda` if the
launcher cannot locate Conda. Keep its terminal open; Ctrl+C stops the server.

Alternatively, from `vydra_core/` inside an activated environment:

```sh
python vydra_cli.py gui
```

From the full repository, use `./vydra gui`. Vydra opens a local browser tab automatically. To open it manually or choose a port:

```sh
./vydra gui --no-browser --port 8732
```

Open **New task**, select a protein FASTA file or a folder (searched recursively), then choose a new or empty output folder outside the input folder. Advanced settings expose the inference device, batch size, download permission, and report generation. The interface uses the existing inference engine and preprocessing; its server needs no additional web framework. CPU inference requires PyTorch and CPU FAISS; CUDA inference requires CUDA-enabled PyTorch and GPU FAISS. Automatic selects a compatible GPU or CPU for all stages. Use **Check installation** to inspect the current environment.

**Runs** groups the active, queued, and completed tasks. Submit another task with **Add to queue**. Tasks run one at a time in submission order. Each active card shows elapsed time, progress and stage ETA when available. Select a card for details, execution logs, cancellation or resumption. Closing the browser tab leaves inference running. Keep the server terminal open; Ctrl+C stops the server and cancels its active inference. Cancellation retains checkpoints. Use **Resume run** to reuse confirmed work with the original profile and classifier.

The server listens only on `127.0.0.1`. Run history and logs are stored in `~/.local/share/vydra/gui`; override with `--state-dir PATH`. If the server exits unexpectedly, a surviving worker continues, and a restarted interface can read its state. Cancellation of that surviving worker is unavailable from the restarted server.

The optional report uses the interactive design: stacked bars, hierarchy diagram, category bars, reference distribution, and filterable protein tables. It embeds the current run’s data and works offline.

Phage details prioritize five nearest prototypes with their individual annotations;
cluster summaries remain available as secondary context. The table exports all
filtered rows as CSV or original FASTA, across pages. Reports show inference and
total processing times. See the [evidence and export guide](../docs/EVIDENCIA_BIOLOGICA_Y_EXPORTACION.md).

The browser and Desktop use the same interface. The main workflow fits into one viewport. Input and output share a row; advanced settings, execution logs, and the English usage FAQ open in dialogs. Long history lists scroll within their panel. Small screens use a stacked, scrollable layout to keep fields readable. Hover or focus a control for its help tooltip. The usage FAQ is adapted from the project’s biologist FAQ; see the bundled English [usage FAQ](../docs/GUI_FAQ.md).

Click **Report** on a completed run to open its saved HTML results in the same window or tab. Report images and downloads are served from that run’s results folder. Runs without a generated report continue to show their status and log. Use the home icon in the report to return to **Runs**.

Local models are used automatically; Check installation is optional. The Allow model downloads checkbox permits downloading only missing model files, which are then used locally. It does not send protein sequences to a remote service. Uncheck it to prohibit downloads. See the main README for GPU and CPU requirements.

## Model profiles

Use **Embedding model** to choose an installed encoder. M4 compares MLP and FAISS using the selected profile’s reference bank. Sizes are encoder weight sizes. Speed is measured with full batches on an RTX 3060; see the link below for scope. [Profile setup and benchmark scope](../docs/MODEL_PROFILES.md).

Desktop adds a setup wizard and update notices. Browser users prepare their own
Python environment and model profiles. The browser installation defaults to a
separate history directory from Desktop.
