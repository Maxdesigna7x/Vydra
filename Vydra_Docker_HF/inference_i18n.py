"""English/Spanish presentation; scientific IDs and persisted result fields stay stable."""
import argparse
import re
import sys

TEXT = {
 'Vydra · Informe de inferencia': 'Vydra · Inference report',
 'Los nombres virales dominantes se presentan como contexto de las referencias. Viral_Euk puede usar el resumen local de clases reconstruido después de la inferencia; consulte procedencia.json. Las etiquetas taxonómicas se heredan de grupos de referencia, no de validación independiente por proteína.': 'Dominant viral names provide reference context. Viral_Euk may use the local class summary reconstructed after inference; see procedencia.json. Taxonomic labels are inherited from reference groups, rather than independently validated for each protein.',
 'Cascada jerárquica': 'Classification hierarchy',
 'Árbol de clasificación con cajas y flechas': 'Classification tree with boxes and arrows',
 'Cada caja cuenta proteínas que siguieron una rama de clasificación. El porcentaje se calcula dentro de su caja padre: por ejemplo, el porcentaje de fagos se calcula sobre las proteínas virales. No representa exactitud ni confianza. Las clases finas se consultan en el selector.': 'Each box counts proteins that followed a classification branch. Percentages use the parent box as the denominator: for example, the phage percentage is calculated among viral proteins. These are not accuracy or confidence scores. Use the selector to inspect fine classes.',
 'Reparto dentro de cada padre': 'Distribution within each parent',
 'Barras por padre, incluidas las diez clases estructurales': 'Parent distributions, including all ten structural classes',
 'Ámbito': 'Scope', 'Clase padre': 'Parent class', 'Control de similitud FAISS': 'FAISS similarity check',
 'esta tabla adicional': 'this additional table',
 'las separa en below_threshold. No confundir etiquetas heredadas con asignación que cumple el umbral.': 'separates them as below_threshold. An inherited label does not mean the assignment meets the threshold.',
 'El criterio es': 'The criterion is',
 'similitud coseno ≥ umbral informado por clase': 'cosine similarity ≥ the reported class threshold',
 ', entre embeddings ProstT5 normalizados y su prototipo más cercano; no es identidad de aminoácidos. El motor devuelve el vecino más cercano sin rechazar por este umbral: aquí se compara después. Son los umbrales de la configuración de referencia informados por la corrida, no un filtro taxonómico validado para proteínas nuevas.': ', between normalized ProstT5 embeddings and the nearest prototype; this is not amino-acid identity. The engine returns the nearest neighbor without rejecting assignments at this threshold; the comparison is retrospective. These are reference configuration thresholds recorded by the run, not a taxonomic filter validated for new proteins.',
 'Clase': 'Class', 'Umbral coseno': 'Cosine threshold', 'Proteínas': 'Proteins', 'Cumplen': 'Passing', '% cumplen': '% passing', 'Mediana coseno': 'Median cosine similarity',
 'Clases sin proteínas: umbral mostrado desde la configuración actual; no hay comparación observada.': 'For classes with no proteins, the threshold comes from the current configuration; no observed comparison is available.',
 'Distribución de similitud frente a los umbrales': 'Similarity distribution and thresholds',
 'La mediana indica dónde cae la mitad de las similitudes de cada clase. Cumplir el umbral no garantiza resolución de género o familia: también se requiere una referencia con metadatos suficientemente homogéneos.': 'The median is the midpoint of the similarity values in each class. Passing the threshold does not guarantee genus or family resolution; the reference must also have sufficiently homogeneous metadata.',
 'Descargar umbrales y conteos por clase': 'Download thresholds and class counts',
 'Resolución taxonómica': 'Taxonomic resolution',
 'Cada barra indica qué proporción de proteínas tiene ese nivel como mejor etiqueta taxonómica disponible en su referencia. Las categorías son exclusivas: cada proteína cuenta una sola vez. Un género puede conocerse sin que la familia cumpla los criterios de cobertura y pureza. Género y familia en los rankings son conteos independientes y pueden solaparse.': 'Each bar shows the share of proteins whose reference has that best available taxonomic level. Categories are exclusive: each protein counts once. A genus may be available even when its family does not meet coverage and purity criteria. Genus and family rankings are counted independently and may overlap.',
 'Top 10 y distribución completa': 'Top 10 and full distribution', 'Rango': 'Rank', 'Género': 'Genus', 'Familia': 'Family', 'Nombre viral de referencia': 'Reference viral name',
 'La distribución muestra cómo se reparten las etiquetas de referencia entre las proteínas. Top 1 es el porcentaje que reúne la etiqueta más frecuente; Top 10 suma las diez más frecuentes. Ambos porcentajes usan solo las proteínas con etiqueta en el rango elegido. Por ejemplo, Top 10 = 70 % significa que esas diez etiquetas reúnen el 70 % de las proteínas con etiqueta; no el 70 % de todas las proteínas analizadas.': 'The distribution shows how reference labels are distributed across proteins. Top 1 is the share assigned to the most frequent label; Top 10 combines the ten most frequent labels. Both percentages use only proteins with a label at the selected rank. For example, Top 10 = 70 % means those ten labels account for 70 % of labeled proteins, rather than 70 % of all analyzed proteins.',
 'Cada sector corresponde a una etiqueta; todos se conservan. Pase el cursor para ver nombre y conteo. Sin etiqueta usa gris. La tabla permite revisar sectores pequeños.': 'Each slice represents a label; all labels are retained. Hover to see the name and count. Unlabeled proteins are gray. Use the table to inspect small slices.',
 'La columna de porcentaje acumulado suma las etiquetas desde la más frecuente hasta cada fila. Siempre llega al 100 % al incluir todas las etiquetas con asignaciones. Una subida rápida indica que pocas etiquetas concentran muchas asignaciones; sirve para describir concentración, no confianza ni abundancia de organismos. Las antiguas curvas de taxones ordenados se han retirado: esta tabla conserva sus datos.': 'The cumulative percentage sums labels from the most frequent down to each row. It reaches 100 % after all assigned labels are included. A rapid increase means a few labels account for many assignments; this describes concentration, not confidence or organism abundance. The former ordered-taxa curves have been removed; this table retains their data.',
 'Figuras para entregar': 'Exportable figures', 'Cascada (% del padre)': 'Hierarchy (% of parent)', 'Resolución': 'Resolution',
 'Las barras Top 10 muestran las etiquetas que reúnen más proteínas: cada barra es una etiqueta y su longitud es el número de proteínas asignadas. Solo aparecen las diez más frecuentes; la tabla interactiva y los CSV conservan todas. Género y familia se leen por separado, y los nombres virales son contexto de la referencia.': 'Top 10 bars show the labels assigned to the most proteins: each bar is one label and its length is the assigned protein count. Only the ten most frequent labels are shown; the interactive table and CSV files retain all labels. Read genus and family separately; viral names provide reference context.',
 'Virus eucariotas': 'Eukaryotic viruses', 'Fagos': 'Phages', 'Secuencias y procedencia': 'Sequences and provenance',
 'Todas las secuencias: CSV comprimido (.gz)': 'All sequences: compressed CSV (.gz)',
 'Todas las secuencias: CSV sin comprimir': 'All sequences: uncompressed CSV',
 '. Descomprima este archivo para abrir el CSV; contiene los mismos datos sin pérdida.': '. Decompress this file to open the CSV; it preserves the same data without loss.',
 ' Incluye resultados de proteínas celulares y virales, ID y encabezado originales, archivo y carpeta, confianza MLP y datos FAISS disponibles. Es una exportación derivada opcional: el HTML no necesita cargarla. Los campos de origen vacíos indican información no disponible en la entrada.': ' It includes cellular and viral protein results, original IDs and headers, source file and folder, MLP confidence and available FAISS data. This is an optional derived export; the HTML does not need to load it. Empty source fields mean the input did not provide that information.',
 'La exportación adicional por secuencia está desactivada; consulte las predicciones completas de la corrida.': 'The additional per-sequence export is disabled; see the full run predictions.',
 'Qué contiene cada archivo, por qué pesa y cómo usarlo': 'File contents, sizes and usage', 'Descargar resumen por archivo': 'Download file summary',
 '. El selector de ámbito incluye archivos/muestras y carpetas.': '. The scope selector includes files/samples and folders.',
 'Carpeta': 'Folder', 'Archivo': 'File', 'Celulares': 'Cellular', 'Virales': 'Viral', 'Datos y método': 'Data and method',
 'Guía breve de archivos': 'Brief file guide', 'Jerarquía': 'Hierarchy', 'Todos los taxones': 'All taxa', 'Dominancia': 'Concentration', 'Calidad': 'Annotation quality', 'Auditoría por proteína': 'Per-protein audit',
 # Figure labels
 'Fagos no estructurales': 'Non-structural phages', 'Fagos estructurales': 'Structural phages', 'Umbral': 'Threshold',
 'Similitud coseno con el prototipo más cercano': 'Cosine similarity to the nearest prototype',
 'Proteínas de inferencia': 'Analyzed proteins', 'Bacteriófagos': 'Bacteriophages', 'Estructurales': 'Structural', 'No estructurales': 'Non-structural',
 'Clases virales (M4)': 'Viral classes (M4)', '10 clases estructurales': '10 structural classes', 'con asignaciones': 'with assignments',
 'Porcentajes = proteínas asignadas / proteínas de la clase padre. No son exactitud ni confianza.': 'Percentages = assigned proteins / proteins in the parent class. Not accuracy or confidence.',
 '% dentro de la clase padre': '% within the parent class', 'Cascada por padre': 'Distribution by parent', 'proteínas': 'proteins',
 'Las 10 clases estructurales (M6)': 'The 10 structural classes (M6)', '% de proteínas de la rama': '% of proteins in the branch',
 'Mejor nivel de referencia · conserva etiquetas originales, incluidos casos bajo umbral FAISS': 'Best reference level · retains original labels, including assignments below the FAISS threshold',
 'Solo hospedero': 'Host only', 'Mixto / funcional': 'Mixed / functional', 'Metadatos insuficientes': 'Insufficient metadata', 'Sin anotación': 'Unannotated',
 'con etiqueta': 'labeled', 'Sin asignaciones disponibles': 'No assignments available', 'Top 10 por rango; nombres virales solo como contexto': 'Top 10 by rank; viral names are reference context only',
 # Brief file guides
 'Guía breve de los archivos del informe.': 'Brief guide to report files.', 'Guía breve de los archivos de la corrida.': 'Brief guide to run files.',
 'Documentación histórica de la corrida.': 'Historical run documentation.', 'Informe interactivo; abrir en un navegador.': 'Interactive report; open in a browser.',
 'Resultados completos: un objeto JSON por proteína; permite regenerar el informe.': 'Full results: one JSON object per protein; allows report regeneration.',
 'Resultados completos guardados por el CLI para el informe.': 'Full structured results retained by the CLI for the report.',
 'Resultados completos en columnas, para análisis.': 'Full results in columns for analysis.',
 'Respaldo anterior; usar el CSV completo actual.': 'Previous backup; use the current full CSV.',
 'Exportación adicional por proteína, sin comprimir; opcional.': 'Additional uncompressed per-protein export; optional.',
 'Exportación adicional por proteína comprimida sin pérdida; opcional.': 'Additional losslessly compressed per-protein export; optional.',
 'Relación entre ID interno, ID/encabezado original, archivo y longitud.': 'Maps internal IDs to original IDs/headers, source files and lengths.',
 'Configuración, modelo, rutas, tiempos y estado de la inferencia.': 'Inference configuration, model, paths, timings and status.',
 'Conteos globales de clasificación.': 'Overall classification counts.', 'Conteos globales en columnas.': 'Overall counts in columns.',
 'Conteos y estadísticas por archivo de origen.': 'Counts and statistics by source file.', 'Conteos y estadísticas por carpeta de origen.': 'Counts and statistics by source folder.',
 'Conteos y estadísticas por muestra.': 'Counts and statistics by sample.', 'Conteos por ruta de clasificación.': 'Counts by classification path.',
 'Conteos por cluster FAISS de referencia.': 'Counts by reference FAISS cluster.', 'Registros descartados y motivo de exclusión.': 'Excluded records and exclusion reasons.',
 'Mensajes del proceso de inferencia.': 'Inference process messages.', 'Comandos usados en la inferencia.': 'Commands used for inference.',
 'Aminoácidos enviados al modelo, ordenados por longitud.': 'Amino-acid sequences sent to the model, sorted by length.',
 'Aminoácidos reunidos con IDs internos para inferencia.': 'Combined amino-acid sequences with internal IDs for inference.',
 'Conteos y porcentajes por rama y ámbito.': 'Counts and percentages by branch and scope.', 'Archivos, carpetas, rutas, hashes y conteos de origen.': 'Source files, folders, paths, hashes and counts.',
 'Conteos por mejor nivel taxonómico de referencia disponible.': 'Counts by best available reference taxonomic level.',
 'Resolución separando asignaciones bajo el umbral FAISS.': 'Resolution with assignments below the FAISS threshold separated.',
 'Todas las etiquetas, conteos y porcentajes, incluido el acumulado.': 'All labels, counts and percentages, including cumulative percentages.',
 'Las diez etiquetas más frecuentes por ámbito, clase y rango.': 'Ten most frequent labels by scope, class and rank.',
 'Concentración de asignaciones: Top 1, Top 10 y Simpson.': 'Assignment concentration: Top 1, Top 10 and Simpson.',
 'Origen de anotaciones y conteos bajo umbral FAISS.': 'Annotation sources and counts below the FAISS threshold.',
 'Etiquetas y procedencia por proteína viral; excluye celulares.': 'Labels and provenance per viral protein; excludes cellular proteins.',
 'Umbrales, conteos y estadísticos de similitud por clase de fago.': 'Thresholds, counts and similarity statistics by phage class.',
 'Fuentes, hashes y reglas de interpretación del informe.': 'Report sources, hashes and interpretation rules.',
 'Comprobaciones registradas de origen y conteos.': 'Recorded provenance and count checks.',
 'Árbol de clasificación y porcentajes dentro del padre.': 'Classification tree and percentages within each parent.',
 'Reparto por padre y clases estructurales M6.': 'Parent distributions and M6 structural classes.',
 'Mejor nivel taxonómico disponible por rama viral.': 'Best available taxonomic level by viral branch.',
 'Distribución de similitud FAISS y umbrales.': 'FAISS similarity distribution and thresholds.',
 'Diez etiquetas más frecuentes de fagos por rango.': 'Ten most frequent phage labels by rank.',
 'Diez etiquetas más frecuentes de virus eucariotas por rango.': 'Ten most frequent eukaryotic virus labels by rank.',
 'ARCHIVOS (tamaños en MiB)': 'FILES (sizes in MiB)', 'INFORME VYDRA': 'VYDRA REPORT', 'RESULTADOS VYDRA': 'VYDRA RESULTS',
 'Abrir informe.html; allí se explica cómo leer cada gráfica.': 'Open informe.html for explanations of every chart.',
 'PNG: imágenes para consulta. SVG: imágenes vectoriales para exportar.': 'PNG: images for viewing. SVG: vector images for export.',
 'Los archivos grandes repiten resultados y anotaciones por proteína.': 'Large files repeat results and annotations for each protein.',
 'Las cadenas de aminoácidos están en los FASTA, no en el CSV ni JSONL.': 'Amino-acid sequences are in FASTA files, not in CSV or JSONL results.',
 'El HTML no necesita cargar las predicciones ni secuencias.csv.gz para abrirse.': 'The HTML opens without loading predictions or secuencias.csv.gz.',
 'Descomprima .gz para abrir el CSV. Gzip es el formato predeterminado, sin pérdida.': 'Decompress .gz to open the CSV. Lossless gzip compression is the default.',
 'Para omitir esta copia adicional: --sequence-export none; sin comprimir: --sequence-export csv.': 'Skip this additional copy with --sequence-export none; use --sequence-export csv for uncompressed output.',
 'Conserve predicciones, manifiesto y metadata para regenerar sin repetir inferencia.': 'Keep predictions, manifest and metadata to regenerate reports without repeating inference.',
 'informe, imágenes y tablas; consultar README.txt dentro.': 'report, images and tables; see README.txt inside.',
 'resultados individuales separados por muestra.': 'individual results separated by sample.', 'carpeta auxiliar de resultados.': 'auxiliary results folder.',
 'Predicciones del CLI en el formato solicitado.': 'CLI predictions in the requested format.', 'Archivo auxiliar de resultados.': 'Auxiliary results file.',
 'Explicaciones de gráficas dentro del HTML.': 'Chart explanations are included in the HTML.', 'Abrir': 'Open',
 'figuras en español; se seleccionan con el switch del informe.': 'Spanish figures; selected using the report language switch.',
}


