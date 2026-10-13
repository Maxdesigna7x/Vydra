#!/usr/bin/env bash
# Open Vydra's local UI using its Conda environment.
# Usage: ./run_vydra_ui.sh [--port 8732] [--no-browser]
# Optional overrides: VYDRA_CONDA_ENV, VYDRA_CONDA_ROOT.
set -eo pipefail

VYDRA_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VYDRA_ENV_NAME="${VYDRA_CONDA_ENV:-vydra}"

if [[ -n "${VYDRA_CONDA_ROOT:-}" ]]; then
    VYDRA_CONDA_BASE="$VYDRA_CONDA_ROOT"
elif [[ -n "${CONDA_EXE:-}" && -x "$CONDA_EXE" ]]; then
    VYDRA_CONDA_BASE="$("$CONDA_EXE" info --base)"
elif command -v conda >/dev/null 2>&1; then
    VYDRA_CONDA_BASE="$(conda info --base)"
else
    for VYDRA_CANDIDATE in "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/miniforge3" /opt/conda; do
        if [[ -f "$VYDRA_CANDIDATE/etc/profile.d/conda.sh" ]]; then
            VYDRA_CONDA_BASE="$VYDRA_CANDIDATE"
            break
        fi
    done
fi

if [[ ! -f "${VYDRA_CONDA_BASE:-}/etc/profile.d/conda.sh" ]]; then
    printf '%s\n' 'No se encontró Conda. Indica su instalación con VYDRA_CONDA_ROOT=/ruta/a/conda.' >&2
    exit 1
fi

source "$VYDRA_CONDA_BASE/etc/profile.d/conda.sh"
if ! conda activate "$VYDRA_ENV_NAME"; then
    printf 'No se pudo activar el entorno %s. Créalo siguiendo environment.yml.\n' "$VYDRA_ENV_NAME" >&2
    exit 1
fi

cd -- "$VYDRA_PROJECT_DIR"
printf 'Iniciando Vydra UI con el entorno %s. Mantén esta terminal abierta; Ctrl+C detiene el servidor.\n' "$VYDRA_ENV_NAME" >&2
exec python "$VYDRA_PROJECT_DIR/vydra" gui "$@"
