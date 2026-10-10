#!/usr/bin/env python3
"""Offline, streaming summaries and figures for a completed Vydra inference."""
from __future__ import annotations

import argparse
import csv
import gzip
import contextlib
import hashlib
import html
import json
import math
import statistics
import textwrap
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .inference_i18n import tr, bilingual_document, language_from_argv, localize_parser
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from inference_i18n import tr, bilingual_document, language_from_argv, localize_parser

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TAXONOMY = ROOT / 'results/viral_euk_class_metadata/viral_euk_class_taxonomy_summary.csv'
LEVELS = ('genus', 'family', 'host', 'mixed_or_functional', 'insufficient_metadata', 'unannotated')
LABELS = {'genus': 'Género', 'family': 'Familia',
          'host': 'Solo hospedero', 'mixed_or_functional': 'Mixto / funcional',
          'insufficient_metadata': 'Metadatos insuficientes', 'unannotated': 'Sin anotación'}
RANKS = ('genus', 'family', 'virus_name_context')
RANK_LABELS = {'genus': 'Género', 'family': 'Familia', 'virus_name_context': 'Nombre viral de referencia'}
COLORS = ['#247ba0', '#f4a261', '#70ad47', '#9b5de5', '#e76f51', '#43aa8b', '#577590', '#f9c74f', '#e56b9f', '#80b6c6']
STRUCTURAL_CLASSES = ('baseplate', 'collar', 'head-tail_joining', 'major_capsid', 'major_tail',
                      'minor_capsid', 'minor_tail', 'portal', 'tail_fiber', 'tail_sheath')
SOURCE_FIELDS = ('original_id', 'original_header', 'source_relative_path', 'source_folder',
                 'source_file', 'source_path', 'source_file_sha256', 'original_length_aa',
                 'model_input_length_aa', 'terminal_stop_removed')


def percent(n, d):
    return 100 * n / d if d else 0.0


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def flatten(obj, prefix=''):
    result = {}
    for key, value in obj.items():
        name = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict):
            result.update(flatten(value, name))
        else:
            result[name] = value
    return result


def raw_rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        if path.suffix == '.csv':
            yield from csv.DictReader(stream)
        elif path.suffix == '.jsonl':
            for line in stream:
                if line.strip():
                    yield flatten(json.loads(line))
        else:
            raise ValueError('La entrada debe ser CSV o JSONL.')


def iter_rows(path):
    """Recover legacy provenance from its saved manifest, without model inference."""
    metadata_path = path.parent / 'metadata_inferencia.json'
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    legacy_root = metadata.get('input_directory')
    manifest_path = path.parent / 'manifest_secuencias.csv'
    origins = {}
    if legacy_root and manifest_path.is_file():
        with manifest_path.open(encoding='utf-8', newline='') as stream:
            for item in csv.DictReader(stream):
                rel = item.get('source_relative_path') or item.get('source_file') or ''
                origins[item['seq_id']] = {
                    **item, 'source_relative_path': rel,
                    'source_folder': str(Path(rel).parent),
                    'source_path': str(Path(legacy_root) / rel),
                    'source_file_sha256': item.get('source_file_sha256') or item.get('source_sha256', ''),
                    'original_length_aa': item.get('original_length_aa') or item.get('original_length', ''),
                }
    seen = set()
    for row in raw_rows(path):
        if origins:
            sid = row.get('seq_id')
            if sid not in origins:
                raise ValueError(f'ID no encontrado en el manifiesto de origen: {sid}')
            seen.add(sid)
            for key, value in origins[sid].items():
                if row.get(key) not in (None, '', value):
                    raise ValueError(f'Procedencia incompatible con manifiesto: {sid}, {key}')
                row[key] = value
        yield row
    if origins and seen != origins.keys():
        raise ValueError('Faltan predicciones para registros del manifiesto de origen.')


def normalized_path(value):
    values = value if isinstance(value, list) else str(value or '').split('/')
    return tuple('eukaryota' if str(v).strip() == 'eukariota' else str(v).strip()
                 for v in values if str(v).strip())


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_taxonomy(path):
    if path is None:
        return {}
    if not path.is_file():
        raise FileNotFoundError(f'No existe el resumen taxonómico: {path}')
    with path.open(encoding='utf-8', newline='') as stream:
        return {str(row['fine_class']): row for row in csv.DictReader(stream)}


def annotation_for(row, path, taxonomy):
    if path[:2] == ('viral', 'phage'):
        annotation = {k.removeprefix('cluster_annotation.'): v for k, v in row.items()
                      if k.startswith('cluster_annotation.')}
        return annotation, 'embedded_cluster_annotation'
    annotation = {k.removeprefix('viral_euk_class_annotation.'): v for k, v in row.items()
                  if k.startswith('viral_euk_class_annotation.')}
    if annotation.get('best_taxonomic_level'):
        return annotation, 'embedded_viral_euk_annotation'
    if len(path) > 2 and path[2] in taxonomy:
        return taxonomy[path[2]], 'local_class_summary_reconstructed'
    return {}, 'missing'


def rank_value(annotation, rank):
    """Retain only ranks supported by the emitted best level; never promote virus names."""
    level = annotation.get('best_taxonomic_level')
    if rank == 'genus' and level == 'genus':
        return str(annotation.get('dominant_genus') or '')
    if rank == 'family' and level in ('family', 'genus'):
        try:
            if float(annotation.get('family_coverage') or 0) >= .70 and float(annotation.get('family_purity') or 0) >= .90:
                return str(annotation.get('dominant_family') or '')
        except (TypeError, ValueError):
            pass
    if rank == 'virus_name_context':
        return str(annotation.get('dominant_virus_name') or '')
    return ''


