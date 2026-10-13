"""Build an explicitly synthetic portable HTML fixture for browser export tests."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vydra_core'))
from interactive_report import write_interactive_report
from report_payloads import write_original_snapshot, update_report_timing


def create(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows, snapshots = [], []
    for i in range(12):
        sid = f'fixture_{i}'
        route = (['viral', 'phage', 'structural', 'collar'] if i < 8 else
                 ['viral', 'phage', 'structural', 'portal'] if i < 10 else
                 ['viral', 'eukariota', '372'] if i == 10 else ['cellular', 'bacteria'])
        header = ('duplicate' if i < 2 else sid) + f' |original annotation {i}| country=Mexico |'
        row = dict(seq_id=sid, original_id=header.split()[0], original_header=header,
                   path=route, length=6, source_relative_path='fixture.faa', source_folder='.',
                   confidences={'M1': .99}, cluster_id=1, cluster_nearest_seq_id='ref0',
                   cluster_similarity=.999, cluster_similarity_threshold=.97)
        if route[1] == 'phage':
            row['nearest_neighbors'] = [dict(rank=j+1, seq_id=f'ref{j}', cluster_id=1 if j<3 else 2,
                  similarity=.999-j*.001, product='hypothetical protein' if j==0 else 'collar protein',
                  function_annotation_status='unspecified' if j==0 else 'description_available',
                  genus='ExampleGenus' if j<4 else '', family='ExampleFamily', host='ExampleHost') for j in range(5)]
            row['cluster_annotation'] = dict(best_taxonomic_level='mixed_or_functional', n_sequences=100,
                  dominant_genus='OtherGenus', genus_coverage=.9, genus_purity=.6,
                  representative_seq_id='representative', representative_product='other protein',
                  dominant_family='ExampleFamily', family_purity=1, family_coverage=1)
        elif route[0] == 'viral':
            row['viral_euk_class_metadata'] = dict(class_number='372', protein_description='hypothetical protein',
                  protein_function_class='Hypothetical', cluster_rep_sequence_accession='published_accession',
                  family_label_ncbi_2023='ExampleEukFamily')
        else:
            row['cluster_id'] = -1
            row['cluster_similarity'] = None
            row['cluster_nearest_seq_id'] = ''
        rows.append(row)
        snapshots.append((sid, header, 'MeKLL*'))
    source = root / 'predictions.jsonl'
    source.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    write_original_snapshot(root / 'original_sequences.jsonl', snapshots)
    write_interactive_report(source, root, {})
    update_report_timing(root, dict(inference_seconds=2.5, report_seconds=.5, total_processing_seconds=3,
                        fixture='Synthetic demonstration; not measured model inference'))
    (root / 'README.txt').write_text('Synthetic demonstration for UI and export validation. Taxa, scores and timings are illustrative, not model results.\n')
    return root / 'informe.html'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(create(parser.parse_args().output))
