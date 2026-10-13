"""Bundle source annotations for the exact deployed phage prototypes, without new inference."""
import argparse
import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vydra_core'))
from biological_context import REFERENCE_FIELDS


def export(metadata, artifacts):
    wanted = {}
    for dataset, name in [('structural', 'Struct_prototype_bank.csv'),
                          ('non_structural', 'Non_Struct_prototype_bank.csv')]:
        with (artifacts / name).open(encoding='utf-8', newline='') as stream:
            for row in csv.DictReader(stream):
                wanted[(dataset, row['class_name'], row['seq_id'])] = None
    with metadata.open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            key = (row['dataset_type'], row['class_name'], row['seq_id'])
            if key in wanted:
                existing = wanted[key]
                if existing is None or sum(bool(row.get(k)) for k in REFERENCE_FIELDS) > sum(bool(existing.get(k)) for k in REFERENCE_FIELDS):
                    wanted[key] = row
    destination = artifacts / 'prototype_sequence_metadata.csv.gz'
    fields = ['dataset_type', 'class_name', 'seq_id', *REFERENCE_FIELDS]
    with gzip.open(destination, 'wt', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for key, row in sorted(wanted.items()):
            writer.writerow({**dict(zip(fields[:3], key)), **{k: (row or {}).get(k, '') for k in REFERENCE_FIELDS}})
    def digest(path):
        result = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                result.update(chunk)
        return result.hexdigest()
    def source_label(path):
        try:
            return str(path.resolve().relative_to(ROOT))
        except ValueError:
            return path.name
    provenance = {'prototypes': len(wanted), 'matched_metadata': sum(v is not None for v in wanted.values()),
                  'missing_metadata': [list(k) for k, v in wanted.items() if v is None],
                  'output': source_label(destination), 'source_sha256': digest(metadata),
                  'source': source_label(metadata), 'metadata_source': 'existing FASTA headers; no new biological validation',
                  'bank_csv_sha256': {name: digest(artifacts / name) for name in ['Struct_prototype_bank.csv', 'Non_Struct_prototype_bank.csv']}}
    (artifacts / 'prototype_metadata_provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return provenance


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata', type=Path, default=ROOT / 'data/metadata/phage_sequence_metadata.csv')
    parser.add_argument('--artifacts', type=Path, default=ROOT / 'vydra_core/artifacts')
    args = parser.parse_args()
    print(json.dumps(export(args.metadata, args.artifacts), indent=2))