def collect(input_path, taxonomy, assignment_path):
    nodes = Counter()
    edges = Counter()
    totals = Counter()
    levels = Counter()
    taxa = defaultdict(Counter)
    sources = Counter()
    quality = Counter()
    accepted_levels = Counter()
    seen = set()
    with assignment_path.open('w', encoding='utf-8', newline='') as stream:
        fields = ['seq_id', *SOURCE_FIELDS, 'sample', 'class', 'path', 'best_taxonomic_level', 'genus', 'family',
                  'virus_name_context', 'annotation_source', 'similarity_below_threshold',
                  'cluster_class', 'cluster_similarity', 'cluster_similarity_threshold']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(iter_rows(input_path), 1):
            seq_id = row.get('seq_id')
            if not seq_id or seq_id in seen:
                raise ValueError(f'ID vacío o duplicado en fila {index}: {seq_id}')
            seen.add(seq_id)
            path = normalized_path(row.get('path'))
            if not path or path[0] not in ('cellular', 'viral'):
                raise ValueError(f'Ruta inválida para {seq_id}: {path}')
            sample = str(row.get('sample_id') or row.get('source_relative_path') or row.get('source_file') or 'sin_muestra')
            scopes = ('GLOBAL', f'muestra:{sample}')
            if row.get('source_relative_path'):
                scopes += (f"carpeta:{row.get('source_folder') or '.'}",)
            for scope in scopes:
                nodes[(scope, ())] += 1
                for depth in range(1, len(path) + 1):
                    nodes[(scope, path[:depth])] += 1
                    edges[(scope, path[:depth - 1], path[:depth])] += 1
            if path[:2] == ('viral', 'phage'):
                groups = ['phage', '/'.join(path[2:]) or 'phage_sin_subclase']
            elif path[:2] == ('viral', 'eukaryota'):
                groups = ['viral_euk', 'viral_euk/' + (path[2] if len(path) > 2 else 'sin_clase')]
            else:
                continue
            annotation, source = annotation_for(row, path, taxonomy)
            level = str(annotation.get('best_taxonomic_level') or 'unannotated')
            # No species field or species rule is supported by the current Vydra schema.
            if level not in LEVELS:
                raise ValueError(f'Nivel no soportado por este contrato: {level}')
            if level in ('genus', 'family') and not annotation.get('dominant_' + level):
                level = 'unannotated'
                annotation = {**annotation, 'best_taxonomic_level': level}
            values = {rank: rank_value(annotation, rank) for rank in RANKS}
            below = False
            try:
                below = float(row['cluster_similarity']) < float(row['cluster_similarity_threshold'])
            except (KeyError, TypeError, ValueError):
                pass
            writer.writerow(dict(seq_id=seq_id, **{k: row.get(k, '') for k in SOURCE_FIELDS},
                                 sample=sample, **{'class': groups[0]}, path='/'.join(path),
                                 best_taxonomic_level=level, **values, annotation_source=source,
                                 similarity_below_threshold=below, cluster_class=row.get('cluster_class',''),
                                 cluster_similarity=row.get('cluster_similarity',''),
                                 cluster_similarity_threshold=row.get('cluster_similarity_threshold','')))
            for scope in scopes:
                for group in groups:
                    totals[(scope, group)] += 1
                    levels[(scope, group, level)] += 1
                    sources[(scope, group, source)] += 1
                    quality[(scope, group)] += int(below)
                    accepted_levels[(scope, group, 'below_threshold' if below else level)] += 1
                    for rank, value in values.items():
                        if value:
                            taxa[(scope, group, rank)][value] += 1
    if not seen:
        raise ValueError('La inferencia está vacía.')
    return nodes, edges, totals, levels, taxa, sources, quality, accepted_levels


def ordered(counter):
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def sequence_sources(input_path, out, input_root=None, sequence_export='gzip'):
    """Export every prediction, including cellular records, without dropping late fields."""
    fields = dict.fromkeys(('seq_id', *SOURCE_FIELDS))
    if sequence_export != 'none':
        for row in iter_rows(input_path):
            fields.update(dict.fromkeys(row))
    counts = Counter()
    complete = 0
    sequence_path = out / ('secuencias.csv.gz' if sequence_export == 'gzip' else 'secuencias.csv')
    target = (gzip.open(sequence_path, 'wt', encoding='utf-8', newline='', compresslevel=6)
              if sequence_export == 'gzip' else sequence_path.open('w', encoding='utf-8', newline='')
              if sequence_export == 'csv' else contextlib.nullcontext(None))
    with target as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields)) if stream else None
        if writer:
            writer.writeheader()
        for row in iter_rows(input_path):
            rel = str(row.get('source_relative_path') or '')
            folder = str(row.get('source_folder') or (str(Path(rel).parent) if rel else ''))
            file = str(row.get('source_file') or (Path(rel).name if rel else ''))
            row.update(source_folder=folder, source_file=file)
            if input_root and rel and not row.get('source_path'):
                row['source_path'] = str(Path(input_root) / rel)
            complete += bool(rel and file and row.get('original_id'))
            counts[(folder or '.', file, rel, row.get('source_path') or '',
                    row.get('source_file_sha256') or '', normalized_path(row.get('path'))[0])] += 1
            if writer:
                writer.writerow({k: '/'.join(normalized_path(v)) if k == 'path' else
                             json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})
    sources = defaultdict(Counter)
    for (*origin, branch), n in counts.items():
        sources[tuple(origin)][branch] += n
    rows = [dict(zip(('source_folder', 'source_file', 'source_relative_path', 'source_path',
                      'source_file_sha256'), origin), sequences=sum(n.values()),
                 cellular=n['cellular'], viral=n['viral']) for origin, n in sorted(sources.items())]
    write_csv(out / 'origen_archivos.csv', rows,
              ['source_folder', 'source_file', 'source_relative_path', 'source_path',
               'source_file_sha256', 'sequences', 'cellular', 'viral'])
    return rows, complete


def tables(out, data):
    nodes, edges, totals, levels, taxa, sources, quality, accepted_levels = data
    hierarchy = []
    for (scope, parent, child), n in sorted(edges.items()):
        hierarchy.append(dict(scope=scope, parent='/'.join(parent) or 'TOTAL', child='/'.join(child),
                              count=n, parent_count=nodes[(scope, parent)], total_count=nodes[(scope, ())],
                              percent_parent=percent(n, nodes[(scope, parent)]), percent_total=percent(n, nodes[(scope, ())])))
    write_csv(out / 'jerarquia.csv', hierarchy, ['scope', 'parent', 'child', 'count', 'parent_count', 'total_count', 'percent_parent', 'percent_total'])
    resolution = [dict(scope=s, **{'class': g}, level=l, count=levels[(s, g, l)], class_count=n,
                       percent_class=percent(levels[(s, g, l)], n))
                  for (s, g), n in sorted(totals.items()) for l in LEVELS]
    write_csv(out / 'resolucion_taxonomica.csv', resolution, ['scope', 'class', 'level', 'count', 'class_count', 'percent_class'])
    rankings, dominance = [], []
    for (scope, group), total in sorted(totals.items()):
        for rank in RANKS:
            counter = taxa[(scope, group, rank)]
            known = sum(counter.values())
            cumulative = 0
            for position, (name, n) in enumerate(ordered(counter), 1):
                cumulative += n
                rankings.append(dict(scope=scope, **{'class': group}, rank=rank, position=position, taxon=name,
                                     count=n, assigned_count=known, class_count=total,
                                     percent_assigned=percent(n, known), percent_class=percent(n, total),
                                     cumulative_percent_assigned=percent(cumulative, known)))
            dominance.append(dict(scope=scope, **{'class': group}, rank=rank, class_count=total,
                                  assigned_count=known, unassigned_count=total-known, n_taxa=len(counter),
                                  top1_percent_assigned=percent(max(counter.values(), default=0), known),
                                  top10_percent_assigned=percent(sum(n for _, n in ordered(counter)[:10]), known),
                                  simpson_concentration=sum((n / known)**2 for n in counter.values()) if known else 0))
    fields = ['scope', 'class', 'rank', 'position', 'taxon', 'count', 'assigned_count', 'class_count', 'percent_assigned', 'percent_class', 'cumulative_percent_assigned']
    write_csv(out / 'taxones_todos.csv', rankings, fields)
    write_csv(out / 'taxones_top10.csv', [r for r in rankings if r['position'] <= 10], fields)
    write_csv(out / 'dominancia.csv', dominance, list(dominance[0]) if dominance else ['scope', 'class', 'rank'])
    source_index = defaultdict(dict)
    for (s, g, src), v in sources.items():
        source_index[(s, g)][src] = v
    qc = [dict(scope=s, **{'class': g}, class_count=n, similarity_below_threshold=quality[(s, g)],
               annotation_sources=json.dumps(source_index[(s, g)], ensure_ascii=False))
          for (s, g), n in sorted(totals.items())]
    write_csv(out / 'calidad_anotacion.csv', qc, ['scope', 'class', 'class_count', 'similarity_below_threshold', 'annotation_sources'])
    threshold_rows = [dict(scope=s, **{'class': g}, level=l, count=accepted_levels[(s, g, l)],
                           class_count=n, percent_class=percent(accepted_levels[(s, g, l)], n))
                      for (s, g), n in sorted(totals.items()) for l in (*LEVELS, 'below_threshold')]
    write_csv(out / 'resolucion_control_umbral.csv', threshold_rows, ['scope', 'class', 'level', 'count', 'class_count', 'percent_class'])
    # Terminal predictions remain in their parent without inventing a child.
    children = Counter()
    for (scope, parent, child), n in edges.items():
        children[(scope, parent)] += n
    for key, n in nodes.items():
        assert children[key] <= n
    for (scope, group), n in totals.items():
        assert sum(levels[(scope, group, level)] for level in LEVELS) == n
    return hierarchy, resolution, rankings, dominance


