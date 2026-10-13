"""Reference evidence helpers; summaries are descriptive, not query predictions."""
from collections import Counter
import csv
import gzip
import json
import re
from pathlib import Path

REFERENCE_FIELDS = ('accession', 'phrog_id', 'local_protein_id', 'vi_id', 'product',
                    'organism', 'virus_name', 'genus', 'family', 'host',
                    'length', 'sequence_length', 'country', 'collection_date',
                    'source_fasta', 'header_format', 'header')


def function_annotation_status(product):
    text = str(product or '').strip().lower()
    if not text:
        return 'unavailable'
    if re.search(r'\b(hypothetical|uncharacterized|unknown function)\b', text):
        return 'unspecified'
    if re.search(r'\b(putative|probable|predicted)\b', text):
        return 'candidate_description'
    return 'description_available'


def load_reference_metadata(path, dataset_type=None):
    if not Path(path).is_file():
        return {}
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        return {(r['dataset_type'], r['class_name'], r['seq_id']):
                {k: r.get(k, '') for k in REFERENCE_FIELDS} for r in csv.DictReader(stream)
                if dataset_type is None or r['dataset_type'] == dataset_type}


def summarize_neighbors(neighbors):
    result = {'n_neighbors': len(neighbors),
              'n_distinct_clusters': len({n['cluster_id'] for n in neighbors}),
              'scope': 'nearest prototypes within predicted class',
              'interpretation': 'reference context; not a calibrated query taxonomic or functional prediction'}
    for field in ('genus', 'family', 'product', 'host'):
        values = [str(n.get(field) or '').strip() for n in neighbors]
        known = [v for v in values if v]
        counts = Counter(known)
        # Break ties by retrieval order; never label a tie as agreement.
        dominant = max(counts, key=counts.get) if counts else ''
        count = counts.get(dominant, 0)
        result.update({f'{field}_dominant': dominant, f'{field}_known': len(known),
                       f'{field}_dominant_count': count, f'{field}_unique': len(counts),
                       f'{field}_coverage': len(known) / len(neighbors) if neighbors else 0,
                       f'{field}_agreement': count / len(known) if known else None,
                       f'{field}_values': dict(counts)})
    result['n_with_function_description'] = sum(
        n.get('function_annotation_status') in ('description_available', 'candidate_description')
        for n in neighbors)
    return result


def flatten_output(obj, prefix=''):
    """CSV schema: paths stay slash-separated; ranked references get numbered columns."""
    result = {}
    for key, value in obj.items():
        name = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict) and key.endswith('_values'):
            result[name] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        elif isinstance(value, dict):
            result.update(flatten_output(value, name))
        elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            for rank, item in enumerate(value, 1):
                result.update(flatten_output(item, f'{name}.{rank}'))
        elif isinstance(value, list):
            result[name] = '/'.join(str(v) for v in value) if key == 'path' else json.dumps(value, ensure_ascii=False)
        else:
            result[name] = value
    return result


def neighbors_from_row(row):
    value = row.get('nearest_neighbors')
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.startswith('['):
        return json.loads(value)
    neighbors = []
    for rank in range(1, 6):
        prefix = f'nearest_neighbors.{rank}.'
        entry = {k[len(prefix):]: v for k, v in row.items() if k.startswith(prefix)}
        if entry.get('seq_id'):
            for key in ('rank', 'cluster_id'):
                entry[key] = int(entry[key])
            entry['similarity'] = float(entry['similarity'])
            neighbors.append(entry)
    return neighbors
