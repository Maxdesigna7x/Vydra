# Local graphical interface

Run the interface from the same Python environment used for CLI inference:

```sh
python vydra_cli.py gui
```

From the full repository, use `./vydra gui`. Vydra opens a local browser tab automatically. To open it manually or choose a port:

```sh
./vydra gui --no-browser --port 8732
```

Select a protein FASTA file or a folder (searched recursively), then choose a new or empty output folder outside the input folder. Advanced settings expose the embedding device, batch size, download permission, and report generation. The interface uses the existing inference engine and preprocessing; its server needs no additional web framework. Existing model, artifact, Python, and CUDA/GPU FAISS requirements still apply, including when CPU embeddings are selected. Use **Check installation** to inspect the current environment.

Only one inference runs at a time. Progress shows actual classified protein counts when available; model loading and embedding generation show their phase without an estimated percentage. Logs and recent runs are available on the same page. Closing the browser tab leaves inference running. Keep the server terminal open; Ctrl+C stops the server and cancels its active inference. Cancellation retains partial files, so retry in a new output folder.

The server listens only on `127.0.0.1`. Run history and logs are stored in `~/.local/share/vydra/gui`; override with `--state-dir PATH`. If the server exits unexpectedly, a surviving worker continues, and a restarted interface can read its state. Cancellation of that surviving worker is unavailable from the restarted server.

The optional report uses the interactive design: stacked bars, hierarchy diagram, category bars, reference distribution, and filterable protein tables. It embeds the current run’s data and works offline.

The desktop interface fits its main workflow into one viewport. Input and output share a row; advanced settings, execution logs, and the English usage FAQ open in dialogs. Long history lists scroll within their panel. Small screens use a stacked, scrollable layout to keep fields readable. Hover or focus a control for its help tooltip. The usage FAQ is adapted from the project’s biologist FAQ; see the bundled English [usage FAQ](../docs/GUI_FAQ.md).

Click a completed run in Recent runs to open its saved HTML results report directly in the same tab. Report images and downloads are served from that run’s results folder. Runs without a generated report continue to show their status and log. Use the browser Back button to return to the inference interface.

Local models are used automatically; Check installation is optional. The Allow model downloads checkbox permits downloading only missing model files, which are then used locally. It does not send protein sequences to a remote service. Uncheck it to prohibit downloads. See the main README for GPU and hybrid CPU requirements.