def similarity_report(input_path, out, language='en', write_table=True):
    """Compare to thresholds recorded in predictions; configuration only fills empty classes."""
    buckets = defaultdict(list)
    counts = Counter()
    missing = Counter()
    for row in iter_rows(input_path):
        path = normalized_path(row.get('path'))
        if path[:2] != ('viral', 'phage'):
            continue
        cls = str(row.get('cluster_class') or (path[-1] if len(path)>3 else 'phage_non_struct'))
        counts[cls] += 1
        try:
            similarity = float(row['cluster_similarity'])
            threshold = float(row['cluster_similarity_threshold'])
            if not math.isfinite(similarity) or not math.isfinite(threshold) or int(row.get('cluster_id', -1)) < 0:
                raise ValueError('Missing similarity or assignment')
            buckets[cls].append((similarity,threshold))
        except (KeyError, TypeError, ValueError):
            missing[cls] += 1
    config = Path(__file__).resolve().parent / 'artifacts/recommended_thresholds_config.json'
    configured = json.loads(config.read_text())['thresholds_by_class'] if config.is_file() else {}
    rows = []
    for cls in ('phage_non_struct', *STRUCTURAL_CLASSES):
        values = buckets[cls]
        thresholds = sorted({t for _,t in values})
        passed = sum(s>=t for s,t in values)
        similarities = [s for s,_ in values]
        rows.append(dict(class_name=cls, threshold=', '.join(f'{t:g}' for t in thresholds) if thresholds else configured.get(cls,''),
                         threshold_source='predictions' if thresholds else 'current_config_no_comparable_predictions',
                         proteins=counts[cls], comparable=len(values), passing=passed, below=len(values)-passed,
                         missing=missing[cls], percent_passing=percent(passed, counts[cls]),
                         median_similarity=statistics.median(similarities) if similarities else '',
                         min_similarity=min(similarities) if similarities else '',
                         max_similarity=max(similarities) if similarities else ''))
    if write_table:
        write_csv(out / 'umbrales_similitud_fagos.csv',rows,list(rows[0]))
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2,1,figsize=(12,10))
    for ax,classes,label in [(axes[0],['phage_non_struct'],'Fagos no estructurales'),
                             (axes[1],list(STRUCTURAL_CLASSES),'Fagos estructurales')]:
        values=[s for cls in classes for s,t in buckets[cls]]
        ax.hist(values,bins=35,color=COLORS[0],edgecolor='white')
        thresholds=sorted({t for cls in classes for s,t in buckets[cls]})
        for i,t in enumerate(thresholds):
            ax.axvline(t,color=COLORS[(i+1)%len(COLORS)],ls='--',lw=2,label=f'Umbral {t:g}')
        ax.set(title=f'{label} · n={sum(counts[c] for c in classes):,}',xlabel='Similitud coseno con el prototipo más cercano',ylabel='Proteínas')
        if thresholds:
            ax.legend(fontsize=12)
    fig.tight_layout()
    localize_figure(fig, language)
    fig.savefig(out / 'similitud_fagos.png',dpi=170,bbox_inches='tight')
    fig.savefig(out / 'similitud_fagos.svg',bbox_inches='tight')
    plt.close(fig)
    return rows


