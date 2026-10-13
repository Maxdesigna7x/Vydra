"""Render the approved standalone interactive report from saved predictions."""
from pathlib import Path
import html
import json
import math
try:
    from .biological_context import neighbors_from_row, summarize_neighbors, function_annotation_status
    from .report_payloads import fasta_payload
except ImportError:
    from biological_context import neighbors_from_row, summarize_neighbors, function_annotation_status
    from report_payloads import fasta_payload

TEMPLATE = Path(__file__).resolve().parent / 'report' / 'interactive.html'

def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def write_interactive_report(input_path, output_dir, taxonomy):
    try:
        from .inference_report import iter_rows, normalized_path, annotation_for, rank_value, sha256
    except ImportError:
        from inference_report import iter_rows, normalized_path, annotation_for, rank_value, sha256
    rows = []
    metadata_path = Path(input_path).parent / 'metadata_inferencia.json'
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    for row in iter_rows(Path(input_path)):
        path = normalized_path(row.get('path'))
        annotation, source = annotation_for(row, path, taxonomy)
        viral = path[:1] == ('viral',)
        phage = path[:2] == ('viral', 'phage')
        level = str(annotation.get('best_taxonomic_level') or 'unannotated') if viral else 'no_aplica'
        if level in ('genus', 'family') and not annotation.get('dominant_' + level):
            level = 'unannotated'
            annotation = {**annotation, 'best_taxonomic_level': level}
        similarity = number(row.get('cluster_similarity'))
        threshold = number(row.get('cluster_similarity_threshold'))
        status = 'no_aplica' if not phage else 'no_disponible'
        if phage and similarity is not None and threshold is not None:
            status = 'bajo' if similarity < threshold else 'supera'
        filename = str(row.get('source_relative_path') or row.get('source_file') or Path(input_path).name)
        folder = str(row.get('source_folder') or Path(filename).parent)
        neighbors = neighbors_from_row(row)
        local = summarize_neighbors(neighbors)
        official = {k.removeprefix('viral_euk_class_metadata.'): v for k, v in row.items()
                    if k.startswith('viral_euk_class_metadata.') and v not in (None, '')}
        cluster = {k.removeprefix('cluster_annotation.'): v for k, v in row.items()
                   if k.startswith('cluster_annotation.')}
        product = str(annotation.get('representative_product') or annotation.get('protein_description') or annotation.get('product') or '')
        rows.append(dict(
            id=str(row['seq_id']), original=str(row.get('original_id') or row['seq_id']),
            original_header=str(row.get('original_header') or row.get('original_id') or row['seq_id']),
            file=filename, folder=folder, path=list(path),
            length=int(number(row.get('original_length_aa') or row.get('length')) or 0),
            chunked=str(row.get('chunked', '')).lower() in ('true','1'),
            conf={key.split('.', 1)[1]: number(value) for key,value in row.items() if key.startswith('confidences.')},
            level=level, genus=rank_value(annotation,'genus'), family=rank_value(annotation,'family'),
            source=source if viral else '', status=status, similarity=similarity, threshold=threshold,
            nearest=str(row.get('cluster_nearest_seq_id') or row.get('nearest_seq_id') or row.get('prototype_seq_id') or ''),
            representative=str(annotation.get('representative_seq_id') or annotation.get('cluster_rep_sequence_accession') or ''),
            product=product,
            virus=rank_value(annotation,'virus_name_context'), host=str(annotation.get('dominant_host') or annotation.get('host') or ''),
            cluster_id=row.get('cluster_id'), neighbors=neighbors, local=local, cluster=cluster, official=official,
            function_status=function_annotation_status(neighbors[0].get('product') if neighbors else '' if phage else product),
            neighbor_genus=local['genus_dominant'] if local['genus_unique'] == 1 else '',
            neighbor_family=local['family_dominant'] if local['family_unique'] == 1 else '',
        ))
    rows.sort(key=lambda row: (row['length'], row['file'], row['id']))
    fasta = fasta_payload(input_path, rows, metadata)
    # Escape '<' so protein IDs/annotations cannot terminate the embedded JSON script.
    payload=json.dumps(rows, ensure_ascii=False, allow_nan=False, separators=(',',':')).replace('<','\\u003c')
    page=TEMPLATE.read_text(encoding='utf-8')
    page=page.replace('__VYDRA_STATE_KEY__','vydra-report-'+sha256(input_path))
    page=page.replace('__VYDRA_SUBTITLE__',html.escape(Path(input_path).parent.name)+' · '+format(len(rows),',')+' proteins')
    page=page.replace('__VYDRA_DATA__',payload)
    page=page.replace('__VYDRA_FASTA__',json.dumps(fasta, separators=(',', ':')))
    page=page.replace('__VYDRA_RUN__',json.dumps(metadata, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c'))
    downloads=[('README_en.txt','File guide'),('asignaciones_taxonomicas.csv','Cluster/class reference assignments'),('jerarquia.csv','Classification counts'),('origen_archivos.csv','Input provenance'),('tiempos.csv','Run timing')]
    downloads += [(name,'All protein records') for name in ['secuencias.csv.gz','secuencias.csv'] if (Path(output_dir)/name).is_file()]
    page=page.replace('__VYDRA_DOWNLOADS__',' · '.join('<a href="'+name+'">'+label+'</a>' for name,label in downloads))
    destination=Path(output_dir)/'informe.html'
    destination.write_text(page,encoding='utf-8')
    return destination