def tr(text, language='en'):
    if language == 'es':
        return text
    if text in TEXT:
        return TEXT[text]
    m = re.fullmatch(r'([\d,]+) proteínas · conteos de proteínas, no abundancia de organismos\.', text)
    if m:
        return f'{m[1]} proteins · protein counts, not organism abundance.'
    m = re.fullmatch(r'(\d+) de (\d+) proteínas de fagos tienen similitud menor al umbral informado\. Las figuras conservan las etiquetas originales;', text)
    if m:
        return f'{m[1]} of {m[2]} phage proteins have similarity below the reported threshold. Figures retain the original labels;'
    # Sequence link and explanation share a text node after an inline anchor.
    for prefix in ('. Descomprima este archivo para abrir el CSV; contiene los mismos datos sin pérdida.', '.', 'La exportación adicional por secuencia está desactivada; consulte las predicciones completas de la corrida.'):
        suffix = ' Incluye resultados de proteínas celulares y virales, ID y encabezado originales, archivo y carpeta, confianza MLP y datos FAISS disponibles. Es una exportación derivada opcional: el HTML no necesita cargarla. Los campos de origen vacíos indican información no disponible en la entrada.'
        if text == (prefix + suffix).strip():
            return TEXT.get(prefix, prefix) + TEXT[suffix]
    return text