def tree_figure(plt, nodes, save):
    """Top-down boxes and arrows; percentages denote counts relative to the parent."""
    fig, ax = plt.subplots(figsize=(15, 10))
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis('off')
    specs = {
        (): (.50, .92, .25, .10, 'Proteínas de inferencia'),
        ('cellular',): (.24, .74, .21, .12, 'Celulares'),
        ('viral',): (.73, .74, .21, .12, 'Virales'),
        ('cellular', 'bacteria'): (.08, .54, .145, .12, 'Bacteria'),
        ('cellular', 'eukaryota'): (.24, .54, .145, .12, 'Eukaryota'),
        ('cellular', 'archaea'): (.40, .54, .145, .12, 'Archaea'),
        ('viral', 'eukaryota'): (.59, .54, .22, .12, 'Virus eucariotas'),
        ('viral', 'phage'): (.86, .54, .22, .12, 'Bacteriófagos'),
        ('viral', 'phage', 'structural'): (.78, .33, .15, .12, 'Estructurales'),
        ('viral', 'phage', 'non_structural'): (.93, .33, .14, .12, 'No estructurales'),
    }
    total = nodes[('GLOBAL', ())]
    for path, (x,y,w,h,label) in specs.items():
        n = nodes[('GLOBAL', path)]
        text = f'{label}\nn = {n:,}' if not path else f'{label}\n{percent(n,nodes[("GLOBAL",path[:-1])]):.1f}%\nn = {n:,}'
        ax.add_patch(plt.Rectangle((x-w/2,y-h/2),w,h,facecolor='#f4f7fa' if not path else 'white',edgecolor='#376487',lw=1.7))
        ax.text(x,y,text,ha='center',va='center',fontsize=15 if len(path)<2 else (14 if len(path)==2 else 13),linespacing=1.4)
    def connect(parent, children):
        px,py,pw,ph,_ = specs[parent]
        target_y = max(specs[c][1]+specs[c][3]/2 for c in children)
        elbow = (py-ph/2+target_y)/2
        ax.plot([px,px],[py-ph/2,elbow],color='#6b7280',lw=1.5)
        xs=[specs[c][0] for c in children]
        ax.plot([min(xs+[px]),max(xs+[px])],[elbow,elbow],color='#6b7280',lw=1.5)
        for c in children:
            x,y,w,h,_ = specs[c]
            ax.annotate('',xy=(x,y+h/2),xytext=(x,elbow),arrowprops={'arrowstyle':'-|>','color':'#6b7280','lw':1.5,'mutation_scale':17})
    connect((), [('cellular',),('viral',)])
    connect(('cellular',), [('cellular','bacteria'),('cellular','eukaryota'),('cellular','archaea')])
    connect(('viral',), [('viral','eukaryota'),('viral','phage')])
    connect(('viral','phage'), [('viral','phage','structural'),('viral','phage','non_structural')])
    for parent, x, width, label in [(('viral','eukaryota'), .59, .19, 'Clases virales (M4)'),
                                   (('viral','phage','structural'), .78, .25, '10 clases estructurales')]:
        y=.33 if len(parent)==2 else .12
        observed = sum(1 for (scope,path),n in nodes.items() if scope=='GLOBAL' and len(path)==len(parent)+1 and path[:-1]==parent and n)
        n = nodes[('GLOBAL',parent)]
        text = f'{label}\n{observed} con asignaciones\nn = {n:,}'
        ax.add_patch(plt.Rectangle((x-width/2,y-.06),width,.12,facecolor='white',edgecolor='#376487',lw=1.7))
        ax.text(x,y,text,ha='center',va='center',fontsize=14,linespacing=1.5)
        _,py,_,ph,_=specs[parent]
        ax.annotate('',xy=(x,y+.06),xytext=(x,py-ph/2),arrowprops={'arrowstyle':'-|>','color':'#6b7280','lw':1.5,'mutation_scale':17})
    ax.text(.02,.01,'Porcentajes = proteínas asignadas / proteínas de la clase padre. No son exactitud ni confianza.',fontsize=13,color='#455a70')
    save(fig, 'cascada_jerarquica')


def localize_figure(fig, language):
    if language == 'es':
        return
    from matplotlib.text import Text
    import re
    for artist in fig.findobj(Text):
        lines = []
        for line in artist.get_text().split('\n'):
            parts = []
            for part in line.split(' · '):
                translated = tr(part, language)
                if translated == part:
                    translated = re.sub(r'^Umbral ', 'Threshold ', part)
                    translated = re.sub(r' con asignaciones$', ' with assignments', translated)
                    translated = re.sub(r' con etiqueta$', ' labeled', translated)
                    translated = re.sub(r' proteínas$', ' proteins', translated)
                parts.append(translated)
            lines.append(' · '.join(parts))
        artist.set_text('\n'.join(lines))


def figures(out, data, language='en'):
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/vydra-report-matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    nodes, edges, totals, levels, taxa, _, _, _ = data
    plt.rcParams.update({'font.size': 14, 'axes.titlesize': 17, 'axes.labelsize': 14,
                         'axes.spines.top': False, 'axes.spines.right': False, 'svg.fonttype': 'none'})
    def save(fig, name):
        localize_figure(fig, language)
        fig.savefig(out / (name + '.png'), dpi=170, bbox_inches='tight')
        fig.savefig(out / (name + '.svg'), bbox_inches='tight')
        plt.close(fig)
    tree_figure(plt, nodes, save)
    parents = [(), ('cellular',), ('viral',), ('viral','phage'), ('viral','phage','structural')]
    fig, ax = plt.subplots(figsize=(15, 8.5))
    for y, parent in enumerate(parents):
        left = 0
        if parent == ('viral','phage','structural'):
            children = [(parent+(label,), nodes[('GLOBAL',parent+(label,))]) for label in STRUCTURAL_CLASSES]
        else:
            children = sorted((c,n) for (s,p,c),n in edges.items() if s=='GLOBAL' and p==parent)
        for i,(child,n) in enumerate(children):
            width = percent(n,nodes[('GLOBAL',parent)])
            ax.barh(y,width,left=left,height=.62,color=COLORS[i % len(COLORS)])
            if parent == ('viral','phage','structural'):
                if width >= 4:
                    ax.text(left+width/2,y,f'{i+1}\n{width:.1f}%',ha='center',va='center',fontsize=12)
            elif width >= 9:
                ax.text(left+width/2,y,f'{child[-1]}\n{width:.1f}% · {n:,}',ha='center',va='center',fontsize=13)
            else:
                ax.text(0,y+.42,f'{child[-1]}: {width:.1f}% · {n:,}',va='center',fontsize=12)
            left += width
    labels=['TOTAL','cellular','viral','viral / phage','phage / structural']
    ax.set(yticks=range(len(parents)),yticklabels=labels,xlim=(0,100),xlabel='% dentro de la clase padre',
           title=f'Cascada por padre · {nodes[("GLOBAL",())]:,} proteínas')
    ax.invert_yaxis()
    legend=[]
    structural_total=nodes[('GLOBAL',('viral','phage','structural'))]
    for i,label in enumerate(STRUCTURAL_CLASSES):
        n=nodes[('GLOBAL',('viral','phage','structural',label))]
        legend.append(plt.Rectangle((0,0),1,1,color=COLORS[i]))
    legend_labels=[f'{i+1}. {label} · n={nodes[("GLOBAL",("viral","phage","structural",label))]:,} · {percent(nodes[("GLOBAL",("viral","phage","structural",label))],structural_total):.1f}%'
                   for i,label in enumerate(STRUCTURAL_CLASSES)]
    ax.legend(legend,legend_labels,loc='upper left',bbox_to_anchor=(0,-.16),ncol=2,frameon=False,fontsize=12.5,title='Las 10 clases estructurales (M6)',title_fontsize=15)
    save(fig,'cascada_por_padre')
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5), sharex=True)
    for ax, group in zip(axes, ('viral_euk', 'phage')):
        n = totals[('GLOBAL', group)]
        counts = [levels[('GLOBAL', group, level)] for level in LEVELS]
        ax.barh(range(len(LEVELS)), [percent(c, n) for c in counts], color=COLORS[:len(LEVELS)])
        ax.set(yticks=range(len(LEVELS)), yticklabels=[LABELS[l] for l in LEVELS], xlim=(0, 112), title=f'{group} · n={n:,}', xlabel='% de proteínas de la rama')
        ax.invert_yaxis()
        for i, c in enumerate(counts):
            ax.text(percent(c, n)+1, i, f'{c:,} ({percent(c,n):.1f}%)', va='center', fontsize=12)
    fig.suptitle('Mejor nivel de referencia · conserva etiquetas originales, incluidos casos bajo umbral FAISS')
    fig.tight_layout()
    save(fig, 'resolucion_taxonomica')
    for group in ('viral_euk', 'phage'):
        fig, axes = plt.subplots(3, 1, figsize=(12, 20))
        for ax, rank in zip(axes, RANKS):
            items = ordered(taxa[('GLOBAL', group, rank)])
            known = sum(n for _, n in items)
            top = items[:10]
            ax.barh(range(len(top)), [n for _, n in top], color=COLORS[0])
            ax.set(yticks=range(len(top)), yticklabels=[textwrap.fill(name, 40) for name, _ in top], title=RANK_LABELS[rank], xlabel=f'Proteínas · {known:,} con etiqueta')
            ax.invert_yaxis()
            if not items:
                ax.set_xlim(0, 1)
                ax.set_xticks([])
                ax.text(.5, .5, 'Sin asignaciones disponibles', transform=ax.transAxes, ha='center')
        fig.suptitle(f'{group} · Top 10 por rango; nombres virales solo como contexto')
        fig.tight_layout(rect=(0,0,1,.96))
        save(fig, f'top10_{group}')


