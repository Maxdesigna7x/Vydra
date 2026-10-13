# Informes de inferencia de Vydra

Esta guía describe el informe del motor local, actualizado el 13 de octubre de
2026. No se necesita GPU ni repetir los modelos para abrir un HTML guardado.

## Abrir y explorar

Desde la GUI, selecciona una corrida completada en el historial. También puedes
abrir `informe_inferencia/informe.html` en un navegador moderno. Las corridas de
CLI usan `informe_inferencia_<nombre_del_archivo>/informe.html`.

El informe incluye clasificación jerárquica, conteos por proteína, evidencia de
referencia, tiempos y una tabla filtrable. Los porcentajes se calculan respecto
a la categoría padre indicada; no son abundancias de organismos ni exactitud.

Para fagos, la perspectiva inicial muestra los cinco prototipos más cercanos de
la clase predicha, incluidos otros clusters como alternativas. Solo se muestra
una etiqueta única de género/familia cuando todos los vecinos con ese campo
coinciden. El detalle informa cuántos tienen anotación, cuántos coinciden y cuántos
valores distintos hay. Otra perspectiva muestra el contexto del cluster asignado.
La evidencia de vecinos y el resumen de grupo son fuentes diferentes.

Para virus eucariotas se mantiene la clase M4 y se muestran anotaciones oficiales
de VirDetect-AI Table S1. No hay búsqueda FAISS en esa rama ni en celulares.
Los resúmenes taxonómicos locales opcionales constituyen otra fuente, registrada
como `local_class_summary_reconstructed`; el repositorio de inferencia no necesita
el conjunto de investigación para mostrar el diccionario de clase incluido.

## Filtrar y exportar

Combina filtros de clase estructural, género/familia de referencia, archivo,
longitud y anotación. Ambos botones exportan **todas** las filas que coinciden,
no solo la página visible:

- CSV conserva resultados y evidencia de referencia de la selección.
- FASTA conserva encabezados completos y residuos originales, incluso IDs
  repetidos y el marcador terminal *. Solo normaliza el formato de las líneas.

La exportación FASTA funciona offline porque el HTML incluye una copia comprimida
 de las secuencias. Requiere soporte gzip del navegador y secuencias originales
disponibles para toda la selección. Entradas solo por embeddings y reportes
antiguos sin snapshot no pueden exportar FASTA. El CSV conserva la correspondencia
entre IDs internos, originales y archivos de origen.

## Archivos completos y tiempos

`predicciones_completas.csv` y `.jsonl` conservan los resultados completos de la
GUI. En CSV, los vecinos aparecen en columnas `nearest_neighbors.1.*` a
`nearest_neighbors.5.*`. JSONL conserva sus objetos estructurados.

`secuencias.csv.gz` es una copia adicional de todas las predicciones, comprimida
sin pérdida y sin cadenas de aminoácidos. `--sequence-export csv` solicita la
versión sin comprimir y `--sequence-export none` omite esa copia; no eliminan
los resultados completos ni desactivan FASTA del HTML.

`tiempos.csv`, la metadata y el encabezado del HTML distinguen inferencia,
generación del informe y procesamiento total. Son tiempos de corrida, no por
proteína. Las mediciones históricas ausentes se muestran como no disponibles.

Conserva originales, `original_sequences.jsonl`, manifiesto, predicciones y
metadata. El HTML funciona por sí solo, pero estos archivos permiten auditar
procedencia y regenerarlo. Su tamaño aumenta con las anotaciones y secuencias
comprimidas. Para reportes muy grandes, el navegador también necesita memoria
para filtrar y descomprimir exportaciones.

## Regenerar un informe sin inferencia

En el entorno instalado:

```bash
python vydra_core/inference_report.py --input /ruta/predicciones_completas.jsonl
```

El generador admite CSV/JSONL y un destino `--output`. No acepta resultados de una
corrida aún marcada running/postprocessing. No convierte embeddings en secuencias,
ni añade vecinos ausentes: esa evidencia se obtiene durante la inferencia.

En el proyecto de investigación también existe el wrapper
`scripts/report_inference.py`; el paquete público usa el módulo de `vydra_core`.
El script histórico `run_full_inference.py` tiene un esquema distinto y no es el
punto de entrada recomendado para este informe.

## Interpretación y procedencia

- La confianza softmax describe una decisión del clasificador, no precisión
  calibrada ni probabilidad conjunta de toda la ruta.
- La similitud coseno no es identidad de aminoácidos.
- El umbral FAISS informado corresponde a construcción del cluster; no rechaza
  consultas ni valida taxonomía al superarlo.
- Hypothetical/uncharacterized es una anotación sin función específica, no una
  función conocida predicha por Vydra.
- `asignaciones_taxonomicas.csv` y figuras derivadas conservan el contexto de
  grupos/clases. El selector de vecinos del HTML es otra perspectiva explícita.
- `procedencia.json` registra fuentes, reglas, hash de entrada y tiempos.

Consulta el [diccionario de salidas](../vydra_core/SALIDAS.md) y el
[diseño de evidencia, exportación y tiempos](EVIDENCIA_BIOLOGICA_Y_EXPORTACION.md).