def language_from_argv(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    for i, arg in enumerate(args):
        if arg.startswith('--language='):
            return arg.split('=', 1)[1]
        if arg == '--language' and i + 1 < len(args):
            return args[i + 1]
    return 'en'


def localize_parser(parser, language='en'):
    parser.add_argument('--language', choices=('en', 'es'), default='en',
                        help='Output language: English (default) or Spanish.' if language == 'en' else 'Idioma de salida: inglés (predeterminado) o español.')
    # Help strings are translated before argparse handles --help.
    def visit(p):
        p.description = HELP.get(p.description, p.description) if language == 'en' else p.description
        p.epilog = HELP.get(p.epilog, p.epilog) if language == 'en' else p.epilog
        for action in p._actions:
            if language == 'en' and action.help:
                action.help = HELP.get(action.help, action.help)
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    if not any(a.dest == 'language' for a in child._actions):
                        child.add_argument('--language', choices=('en', 'es'), default=argparse.SUPPRESS,
                                           help='Output language: en (default) or es.' if language == 'en' else 'Idioma de salida: en (predeterminado) o es.')
                    visit(child)
                for choice in action._choices_actions:
                    if language == 'en': choice.help = HELP.get(choice.help, choice.help)
    visit(parser)
    return parser

HELP = {}

import html
import json
from html.parser import HTMLParser

UI = {
 'en': {'no_data':'No data', 'unlabeled':'Unlabeled', 'distribution':'Distribution of all labels', 'class_percent':'% of class',
        'stats':'{assigned} of {total} proteins labeled; {taxa} labels; Top 1: {top1}% of labeled proteins; Top 10: {top10}%.',
        'child':'Branch','count':'Proteins','percent_parent':'% of parent','percent_total':'% of total','class':'Class','level':'Best level','percent_class':'% of class','position':'Position','taxon':'Reference label','percent_assigned':'% of labeled proteins','cumulative_percent_assigned':'Cumulative % of labeled proteins',
        'genus':'Genus','family':'Family','virus_name_context':'Reference viral name','host':'Host only','mixed_or_functional':'Mixed / functional','insufficient_metadata':'Insufficient metadata','unannotated':'Unannotated',
        'GLOBAL':'GLOBAL','TOTAL':'TOTAL','cellular':'Cellular','viral':'Viral','phage':'Phages','viral_euk':'Eukaryotic viruses','structural':'Structural','non_structural':'Non-structural','muestra:':'Sample/file:','carpeta:':'Folder:'},
 'es': {'no_data':'Sin datos','unlabeled':'Sin etiqueta','distribution':'Distribución de todas las etiquetas','class_percent':'% de la clase',
        'stats':'{assigned} de {total} proteínas con etiqueta; {taxa} etiquetas; Top 1: {top1}% de proteínas con etiqueta; Top 10: {top10}%.',
        'child':'Rama','count':'Proteínas','percent_parent':'% del padre','percent_total':'% del total','class':'Clase','level':'Mejor nivel','percent_class':'% de la clase','position':'Posición','taxon':'Etiqueta de referencia','percent_assigned':'% de proteínas con etiqueta','cumulative_percent_assigned':'% acumulado de proteínas con etiqueta',
        'genus':'Género','family':'Familia','virus_name_context':'Nombre viral de referencia','host':'Solo hospedero','mixed_or_functional':'Mixto / funcional','insufficient_metadata':'Metadatos insuficientes','unannotated':'Sin anotación',
        'GLOBAL':'GLOBAL','TOTAL':'TOTAL','cellular':'Celular','viral':'Viral','phage':'Fagos','viral_euk':'Virus eucariotas','structural':'Estructurales','non_structural':'No estructurales','muestra:':'Muestra/archivo:','carpeta:':'Carpeta:'},
}


def bilingual_document(document, language='en'):
    """Localize presentation only; preserve a single copy of the scientific payload."""
    if language not in ('en', 'es'):
        raise ValueError('language must be en or es')
    catalog = {}
    def register(es):
        key = str(len(catalog))
        catalog[key] = {'en': tr(es), 'es': es}
        return key
    class Localizer(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.output = []
            self.stack = []
        def handle_decl(self, decl): self.output.append('<!' + decl + '>')
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'html': attrs['lang'] = language
            if tag in ('img', 'a'):
                attr = 'src' if tag == 'img' else 'href'
                path = attrs.get(attr, '')
                if path.endswith(('.png', '.svg')):
                    attrs['data-figure-' + attr] = path
                    if language == 'es': attrs[attr] = 'es/' + path
                if tag == 'a' and path == 'README.txt':
                    attrs['data-guide'] = 'README'
                    attrs['href'] = 'README_es.txt' if language == 'es' else 'README_en.txt'
            for attr in ('alt', 'aria-label'):
                if attrs.get(attr) and tr(attrs[attr]) != attrs[attr]:
                    key = register(attrs[attr])
                    attrs['data-i18n-' + attr] = key
                    attrs[attr] = catalog[key][language]
            self.output.append('<' + tag + ''.join(' ' + k + ('="' + html.escape(v, quote=True) + '"' if v is not None else '') for k,v in attrs.items()) + '>')
            if tag not in ('meta','img','br','hr','input','link'): self.stack.append(tag)
        def handle_endtag(self, tag):
            self.output.append('</' + tag + '>')
            if self.stack and self.stack[-1] == tag: self.stack.pop()
        def handle_data(self, data):
            tag = self.stack[-1] if self.stack else ''
            if tag in ('script', 'style'):
                self.output.append(data)
                return
            text = data.strip()
            if text and tr(text) != text:
                key = register(text)
                value = html.escape(catalog[key][language])
                leading = data[:len(data)-len(data.lstrip())]
                trailing = data[len(data.rstrip()):]
                if tag in ('title','option'):
                    self.output[-1] = self.output[-1][:-1] + f' data-i18n="{key}">'
                    self.output.append(leading + value + trailing)
                else:
                    self.output.append(leading + f'<span data-i18n="{key}">' + value + '</span>' + trailing)
            else:
                self.output.append(html.escape(data))
    parser = Localizer()
    parser.feed(document)
    document = ''.join(parser.output)
    # Localize generated tables, options, stats and pie labels as well.
    document = document.replace("'<th>'+esc(k)", "'<th>'+esc(T(k))")
    document = document.replace("'<td>'+esc(typeof r[k]", "'<td>'+esc(typeof r[k]")
    document = document.replace(":r[k])", ":(['child','class','level'].includes(k)?display(r[k]):r[k]))")
    document = document.replace('`<option>${esc(v)}</option>`', '`<option value="${esc(v)}">${esc(display(v))}</option>`')
    document = document.replace("'Sin datos'", "T('no_data')")
    old_stats = '${stat.assigned_count} de ${stat.class_count} con etiqueta; ${stat.n_taxa} taxones; top 1: ${stat.top1_percent_assigned.toFixed(1)}% de etiquetas; top 10: ${stat.top10_percent_assigned.toFixed(1)}%.'
    document = document.replace('`' + old_stats + '`', "T('stats').replace('{assigned}',stat.assigned_count).replace('{total}',stat.class_count).replace('{taxa}',stat.n_taxa).replace('{top1}',stat.top1_percent_assigned.toFixed(1)).replace('{top10}',stat.top10_percent_assigned.toFixed(1))")
    document = document.replace("name:'Sin etiqueta'", "name:T('unlabeled')").replace("s.name=='Sin etiqueta'", "s.name==T('unlabeled')")
    document = document.replace('aria-label="Distribución de todos los taxones"', 'aria-label="\'+esc(T(\'distribution\'))+\'"')
    document = document.replace("+'% de la clase)'", "+' '+T('class_percent')+')'")
    # Define language helpers before the existing report script executes.
    prelude = '<script>const CATALOG=' + json.dumps(catalog, ensure_ascii=False).replace('<','\\u003c') + ';const UI=' + json.dumps(UI, ensure_ascii=False).replace('<','\\u003c') + ';let LANG=' + json.dumps(language) + ''';
function T(k){return UI[LANG][k]||k}
function display(v){v=String(v);for(const prefix of ['muestra:','carpeta:'])if(v.startsWith(prefix))return T(prefix)+v.slice(prefix.length);return v.split('/').map(T).join(' / ')}
function setLanguage(lang){LANG=lang;document.documentElement.lang=lang;document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=CATALOG[el.dataset.i18n][lang]);for(const attr of ['alt','aria-label'])document.querySelectorAll('[data-i18n-'+attr+']').forEach(el=>el.setAttribute(attr,CATALOG[el.getAttribute('data-i18n-'+attr)][lang]));for(const attr of ['src','href'])document.querySelectorAll('[data-figure-'+attr+']').forEach(el=>el.setAttribute(attr,(lang==='es'?'es/':'')+el.getAttribute('data-figure-'+attr)));document.querySelectorAll('[data-guide]').forEach(el=>el.href=lang==='es'?'README_es.txt':'README_en.txt');document.querySelectorAll('#scope option,#parent option,#group option').forEach(el=>el.textContent=display(el.value));document.getElementById('language').value=lang;draw()}
</script>'''
    control = '<div style="position:sticky;top:0;background:#f5f7fa;padding:10px;z-index:2;text-align:right"><label for="language">Language / Idioma</label> <select id="language" aria-label="Report language / Idioma del informe"><option value="en"' + (' selected' if language == 'en' else '') + '>English</option><option value="es"' + (' selected' if language == 'es' else '') + '>Español</option></select></div>'
    document = document.replace('<h1>', control + '<h1>', 1)
    document = document.replace('<script>const D=', prelude + '<script>const D=', 1)
    document = document.replace('parents();</script>', "parents();document.getElementById('language').onchange=e=>setLanguage(e.target.value);setLanguage(LANG);</script>")
    return document

HELP.update({
 'Clasificador jerarquico local de proteinas Vydra.':'Local hierarchical protein classifier Vydra.',
 'Ayuda de inferencia: vydra predict --help. Cada subcomando admite --help.':'Inference help: vydra predict --help. Every subcommand supports --help.',
 'mostrar la versión del CLI':'show the CLI version', 'clasificar secuencias o embeddings':'classify sequences or embeddings',
 'Clasifica proteínas con ProstT5, MLP y FAISS. Elija una entrada. Con --output genera resultados, informe y guía TXT.':'Classify proteins with ProstT5, MLP and FAISS. Choose one input. With --output, save predictions, a report and TXT guides.',
 'Ejemplo:\n  vydra predict --fasta proteinas.faa --format csv --output resultados/predicciones.csv\n\nLa exportación adicional del informe se comprime por defecto con gzip.':'Example:\n  vydra predict --fasta proteins.faa --format csv --output results/predictions.csv\n\nThe additional report export uses lossless gzip compression by default.',
 'secuencia de aminoacidos o texto FASTA':'amino-acid sequence or FASTA text', 'archivo FASTA/TXT':'FASTA/TXT file', 'archivo de embeddings .pt o .npy':'.pt or .npy embedding file', 'leer secuencia/FASTA desde stdin':'read sequence/FASTA from stdin',
 'formato de resultados: tabla legible, JSON, JSON por línea o CSV (predeterminado: table)':'output format: readable table, JSON, one JSON object per line, or CSV (default: table)',
 'archivo de resultados; sin esta opción imprime en terminal y no genera informe':'output file; without this option, print to the terminal and skip the report',
 'generar informe junto al archivo --output (por defecto; --no-report lo desactiva)':'generate a report next to --output (default; disable with --no-report)',
 'Exportación adicional del informe: gzip (default), CSV o ninguna':'additional report export: gzip (default), uncompressed CSV, or none',
 'dispositivo para ProstT5/MLP; FAISS siempre requiere GPU CUDA':'device for ProstT5/MLP (default: auto); FAISS always requires a CUDA GPU',
 'prohibir descargas y usar solo archivos locales':'disable downloads and use local files only',
 'batch fijo inicial; por defecto se calcula automaticamente':'initial batch size; calculated automatically when omitted',
 'limite superior del batch automatico (GPU: 256, CPU: 32)':'automatic batch size limit (default: GPU 256, CPU 32)',
 'fraccion maxima de memoria total utilizable (GPU: 0.85, CPU: 0.75)':'maximum fraction of total memory to use (default: GPU 0.85, CPU 0.75)',
 'reserva de memoria en GiB; si se omite, el motor la calcula':'reserved memory in GiB; calculated by the engine when omitted',
 'ancho en aa de los buckets de longitud (por defecto: 128)':'length bucket width in amino acids (default: 128)',
 'comprobar dependencias, pesos y artefactos':'check dependencies, weights and artifacts',
 'guardar ProstT5 dentro del paquete':'save ProstT5 inside the package', 'directorio de destino (por defecto models/prostt5)':'destination directory (default: models/prostt5)',
 'descargar los bancos de prototipos publicados en GitHub Releases':'download prototype banks published in GitHub Releases', 'reemplazar archivos existentes':'replace existing files',
 'Genera un informe desde predicciones guardadas, sin repetir la inferencia ni necesitar GPU.':'Generate a report from saved predictions without repeating inference or requiring a GPU.',
 'Ejemplo:\n  python scripts/report_inference.py --input results/inference/corrida/predicciones_completas.jsonl\n\nGenera HTML, figuras, tablas y guías TXT. Exportación adicional: gzip por defecto.':'Example:\n  python scripts/report_inference.py --input results/inference/run/predicciones_completas.jsonl\n\nGenerate HTML, figures, tables and TXT guides. Additional export: gzip by default.',
 'Predicciones completas CSV o JSONL de una corrida terminada':'full CSV or JSONL predictions from a completed run', 'Default: directorio de entrada / informe_inferencia':'output directory (default: input directory / informe_inferencia)',
 'CSV de referencia para enriquecer clases de virus eucariotas; por defecto usa el resumen local del proyecto':'reference CSV for eukaryotic virus class annotations (default: project local class summary)',
 'No cruzar clases con el CSV taxonómico; conserva las anotaciones ya guardadas':'skip the taxonomy CSV lookup; retain saved annotations',
 'Tabla adicional por secuencia: comprimida sin pérdida (default), CSV o sin exportación':'additional per-sequence table: lossless gzip (default), uncompressed CSV, or none',
 'Inferencia Vydra recursiva sobre FASTA de proteínas, con exclusión de nucleótidos por contenido.':'Recursively run Vydra on protein FASTA files, excluding nucleotide records by content.',
 'Ejemplo:\n  python scripts/infer_protein_folder.py --input /ruta/proteinas --output results/inference/nueva_corrida\n\nGenera resultados, informe y guías TXT. Exportación adicional: gzip por defecto.':'Example:\n  python scripts/infer_protein_folder.py --input /path/to/proteins --output results/inference/new_run\n\nGenerate results, a report and TXT guides. Additional export: gzip by default.',
 'Carpeta con archivos FASTA, incluso en subcarpetas':'input folder containing FASTA files, including subfolders',
 'Carpeta nueva o vacía para resultados, manifiesto, informe y logs':'new or empty output folder for results, manifest, report and logs',
 'Snapshot local opcional; por defecto usa la caché o descarga ProstT5':'optional local model snapshot; otherwise use the cache or download ProstT5',
 'Usar únicamente el modelo local o en caché, sin descargas':'use only the local/cached model; disable downloads',
 'Dispositivo de ProstT5/MLP (predeterminado: cuda); FAISS requiere GPU CUDA':'ProstT5/MLP device (default: cuda); FAISS requires a CUDA GPU',
 'Generar informe HTML, CSV y figuras al terminar (activo por defecto; --no-report lo desactiva; requiere matplotlib)':'generate HTML, CSV and figures after inference (enabled by default; disable with --no-report; requires matplotlib)',
 'Exportación adicional del informe: gzip (default), CSV sin comprimir o ninguna':'additional report export: gzip (default), uncompressed CSV, or none',
})