def dashboard(out, data, result_tables, similarity_rows, source_rows=(), sequence_export='gzip', language='en'):
    nodes, edges, totals, _, _, _, _, _ = data
    hierarchy, resolution, rankings, dominance = result_tables
    payload = json.dumps(dict(hierarchy=hierarchy, resolution=resolution, rankings=rankings, dominance=dominance), ensure_ascii=False).replace('<', '\\u003c')
    document = '''<!doctype html><html lang="es"><meta charset="utf-8"><title>Vydra · Informe de inferencia</title>
<style>body{font:19px/1.65 system-ui;color:#17324d;background:#f5f7fa;max-width:1250px;margin:30px auto;padding:0 20px}section{background:white;padding:24px;border-radius:12px;margin:22px 0}h1,h2{color:#17324d}img{max-width:100%;height:auto}select{font:inherit} .figure{overflow-x:auto} .figure img{min-width:1000px} .vertical-figure{max-width:1000px;margin:auto}select{padding:10px;max-width:90%;margin:6px}table{border-collapse:collapse;width:100%;font-size:17px}td,th{padding:7px;text-align:left;border-bottom:1px solid #ddd}.scroll{max-height:460px;overflow:auto}.note{padding:15px;background:#fff2cd}svg{max-width:100%}</style>
<h1>Vydra · Informe de inferencia</h1><p>COUNT proteínas · conteos de proteínas, no abundancia de organismos.</p>
<p class="note">Los nombres virales dominantes se presentan como contexto de las referencias. Viral_Euk puede usar el resumen local de clases reconstruido después de la inferencia; consulte procedencia.json. Las etiquetas taxonómicas se heredan de grupos de referencia, no de validación independiente por proteína.</p>
<section><h2>Cascada jerárquica</h2><div class="figure"><img src="cascada_jerarquica.svg" alt="Árbol de clasificación con cajas y flechas"></div><p>Porcentajes respecto al padre; no representan exactitud ni confianza. Las clases finas se consultan en el selector.</p><h3>Reparto dentro de cada padre</h3><div class="figure"><img src="cascada_por_padre.png" alt="Barras por padre, incluidas las diez clases estructurales"></div><label>Ámbito <select id="scope"></select></label><label>Clase padre <select id="parent"></select></label><div id="branches"></div></section>
<section><h2>Control de similitud FAISS</h2><p>BELOW de PHAGE proteínas de fagos tienen similitud menor al umbral informado. Las figuras conservan las etiquetas originales; <a href="resolucion_control_umbral.csv">esta tabla adicional</a> las separa en below_threshold. No confundir etiquetas heredadas con asignación que cumple el umbral.</p><p>El criterio es <strong>similitud coseno ≥ umbral informado por clase</strong>, entre embeddings ProstT5 normalizados y su prototipo más cercano; no es identidad de aminoácidos. El motor devuelve el vecino más cercano sin rechazar por este umbral: aquí se compara después. Son los umbrales de la configuración de referencia informados por la corrida, no un filtro taxonómico validado para proteínas nuevas.</p><div class="scroll">THRESHOLD_TABLE</div><div class="vertical-figure"><img src="similitud_fagos.png" alt="Distribución de similitud frente a los umbrales"></div><p>La mediana indica dónde cae la mitad de las similitudes de cada clase. Cumplir el umbral no garantiza resolución de género o familia: también se requiere una referencia con metadatos suficientemente homogéneos.</p><a href="umbrales_similitud_fagos.csv">Descargar umbrales y conteos por clase</a></section><section><h2>Resolución taxonómica</h2><img src="resolucion_taxonomica.png"><p>Categorías exclusivas: mejor nivel disponible. Género y familia en los rankings son conteos independientes y pueden solaparse.</p><div id="resolutionTable"></div></section>
<section><h2>Top 10 y distribución completa</h2><label>Clase <select id="group"></select></label><label>Rango <select id="rank"><option value="genus">Género</option><option value="family">Familia</option><option value="virus_name_context">Nombre viral de referencia</option></select></label><p id="stats"></p><div id="pie"></div><p>Cada sector corresponde a una etiqueta; todos se conservan. Pase el cursor para ver nombre y conteo. Sin etiqueta usa gris. La tabla permite revisar sectores pequeños.</p><div class="scroll" id="ranking"></div></section>
<section><h2>Figuras para entregar</h2><a href="cascada_por_padre.svg">Cascada (% del padre)</a> · <a href="resolucion_taxonomica.svg">Resolución</a><p>Las barras Top 10 muestran las etiquetas que reúnen más proteínas: cada barra es una etiqueta y su longitud es el número de proteínas asignadas. Solo aparecen las diez más frecuentes; la tabla interactiva y los CSV conservan todas. Género y familia se leen por separado, y los nombres virales son contexto de la referencia.</p><h3>Virus eucariotas</h3><div class="vertical-figure"><img src="top10_viral_euk.png"></div><h3>Fagos</h3><div class="vertical-figure"><img src="top10_phage.png"></div></section>
<section><h2>Datos y método</h2><a href="README.txt">Guía breve de archivos</a> · <a href="jerarquia.csv">Jerarquía</a> · <a href="resolucion_taxonomica.csv">Resolución</a> · <a href="taxones_todos.csv">Todos los taxones</a> · <a href="taxones_top10.csv">Top 10</a> · <a href="dominancia.csv">Dominancia</a> · <a href="calidad_anotacion.csv">Calidad</a> · <a href="asignaciones_taxonomicas.csv">Auditoría por proteína</a></section>
<script>const D=PAYLOAD;const $=id=>document.getElementById(id);const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const options=(id,values)=>{$(id).innerHTML=values.map(v=>`<option>${esc(v)}</option>`).join('')};
options('scope',[...new Set(D.hierarchy.map(r=>r.scope))]);
function parents(){options('parent',[...new Set(D.hierarchy.filter(r=>r.scope==$('scope').value).map(r=>r.parent))]);options('group',[...new Set(D.resolution.filter(r=>r.scope==$('scope').value).map(r=>r.class))]);draw()}
function table(rows,keys){return '<table><thead><tr>'+keys.map(k=>'<th>'+esc(k)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+keys.map(k=>'<td>'+esc(typeof r[k]=='number'?Number(r[k].toFixed(2)):r[k])+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function draw(){let scope=$('scope').value;let branches=D.hierarchy.filter(r=>r.scope==scope&&r.parent==$('parent').value);$('branches').innerHTML=table(branches,['child','count','percent_parent','percent_total']);let group=$('group').value,rank=$('rank').value;$('resolutionTable').innerHTML=table(D.resolution.filter(r=>r.scope==scope&&r.class==group),['class','level','count','percent_class']);let rows=D.rankings.filter(r=>r.scope==scope&&r.class==group&&r.rank==rank);let stat=D.dominance.find(r=>r.scope==scope&&r.class==group&&r.rank==rank);if(!stat){$('stats').textContent='Sin datos';$('pie').innerHTML='';$('ranking').innerHTML='';return} $('stats').textContent=`${stat.assigned_count} de ${stat.class_count} con etiqueta; ${stat.n_taxa} taxones; top 1: ${stat.top1_percent_assigned.toFixed(1)}% de etiquetas; top 10: ${stat.top10_percent_assigned.toFixed(1)}%.`;
$('ranking').innerHTML=table(rows,['position','taxon','count','percent_assigned','percent_class','cumulative_percent_assigned']);let sectors=rows.map(r=>({name:r.taxon,n:r.count}));if(stat.unassigned_count)sectors.push({name:'Sin etiqueta',n:stat.unassigned_count});let angle=-Math.PI/2,svg='<svg viewBox="0 0 520 330" width="520" role="img" aria-label="Distribución de todos los taxones">';sectors.forEach((s,i)=>{let a=2*Math.PI*s.n/stat.class_count;let color=s.name=='Sin etiqueta'?'#d6dce3':`hsl(${(i*137.508)%360} 58% 48%)`;let title=esc(s.name)+': '+s.n+' ('+(100*s.n/stat.class_count).toFixed(2)+'% de la clase)';if(a>=2*Math.PI-1e-9){svg+=`<circle cx="240" cy="160" r="145" fill="${color}"><title>${title}</title></circle>`}else{let x=240+145*Math.cos(angle),y=160+145*Math.sin(angle),end=angle+a,xx=240+145*Math.cos(end),yy=160+145*Math.sin(end);svg+=`<path d="M240,160 L${x},${y} A145,145 0 ${a>Math.PI?1:0},1 ${xx},${yy} Z" fill="${color}"><title>${title}</title></path>`}angle+=a});$('pie').innerHTML=svg+'</svg>'}
$('scope').onchange=parents;['parent','group','rank'].forEach(id=>$(id).onchange=draw);parents();</script></html>'''
    threshold_table = '<table><thead><tr><th>Clase</th><th>Umbral coseno</th><th>Proteínas</th><th>Cumplen</th><th>% cumplen</th><th>Mediana coseno</th></tr></thead><tbody>'
    for r in similarity_rows:
        median = f'{r["median_similarity"]:.4f}' if r['median_similarity'] != '' else '—'
        threshold_table += f'<tr><td>{html.escape(r["class_name"])}</td><td>{r["threshold"]}</td><td>{r["proteins"]:,}</td><td>{r["passing"]:,}</td><td>{r["percent_passing"]:.2f}%</td><td>{median}</td></tr>'
    threshold_table += '</tbody></table><p>Clases sin proteínas: umbral mostrado desde la configuración actual; no hay comparación observada.</p>'
    sequence_link = ('<a href="secuencias.csv.gz">Todas las secuencias: CSV comprimido (.gz)</a>. Descomprima este archivo para abrir el CSV; contiene los mismos datos sin pérdida.' if sequence_export == 'gzip' else
                     '<a href="secuencias.csv">Todas las secuencias: CSV sin comprimir</a>.' if sequence_export == 'csv' else
                     'La exportación adicional por secuencia está desactivada; consulte las predicciones completas de la corrida.')
    origin_table = '<section><h2>Secuencias y procedencia</h2><p>' + sequence_link + ' Incluye resultados de proteínas celulares y virales, ID y encabezado originales, archivo y carpeta, confianza MLP y datos FAISS disponibles. Es una exportación derivada opcional: el HTML no necesita cargarla. Los campos de origen vacíos indican información no disponible en la entrada.</p><p><a href="README.txt">Qué contiene cada archivo, por qué pesa y cómo usarlo</a> · <a href="origen_archivos.csv">Descargar resumen por archivo</a>. El selector de ámbito incluye archivos/muestras y carpetas.</p><div class="scroll"><table><tr><th>Carpeta</th><th>Archivo</th><th>Proteínas</th><th>Celulares</th><th>Virales</th></tr>'
    for row in source_rows:
        origin_table += '<tr>' + ''.join(f'<td>{html.escape(str(row[k]))}</td>' for k in
                                        ('source_folder', 'source_relative_path', 'sequences', 'cellular', 'viral')) + '</tr>'
    origin_table += '</table></div></section>'
    document = document.replace('<section><h2>Datos y método</h2>', origin_table + '<section><h2>Datos y método</h2>')
    document = document.replace('<p id="stats"></p>', '<p>La distribución muestra cómo se reparten las etiquetas de referencia entre las proteínas. Top 1 es el porcentaje que reúne la etiqueta más frecuente; Top 10 suma las diez más frecuentes. Ambos porcentajes usan solo las proteínas con etiqueta en el rango elegido. Por ejemplo, Top 10 = 70 % significa que esas diez etiquetas reúnen el 70 % de las proteínas con etiqueta; no el 70 % de todas las proteínas analizadas.</p><p id="stats"></p>')
    document = document.replace('<div class="scroll" id="ranking"></div>', '<p>La columna de porcentaje acumulado suma las etiquetas desde la más frecuente hasta cada fila. Siempre llega al 100 % al incluir todas las etiquetas con asignaciones. Una subida rápida indica que pocas etiquetas concentran muchas asignaciones; sirve para describir concentración, no confianza ni abundancia de organismos. Las antiguas curvas de taxones ordenados se han retirado: esta tabla conserva sus datos.</p><div class="scroll" id="ranking"></div>')
    document = document.replace('Categorías exclusivas: mejor nivel disponible.', 'Cada barra indica qué proporción de proteínas tiene ese nivel como mejor etiqueta taxonómica disponible en su referencia. Las categorías son exclusivas: cada proteína cuenta una sola vez. Un género puede conocerse sin que la familia cumpla los criterios de cobertura y pureza.')
    document = document.replace('Porcentajes respecto al padre; no representan exactitud ni confianza.', 'Cada caja cuenta proteínas que siguieron una rama de clasificación. El porcentaje se calcula dentro de su caja padre: por ejemplo, el porcentaje de fagos se calcula sobre las proteínas virales. No representa exactitud ni confianza.')
    document = document.replace('THRESHOLD_TABLE', threshold_table)
    document = document.replace('BELOW', str(data[6][('GLOBAL', 'phage')])).replace('PHAGE', str(totals[('GLOBAL', 'phage')]))
    document = document.replace('COUNT', f'{nodes[("GLOBAL", ())]:,}').replace('PAYLOAD', payload)
    (out / 'informe.html').write_text(bilingual_document(document, language), encoding='utf-8')


