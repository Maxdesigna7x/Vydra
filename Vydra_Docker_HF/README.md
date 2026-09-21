---
title: Vydra Protein Classifier
emoji: 🧬
colorFrom: blue
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Vydra Docker Space

Interfaz web y backend Docker para ejecutar inferencia de Vydra en Hugging Face Spaces. La pagina sirve una UI custom en HTML/CSS/JS y un backend Python con FastAPI que reutiliza la inferencia jerarquica existente: ProstT5, seis MLPs, FAISS estructural y contexto biologico de cluster.

## Que Hace

- Recibe secuencias proteicas en FASTA.
- Extrae embeddings con `Rostlab/ProstT5`.
- Ejecuta la cascada jerarquica de clasificadores MLP.
- Asigna cluster FAISS cuando aplica.
- Muestra metadata oficial de clase VirDetect-AI cuando la prediccion cae en Viral_Euk.
- Muestra metadata enriquecida de clusters Vydra cuando la prediccion cae en phage.
- Muestra una secuencia a la vez con navegacion `Anterior` / `Siguiente`.
- Resalta en el esquema jerarquico la ruta tomada por la secuencia actual.
- Permite descargar todos los resultados en CSV.
- Soporta tema claro/oscuro e idioma ES/EN segun preferencias del navegador, con opcion manual.

## Estructura

```text
Vydra_Docker_HF/
  Dockerfile
  app.py                 # FastAPI + frontend estatico + API de inferencia/jobs
  inference_gradio.py    # Logica base reutilizada desde HF_Space/app.py
  requirements.txt
  web/                   # Interfaz HTML/CSS/JS y assets
  artifacts/             # Artefactos requeridos por inferencia
  models/                # Pesos MLP
  jobs/                  # CSVs generados en runtime, ignorado por git
```

## Endpoints

- `GET /`: interfaz web.
- `GET /health`: healthcheck y estado de warmup.
- `POST /api/infer`: inferencia sincronica desde JSON `{ "sequence_or_fasta": "..." }`.
- `POST /api/infer-file`: inferencia sincronica desde archivo FASTA/TXT.
- `POST /api/jobs`: crea job asincronico desde JSON.
- `POST /api/jobs-file`: crea job asincronico desde archivo FASTA/TXT.
- `GET /api/jobs/{job_id}`: consulta progreso y resultados.
- `GET /api/jobs/{job_id}/download`: descarga CSV final.

La UI usa los endpoints de jobs para poder mostrar progreso de ProstT5.

## Artefactos

Estos archivos deben existir:

```text
artifacts/label_classes.json
artifacts/Struct_prototype_bank.pt
artifacts/Non_Struct_prototype_bank.pt
artifacts/Struct_prototype_bank.csv
artifacts/Non_Struct_prototype_bank.csv
artifacts/Struct_id_cluster_map.csv
artifacts/Non_Struct_id_cluster_map.csv
artifacts/cluster_taxonomy_summary.csv
artifacts/viral_euk_class_metadata.csv
artifacts/recommended_thresholds_config.json
models/mlp_weights/*.pth
```

La asignacion FAISS usa bancos de prototipos/medoids compactos, no los embeddings completos de referencia. Cada banco `.pt` contiene `class_name -> {cluster_ids, seq_ids, centroids/prototypes}` y se indexa con FAISS `IndexFlatIP` despues de normalizar los vectores. El `cluster_nearest_seq_id` reportado corresponde al prototipo mas cercano.

`artifacts/cluster_taxonomy_summary.csv` es el diccionario biologico de clusters Vydra de phage. Incluye dominantes, purezas, coberturas, representante del cluster, listas compactas de familias/generos/hosts/productos y estadisticas de longitud. Se genera desde `data/metadata/phage_sequence_metadata.csv` y los mapas FAISS con `scripts/evaluate_current_faiss_cluster_taxonomy.py`.

`artifacts/viral_euk_class_metadata.csv` se exporta desde la Table S1 oficial de VirDetect-AI (`Supplementary_Tables_VirDetect-AI_v3.xlsx`) y se usa como diccionario biologico de las clases `viral/euk/0` a `viral/euk/977`. El proceso de regeneracion esta documentado en `artifacts/VIRAL_EUK_CLASS_METADATA.md`.

## Ejecucion Local Sin Docker

Desde esta carpeta:

```bash
uvicorn app:app --host 0.0.0.0 --port 7860 --reload
```

Abrir:

```text
http://localhost:7860
```

Con `--reload`, los cambios Python recargan el servidor. Cambios HTML/CSS/JS requieren refrescar el navegador.

## Publicar La App Con Cloudflared

Para exponer la app temporalmente en internet desde tu maquina local, abre dos terminales.

Primero instala `cloudflared`:

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb && sudo dpkg -i cloudflared.deb
```

Luego levanta Vydra en una terminal:

```bash
cd /home/randy/Tesis/Vydra/Vydra_Docker_HF
source ~/miniconda3/etc/profile.d/conda.sh
conda activate vydra
uvicorn app:app --host 0.0.0.0 --port 7860
```

En otra terminal, crea el tunnel hacia el server local:

```bash
cloudflared tunnel --url http://localhost:7860
```

Cloudflared imprime una URL publica temporal, por ejemplo:

```text
https://soldier-tap-cst-humor.trycloudflare.com
```

Esa URL cambia cada vez que reinicias el tunnel. La app debe estar corriendo antes de ejecutar `cloudflared`, porque el tunnel solo expone el server local que ya esta escuchando en `7860`.

## Ejecucion Local Con Docker

```bash
docker build -t vydra-space .
docker run --rm -p 7860:7860 vydra-space
```

Abrir:

```text
http://localhost:7860
```

Si cambias archivos y usas Docker, debes reconstruir la imagen.

## Subir A Hugging Face Spaces

Este repo ya apunta a:

```text
https://huggingface.co/spaces/RandyA7X/Vydra
```

Flujo recomendado:

```bash
cd /home/randy/Tesis/Vydra/Vydra_Docker_HF
git status
git add .
git commit -m "Update Vydra Docker Space"
git push
```

Los archivos grandes deben ir por Git LFS. Este repo ya trackea `*.pt`, `*.pth` y `*.webp` en `.gitattributes`.

## Notas De Desarrollo

- El backend hace warmup de modelos al arrancar para reducir latencia de la primera inferencia.
- ProstT5 procesa secuencias ordenadas por longitud y ajusta batch size segun longitud.
- `jobs/` se genera en runtime y no debe subirse.
- `__pycache__/` no debe subirse.
- El CSV descargable se genera por job en `jobs/`.

## Hardware

CPU Basic puede funcionar, pero ProstT5 puede tardar bastante y consumir memoria. Si la demo queda lenta o falla por memoria, conviene probar GPU en Hugging Face Spaces.
