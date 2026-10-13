"""Portable original FASTA records and run timing for standalone offline reports."""
import base64
import csv
import gzip
import json
import re
from pathlib import Path


def original_records(text):
    """Preserve full header text and residue spelling; only line wrapping is normalized."""
    header, pieces = None, []
    for line in text.splitlines():
        if line.lstrip().startswith('>'):
            if pieces:
                yield header if header is not None else 'query_1', ''.join(pieces)
            header, pieces = line.lstrip()[1:], []
        elif line.strip():
            pieces.append(''.join(line.split()))
    if pieces:
        yield header if header is not None else 'query_1', ''.join(pieces)


def write_original_snapshot(path, records):
    with Path(path).open('w', encoding='utf-8') as stream:
        for sid, header, sequence in records:
            stream.write(json.dumps({'seq_id': sid, 'header': header, 'sequence': sequence}, ensure_ascii=False) + '\n')


def fasta_payload(input_path, rows, metadata):
    input_path = Path(input_path).resolve()
    path = Path(metadata.get('original_sequences_path') or input_path.parent / 'original_sequences.jsonl')
    if not path.is_absolute():
        path = input_path.parent / path
    wanted = {r['id'] for r in rows}
    found = set()
    compressed = bytearray()
    # Compress as a stream to avoid holding another full uncompressed sequence copy.
    import io
    buffer = io.BytesIO()
    if metadata.get('input_type') != 'embedding' and path.is_file():
        with gzip.GzipFile(fileobj=buffer, mode='wb', mtime=0) as target, path.open(encoding='utf-8') as source:
            for line in source:
                record = json.loads(line)
                sid = record['seq_id']
                if sid not in wanted:
                    continue
                if sid in found:
                    raise ValueError(f'Duplicate original FASTA snapshot ID: {sid}')
                if '\n' in record['header'] or '\r' in record['header']:
                    raise ValueError(f'Invalid original FASTA header: {sid}')
                found.add(sid)
                target.write((json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8'))
        compressed = buffer.getvalue()
    for row in rows:
        row['fasta_available'] = row['id'] in found
    return {'encoding': 'gzip-base64-jsonl', 'records': len(found),
            'data': base64.b64encode(compressed).decode('ascii') if compressed else ''}


def update_report_timing(report_dir, timing):
    timing = {k: timing[k] for k in ('inference_seconds', 'elapsed_seconds', 'report_seconds',
              'total_processing_seconds', 'started_at', 'finished_at', 'scope', 'fixture') if k in timing}
    with (Path(report_dir) / 'tiempos.csv').open('w', encoding='utf-8', newline='') as stream:
        fields = ['inference_seconds', 'report_seconds', 'total_processing_seconds', 'started_at', 'finished_at']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow({k: timing.get(k) for k in fields})
    path = Path(report_dir) / 'informe.html'
    if not path.is_file():
        return
    payload = json.dumps(timing, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    document = re.sub(r'(<script type="application/json" data-el="run">).*?(</script>)',
                      lambda m: m[1] + payload + m[2], path.read_text(encoding='utf-8'), flags=re.S)
    path.write_text(document, encoding='utf-8')
    provenance = Path(report_dir) / 'procedencia.json'
    if provenance.is_file():
        data = json.loads(provenance.read_text())
        data['run_timing'] = timing
        provenance.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