FILE_DESCRIPTIONS = {
    'README.txt': 'Guía breve de los archivos del informe.',
    'README_ARCHIVOS.txt': 'Guía breve de los archivos de la corrida.',
    'README_resultados.md': 'Documentación histórica de la corrida.',
    'informe.html': 'Informe interactivo; abrir en un navegador.',
    'predicciones_completas.jsonl': 'Resultados completos: un objeto JSON por proteína; permite regenerar el informe.',
    'predicciones.jsonl': 'Resultados completos guardados por el CLI para el informe.',
    'predicciones_completas.csv': 'Resultados completos en columnas, para análisis.',
    'predicciones_completas.antes_recuperacion_columnas.csv': 'Respaldo anterior; usar el CSV completo actual.',
    'secuencias.csv': 'Exportación adicional por proteína, sin comprimir; opcional.',
    'secuencias.csv.gz': 'Exportación adicional por proteína comprimida sin pérdida; opcional.',
    'manifest_secuencias.csv': 'Relación entre ID interno, ID/encabezado original, archivo y longitud.',
    'metadata_inferencia.json': 'Configuración, modelo, rutas, tiempos y estado de la inferencia.',
    'resumen_general.json': 'Conteos globales de clasificación.',
    'resumen_general.csv': 'Conteos globales en columnas.',
    'resumen_por_archivo.csv': 'Conteos y estadísticas por archivo de origen.',
    'resumen_por_carpeta.csv': 'Conteos y estadísticas por carpeta de origen.',
    'resumen_por_muestra.csv': 'Conteos y estadísticas por muestra.',
    'resumen_por_ruta.csv': 'Conteos por ruta de clasificación.',
    'resumen_clusters.csv': 'Conteos por cluster FAISS de referencia.',
    'secuencias_excluidas.csv': 'Registros descartados y motivo de exclusión.',
    'registro_ejecucion.log': 'Mensajes del proceso de inferencia.',
    'comandos_ejecucion.txt': 'Comandos usados en la inferencia.',
    'input_proteinas_ordenadas.faa': 'Aminoácidos enviados al modelo, ordenados por longitud.',
    'input_combinado.fasta': 'Aminoácidos reunidos con IDs internos para inferencia.',
    'jerarquia.csv': 'Conteos y porcentajes por rama y ámbito.',
    'origen_archivos.csv': 'Archivos, carpetas, rutas, hashes y conteos de origen.',
    'resolucion_taxonomica.csv': 'Conteos por mejor nivel taxonómico de referencia disponible.',
    'resolucion_control_umbral.csv': 'Resolución separando asignaciones bajo el umbral FAISS.',
    'taxones_todos.csv': 'Todas las etiquetas, conteos y porcentajes, incluido el acumulado.',
    'taxones_top10.csv': 'Las diez etiquetas más frecuentes por ámbito, clase y rango.',
    'dominancia.csv': 'Concentración de asignaciones: Top 1, Top 10 y Simpson.',
    'calidad_anotacion.csv': 'Origen de anotaciones y conteos bajo umbral FAISS.',
    'asignaciones_taxonomicas.csv': 'Etiquetas y procedencia por proteína viral; excluye celulares.',
    'umbrales_similitud_fagos.csv': 'Umbrales, conteos y estadísticos de similitud por clase de fago.',
    'procedencia.json': 'Fuentes, hashes y reglas de interpretación del informe.',
    'verificacion_origen.json': 'Comprobaciones registradas de origen y conteos.',
}
FIGURE_DESCRIPTIONS = {
    'cascada_jerarquica': 'Árbol de clasificación y porcentajes dentro del padre.',
    'cascada_por_padre': 'Reparto por padre y clases estructurales M6.',
    'resolucion_taxonomica': 'Mejor nivel taxonómico disponible por rama viral.',
    'similitud_fagos': 'Distribución de similitud FAISS y umbrales.',
    'top10_phage': 'Diez etiquetas más frecuentes de fagos por rango.',
    'top10_viral_euk': 'Diez etiquetas más frecuentes de virus eucariotas por rango.',
}


