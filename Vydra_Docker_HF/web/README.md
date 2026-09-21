# Vydra Service Page

Pagina estatica de inferencia para Vydra. La UI esta preparada para renderizar resultados desde un objeto JSON con el mismo formato que deberia devolver el servidor.

## Contrato De Resultado

El frontend espera un objeto `InferenceResult`:

```json
{
  "query_id": "Q7X8...A2F3",
  "elapsed_seconds": 14.2,
  "status": "Prediccion completa",
  "prediction": {
    "route_label": "Phage - Estructural",
    "class_key": "major_capsid",
    "class_label": "Major capsid",
    "class_icon": "assets/Structural_Phage.webp",
    "visual_asset": "assets/Parts/Major_Capsid.webp",
    "description": "Proteina estructural mayor de capside."
  },
  "confidence": {
    "value": 0.96,
    "label": "Muy alta"
  },
  "hierarchy": [
    { "level": "Nivel 1", "label": "Viral", "score": 0.999, "color": "coral" },
    { "level": "Nivel 2", "label": "Phage", "score": 0.998, "color": "green" },
    { "level": "Nivel 3", "label": "Estructural", "score": 0.979, "color": "cyan" },
    { "level": "Nivel 4", "label": "Capsid proteins", "score": 0.962, "color": "blue" },
    { "level": "Nivel 5", "label": "Major capsid", "score": 0.955, "color": "violet" }
  ],
  "cluster": {
    "id": "C2034",
    "size": 1248,
    "avg_similarity": 0.87,
    "functions": ["Estructura de capside", "Ensamblaje viral"],
    "organisms": ["Escherichia phage T4", "Mycobacteriophage D29", "+ 25 mas"]
  }
}
```

## Campos

- `query_id`: identificador corto o completo de la secuencia consultada.
- `elapsed_seconds`: tiempo de procesamiento en segundos.
- `status`: texto visible junto al titulo de resultados.
- `prediction.route_label`: ruta principal resumida.
- `prediction.class_key`: clave estable para la clase predicha.
- `prediction.class_label`: nombre visible de la clase.
- `prediction.class_icon`: icono pequeno del pill `Clase: ...`.
- `prediction.visual_asset`: imagen grande de la tarjeta principal.
- `prediction.description`: descripcion breve de la clase o ruta.
- `confidence.value`: confianza entre `0` y `1`.
- `confidence.label`: etiqueta cualitativa visible.
- `hierarchy`: lista ordenada de niveles mostrados en `Top clases jerarquicas`.
- `cluster`: contexto FAISS o biologico asociado.

## Assets De Clase

Las imagenes grandes para `prediction.visual_asset` viven en `assets/Parts/`.

Claves usadas por el placeholder actual:

- `baseplate` -> `assets/Parts/Baseplate.webp`
- `collar` -> `assets/Parts/Collar.webp`
- `head_tail_joining` -> `assets/Parts/Head-Tail_Joining.webp`
- `major_capsid` -> `assets/Parts/Major_Capsid.webp`
- `major_tail` -> `assets/Parts/Major_Tail.webp`
- `minor_capsid` -> `assets/Parts/Minor_Capsid.webp`
- `minor_tail` -> `assets/Parts/Minor_Tail.webp`
- `portal` -> `assets/Parts/Portal.webp`
- `tail_fiber` -> `assets/Parts/Tail_Fiber.webp`
- `tail_sheath` -> `assets/Parts/Tail_Sheath.webp`
- `non_structural` -> `assets/Parts/Non_Struct.webp`

## Integracion Futura

Cuando exista backend, la llamada de inferencia debe transformar la respuesta del servidor a este contrato y llamar a:

```js
renderInferenceResult(serverResult);
applyInferenceState(true);
```

El boton `Generar resultado random` solo usa datos mock para validar como se comporta la UI con distintas clases.
