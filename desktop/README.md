# Vydra Desktop

Vydra Desktop abre la interfaz local de Vydra en una ventana de Electron. El
asistente prepara un entorno privado y los archivos de ProstT5. Las entradas y
los resultados se eligen en cada análisis.

| Modo | Debian/Ubuntu x64 | Windows x64 |
| --- | --- | --- |
| CPU | PyTorch y FAISS en CPU | PyTorch y FAISS en CPU |
| NVIDIA | PyTorch y FAISS en CUDA | PyTorch en CUDA, FAISS en CPU |

Cada computadora con NVIDIA debe tener un controlador compatible con CUDA
12.9 en Linux o CUDA 12.6 en Windows. El entorno
de escritorio tiene sus propias dependencias. Para la primera instalación se
necesita conexión y espacio libre en la carpeta seleccionada. Después de la
preparación se puede ejecutar ProstT5 sin conexión.

## Antes de descargar pesos

1. Trabajar en `desktop/v1`. La copia de investigación está en
   `/home/randy/Tesis/Vydra` y el checkout de distribución en
   `/home/randy/Tesis/Vydra-github`. El worktree de Desktop está en
   `/home/randy/Tesis/Vydra-desktop`.
2. Desde la raíz, ejecutar `npm --prefix desktop test`. Estas pruebas usan
   archivos pequeños y un servidor de prueba en la misma máquina.
3. El workflow **Vydra Desktop** compila los instaladores al actualizar la rama
   y prueba las dependencias CPU y CUDA en máquinas virtuales sin descargar
   modelos. El job CUDA sin una GPU verifica los paquetes y sus importaciones.
   Una segunda prueba en hardware validará la ejecución CUDA.
4. Revisar o volver a ejecutar en [GitHub Actions](https://github.com/Maxdesigna7x/Vydra/actions/workflows/desktop.yml).
   Los jobs abren el asistente empaquetado sin bajar modelos. Los instaladores
   de prueba están en los artefactos de los jobs de compilación.
   Para compilar manualmente en el sistema objetivo, usar Node 22 y ejecutar
   `npm ci`, `npm run stage` y `npm run make -- --arch=x64` desde `desktop/`.
   Linux requiere `fakeroot` y `dpkg`.

## Validación final y publicación

- Usar un Windows y un Debian/Ubuntu limpios. Validar el instalador, los accesos
  directos y una carpeta con espacios en otro disco. Probar CPU y, en hardware
  NVIDIA, una ejecución pequeña con control de dispositivo en el registro.
  Windows debe indicar PyTorch CUDA y FAISS CPU. Linux debe indicar CUDA en
  ambos. En esta PC esperar a que termine la extracción antes de reservar GPU.
- Completar ProstT5 una vez por carpeta. Interrumpir y reabrir con la misma ruta.
  Confirmar que los parciales y los archivos completos se reutilizan. Desconectar
  la red y ejecutar un análisis pequeño con generación de informe.
- Confirmar la CLI existente con `python -m unittest discover -s tests` desde el
  worktree. Verificar también que la GUI independiente sigue funcionando.
- Tras superar las comprobaciones, crear una etiqueta `desktop-v<versión>`
  que coincida con `desktop/package.json`. El workflow compila, genera
  `SHA256SUMS.txt` y adjunta ambos instaladores a un borrador de GitHub Release.
  Revisar el borrador y publicar los dos juntos. Las etiquetas de Desktop son
  independientes de las etiquetas de artefactos de Vydra.

## Reanudar una instalación

Pulsa **Pausar preparación** si necesitas detener la descarga. Vuelve a
elegir la misma carpeta y el mismo modo. Consulta `setup.log` en la
carpeta de datos y el estado de la etapa en `app/<versión>/setup-<modo>.json`.

- Si se interrumpió el entorno, el asistente vuelve a ejecutar su instalación
  y conserva las cachés de paquetes. Las siguientes etapas reutilizan un entorno
  que ya pasó esa parte.
- Si se interrumpió un banco, su archivo `.part` queda en
  `artifacts/artifacts-v1/`. El asistente continúa desde ese tamaño si el
  servidor acepta solicitudes por tramos. Comprueba el tamaño y SHA-256.
- Si se interrumpió ProstT5, se conservan los parciales mantenidos por
  Hugging Face en `models/prostt5-07a6547/`. Los dos bancos y ProstT5 se
  comparten entre los modos de esa misma carpeta.
- Si ya tienes estos archivos de las revisiones publicadas, puedes copiarlos
  al directorio correspondiente antes de preparar la app. El asistente verifica
  los bancos, el peso y el tokenizer antes de aceptarlos. Si hay un error
  persistente de integridad en un archivo previamente copiado, aparta ese
  archivo y vuelve a iniciar el asistente.
- Las salidas de investigación y los embeddings previos quedan fuera de las
  carpetas de preparación. Se requiere únicamente un FASTA pequeño para la
  comprobación final.

## Estado del trabajo

- Base de Vydra `76e36d0`. Implementado el lanzador, el asistente, las dos
  configuraciones de dispositivo y el workflow de construcción y borrador.
- En esta máquina se reservó `/media/randy/3TB5/VydraDesktop-build` para cachés
  y pruebas. La partición es NTFS y permite crear enlaces simbólicos. Todavía
  hay que verificar una instalación completa del entorno Linux allí.
- La preparación inicial instala ProstT5 con MLP. Los perfiles adicionales
  que ya estén en `profiles/` se detectan desde la interfaz. La instalación de
  perfiles opcionales desde la app queda pendiente.
- [Primera matriz completa](https://github.com/Maxdesigna7x/Vydra/actions/runs/44593236218).
  Se generaron ambos instaladores y se importaron las dependencias CPU y CUDA
  de ambos sistemas en una carpeta con espacios. Las pruebas no usaron GPU.
- La prueba ligera local inició y cerró el servidor, con el historial en una
  carpeta de NTFS con espacios. También se probaron las descargas parciales y
  las regresiones del núcleo con CUDA oculta.
- Punto de reanudación. Revisar la última ejecución de GitHub Actions. Si la
  compilación y las comprobaciones ligeras están en verde, avanzar a la
  instalación limpia y a las pruebas NVIDIA y offline.