def file_inventory(directory, report_dir=None, prediction_path=None, language='en'):
    lines = [tr('ARCHIVOS (tamaños en MiB)', language), '']
    figures = defaultdict(list)
    for path in sorted(directory.iterdir()):
        if path.is_dir():
            if path == report_dir:
                lines.append(f'{path.name}/: ' + tr('informe, imágenes y tablas; consultar README.txt dentro.', language))
            elif path.name == 'por_muestra':
                lines.append('por_muestra/*.csv: ' + tr('resultados individuales separados por muestra.', language))
            elif path.name == 'es':
                lines.append('es/: ' + tr('figuras en español; se seleccionan con el switch del informe.', language))
            else:
                lines.append(f'{path.name}/: ' + tr('carpeta auxiliar de resultados.', language))
            continue
        if path.name in ('README.md', 'README_ARCHIVOS.md'):
            continue
        if path.suffix in ('.png', '.svg') and path.stem in FIGURE_DESCRIPTIONS:
            figures[path.stem].append(path.name)
            continue
        description = ('Predicciones del CLI en el formato solicitado.' if path == prediction_path else
                       FILE_DESCRIPTIONS.get(path.name, 'Archivo auxiliar de resultados.'))
        size = '' if path.suffix == '.txt' and path.name.startswith('README') else f' ({path.stat().st_size / 1024**2:.2f} MiB)'
        if path.name in ('README_en.txt', 'README_es.txt', 'README_ARCHIVOS_en.txt', 'README_ARCHIVOS_es.txt'):
            description = 'English file guide.' if '_en.' in path.name else 'Spanish file guide.'
            if language == 'es': description = 'Guía de archivos en inglés.' if '_en.' in path.name else 'Guía de archivos en español.'
        lines.append(f'{path.name}{size}: {tr(description, language)}')
    for stem, names in sorted(figures.items()):
        lines.append(f'{" / ".join(names)}: {tr(FIGURE_DESCRIPTIONS[stem], language)}')
    return lines


def storage_notes(language='en'):
    return [tr(line, language) for line in ['', 'Los archivos grandes repiten resultados y anotaciones por proteína.',
            'Las cadenas de aminoácidos están en los FASTA, no en el CSV ni JSONL.',
            'El HTML no necesita cargar las predicciones ni secuencias.csv.gz para abrirse.',
            'Descomprima .gz para abrir el CSV. Gzip es el formato predeterminado, sin pérdida.',
            'Para omitir esta copia adicional: --sequence-export none; sin comprimir: --sequence-export csv.',
            'Conserve predicciones, manifiesto y metadata para regenerar sin repetir inferencia.', '']]


