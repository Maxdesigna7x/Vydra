# Limite de batch GPU: Vydra 128 y 512 aa

Fecha: `2026-09-21 16:16:14 -0600`  
GPU: **NVIDIA GeForce RTX 3060**, 11.63 GiB  
VRAM ocupada después de cargar encoder, MLP y todos los indices FAISS GPU: **5.28 GiB**

## Semantica de la prueba

Cada repeticion ejecuta el batch completo en orden: tokenizacion + encoder, cascada MLP jerarquica y una consulta FAISS no estructural por secuencia. Las secuencias de cada escenario tienen exactamente la longitud indicada. Hay un warm-up por forma que no entra en la medicion y tres repeticiones medidas.

El checkpoint local ProtT5 se usa como sustituto de rendimiento del encoder ProstT5 por compartir su arquitectura; las rutas biologicas no se interpretan. La consulta FAISS se fija al banco no estructural de 239,561 vectores para que las `X` embeddings lleguen siempre a esa etapa y para medir el caso mas pesado.

## Resultado por batch

| length | batch_size | embedding_per_sequence_s | mlp_per_sequence_s | faiss_per_sequence_s | total_per_sequence_s | sequences_per_second | speedup_throughput_vs_batch1 | peak_gpu_used_gib |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 128 | 1 | 0.0508 | 0.0010 | 0.0039 | 0.0554 | 18.0426 | 1.0000 | 6.0995 |
| 128 | 2 | 0.0367 | 0.0007 | 0.0016 | 0.0391 | 25.5646 | 1.4169 | 6.1191 |
| 128 | 4 | 0.0313 | 0.0003 | 0.0008 | 0.0325 | 30.7263 | 1.7030 | 6.1503 |
| 128 | 8 | 0.0266 | 0.0002 | 0.0004 | 0.0272 | 36.7892 | 2.0390 | 6.3088 |
| 128 | 16 | 0.0248 | 0.0001 | 0.0002 | 0.0252 | 39.7268 | 2.2018 | 6.5375 |
| 128 | 32 | 0.0242 | 0.0000 | 0.0001 | 0.0243 | 41.0813 | 2.2769 | 6.7117 |
| 128 | 64 | 0.0234 | 0.0000 | 0.0001 | 0.0236 | 42.4240 | 2.3513 | 7.5873 |
| 128 | 128 | 0.0233 | 0.0000 | 0.0001 | 0.0235 | 42.6436 | 2.3635 | 8.8105 |
| 128 | 256 | 0.0234 | 0.0000 | 0.0001 | 0.0235 | 42.5544 | 2.3585 | 11.0279 |
| 512 | 1 | 0.1653 | 0.0015 | 0.0034 | 0.1701 | 5.8787 | 1.0000 | 6.2560 |
| 512 | 2 | 0.1554 | 0.0008 | 0.0017 | 0.1581 | 6.3247 | 1.0759 | 6.3456 |
| 512 | 4 | 0.1423 | 0.0004 | 0.0009 | 0.1437 | 6.9609 | 1.1841 | 6.5463 |
| 512 | 8 | 0.1414 | 0.0002 | 0.0004 | 0.1423 | 7.0284 | 1.1956 | 6.9567 |
| 512 | 16 | 0.1381 | 0.0001 | 0.0002 | 0.1384 | 7.2241 | 1.2289 | 8.0430 |
| 512 | 32 | 0.1359 | 0.0001 | 0.0001 | 0.1361 | 7.3472 | 1.2498 | 9.6928 |

## Primer OOM por longitud

| length | batch_size | error |
| --- | --- | --- |
| 512 | 64 | CUDA out of memory. Tried to allocate 2.02 GiB. GPU 0 has a total capacity of 11.63 GiB of which 280.62 MiB is free. Process 5545 has 197.59 MiB memory in use. Process 5800 has 11.65 MiB memory in use. Including non-PyTorch memory, this process has 10.51 GiB memory in use. Of the allocated memory 7.04 GiB is allocated by PyTorch, and 2.17 GiB is reserved by PyTorch but unallocated. If reserved but unallocated memory is large try setting PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True to avoid fragmentation.  See documentation for Memory Management  (https://pytorch.org/docs/stable/notes/cuda.html#environment-variables) |
| 128 | 512 | CUDA out of memory. Tried to allocate 4.06 GiB. GPU 0 has a total capacity of 11.63 GiB of which 2.61 GiB is free. Process 5545 has 197.53 MiB memory in use. Process 5800 has 11.65 MiB memory in use. Including non-PyTorch memory, this process has 8.19 GiB memory in use. Of the allocated memory 5.57 GiB is allocated by PyTorch, and 1.32 GiB is reserved by PyTorch but unallocated. If reserved but unallocated memory is large try setting PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True to avoid fragmentation.  See documentation for Memory Management  (https://pytorch.org/docs/stable/notes/cuda.html#environment-variables) |

## Archivos

- `summary.csv`: medianas por longitud y batch.
- `raw_repeats.csv`: cada repeticion y uso de VRAM.
- `metadata.json`: configuracion exacta.