def write_report_readme(report_dir, language='en'):
    for name in ('README.txt', 'README_en.txt', 'README_es.txt'):
        (report_dir / name).touch(exist_ok=True)
    for lang in ('en', 'es'):
        lines = [tr('INFORME VYDRA', lang), tr('Abrir informe.html; allí se explica cómo leer cada gráfica.', lang),
             'PNG: imágenes para consulta. SVG: imágenes vectoriales para exportar.', '',
             *file_inventory(report_dir, language=lang), *storage_notes(lang)]
        lines[2] = tr(lines[2], lang)
        (report_dir / f'README_{lang}.txt').write_text('\n'.join(lines), encoding='utf-8')
    (report_dir / 'README.txt').write_text((report_dir / f'README_{language}.txt').read_text(), encoding='utf-8')
    (report_dir / 'README.md').unlink(missing_ok=True)


def write_run_readme(run_dir, report_dir, prediction_path=None, language='en'):
    for name in ('README_ARCHIVOS.txt', 'README_ARCHIVOS_en.txt', 'README_ARCHIVOS_es.txt'):
        (run_dir / name).touch(exist_ok=True)
    rel = os.path.relpath(report_dir / 'informe.html', run_dir)
    for lang in ('en', 'es'):
        lines = [tr('RESULTADOS VYDRA', lang), f'{tr("Abrir", lang)} {rel}. ' + tr('Explicaciones de gráficas dentro del HTML.', lang), '',
                 *file_inventory(run_dir, report_dir, prediction_path, lang), *storage_notes(lang)]
        (run_dir / f'README_ARCHIVOS_{lang}.txt').write_text('\n'.join(lines), encoding='utf-8')
    (run_dir / 'README_ARCHIVOS.txt').write_text((run_dir / f'README_ARCHIVOS_{language}.txt').read_text(), encoding='utf-8')
    (run_dir / 'README_ARCHIVOS.md').unlink(missing_ok=True)


def generate_report(input_path, output_dir, taxonomy_path=DEFAULT_TAXONOMY, sequence_export='gzip', language='en'):
    if language not in ('en', 'es'):
        raise ValueError('language must be en or es')
    if sequence_export not in ('gzip', 'csv', 'none'):
        raise ValueError('sequence_export debe ser gzip, csv o none')
    input_path, output_dir = Path(input_path).resolve(), Path(output_dir).resolve()
    metadata_path = input_path.parent / 'metadata_inferencia.json'
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    if metadata:
        state = metadata.get('status')
        if state and state != 'complete':
            raise ValueError(f'La corrida todavía no está completa (status={state}). Espere al cierre.')
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'cascada_sankey.svg').unlink(missing_ok=True)
    taxonomy_path = Path(taxonomy_path).resolve() if taxonomy_path else None
    taxonomy = load_taxonomy(taxonomy_path)
    data = collect(input_path, taxonomy, output_dir / 'asignaciones_taxonomicas.csv')
    source_rows, source_complete = sequence_sources(input_path, output_dir,
                                                  metadata.get('input_root') or metadata.get('input_directory'), sequence_export)
    result_tables = tables(output_dir, data)
    figures(output_dir, data)
    similarity_rows = similarity_report(input_path, output_dir)
    spanish_dir = output_dir / 'es'
    spanish_dir.mkdir(exist_ok=True)
    figures(spanish_dir, data, language='es')
    similarity_report(input_path, spanish_dir, language='es', write_table=False)
    try:
        from .interactive_report import write_interactive_report
    except ImportError:
        from interactive_report import write_interactive_report
    write_interactive_report(input_path, output_dir, taxonomy)
    # These are reproducible outputs owned by the generator; retire obsolete copies.
    for name in ('dominancia_todos_phage.png', 'dominancia_todos_phage.svg',
                 'dominancia_todos_viral_euk.png', 'dominancia_todos_viral_euk.svg'):
        (output_dir / name).unlink(missing_ok=True)
    for name, mode in (('secuencias.csv', 'csv'), ('secuencias.csv.gz', 'gzip')):
        if sequence_export != mode:
            (output_dir / name).unlink(missing_ok=True)
    provenance = dict(schema_version=5, report_design='interactive', default_language='en', report_languages=['en'], input=str(input_path), input_sha256=sha256(input_path),
                      sequence_export=sequence_export,
                      input_root=metadata.get('input_root') or metadata.get('input_directory'), source_files=len(source_rows),
                      proteins_with_source_and_original_id=source_complete,
                      proteins=data[0][('GLOBAL', ())], viral_euk_taxonomy=str(taxonomy_path) if taxonomy_path else None,
                      viral_euk_taxonomy_sha256=sha256(taxonomy_path) if taxonomy_path else None,
                      species_supported=False, source='existing predictions; no model inference repeated',
                      below_threshold_policy='flag only; preserves original engine assignments',
                      counts_unit='protein records', checks=['unique nonempty seq_id', 'valid root path', 'exclusive levels sum to class count', 'children do not exceed parent'])
    (output_dir / 'procedencia.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write_report_readme(output_dir, language)
    if metadata_path.is_file():
        write_run_readme(input_path.parent, output_dir, language=language)
    return provenance


def main():
    parser = argparse.ArgumentParser(description='Genera un informe desde predicciones guardadas, sin repetir la inferencia ni necesitar GPU.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Ejemplo:\n  python scripts/report_inference.py --input results/inference/corrida/predicciones_completas.jsonl\n\nGenera HTML, figuras, tablas y guías TXT. Exportación adicional: gzip por defecto.')
    parser.add_argument('--input', required=True, type=Path, help='Predicciones completas CSV o JSONL de una corrida terminada')
    parser.add_argument('--output', type=Path, help='Default: directorio de entrada / informe_inferencia')
    parser.add_argument('--viral-euk-taxonomy', type=Path, default=DEFAULT_TAXONOMY,
                        help='CSV de referencia para enriquecer clases de virus eucariotas; por defecto usa el resumen local del proyecto')
    parser.add_argument('--no-taxonomy-enrichment', action='store_true',
                        help='No cruzar clases con el CSV taxonómico; conserva las anotaciones ya guardadas')
    parser.add_argument('--sequence-export', choices=('gzip', 'csv', 'none'), default='gzip',
                        help='Tabla adicional por secuencia: comprimida sin pérdida (default), CSV o sin exportación')
    parser = localize_parser(parser, language_from_argv())
    args = parser.parse_args()
    result = generate_report(args.input, args.output or args.input.parent / 'informe_inferencia',
                             None if args.no_taxonomy_enrichment else args.viral_euk_taxonomy, args.sequence_export, args.language)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
