import base64
import csv
import gzip
import json
import re
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vydra_core'))
from biological_context import flatten_output, neighbors_from_row, summarize_neighbors, function_annotation_status
from interactive_report import write_interactive_report
from report_payloads import original_records, write_original_snapshot, update_report_timing, fasta_payload
from folder_inputs import prepare_inputs


class ReferenceEvidenceTests(unittest.TestCase):
    def test_agreement_uses_known_denominator_and_retains_disagreement(self):
        rows = [dict(cluster_id=1, genus='A', product='hypothetical protein', function_annotation_status='unspecified'),
                dict(cluster_id=2, genus='B', product='putative helicase', function_annotation_status='candidate_description'),
                dict(cluster_id=2, genus='A', product='', function_annotation_status='unavailable')]
        summary = summarize_neighbors(rows)
        self.assertEqual(summary['genus_dominant_count'], 2)
        self.assertEqual(summary['genus_unique'], 2)
        self.assertEqual(summary['genus_agreement'], 2/3)
        self.assertEqual(summary['family_known'], 0)
        self.assertIsNone(summary['family_agreement'])
        self.assertEqual(summary['n_with_function_description'], 1)

    def test_numbered_csv_neighbors_roundtrip_without_taxon_columns(self):
        row = dict(path=['viral', 'phage'], nearest_neighbors=[dict(rank=1, seq_id='a', cluster_id=4,
                   similarity=.987, product='protein, with commas', genus='G')],
                   neighbor_summary={'genus_values': {'G': 1}})
        flat = flatten_output(row)
        self.assertEqual(flat['path'], 'viral/phage')
        self.assertNotIn('neighbor_summary.genus_values.G', flat)
        self.assertEqual(json.loads(flat['neighbor_summary.genus_values']), {'G': 1})
        self.assertEqual(neighbors_from_row({k: str(v) for k, v in flat.items()}), row['nearest_neighbors'])

    def test_uncertain_description_is_not_unknown_function(self):
        self.assertEqual(function_annotation_status('Hypothetical protein gp2'), 'unspecified')
        self.assertEqual(function_annotation_status('uncharacterized protein'), 'unspecified')
        self.assertEqual(function_annotation_status('putative major capsid protein'), 'candidate_description')
        self.assertEqual(function_annotation_status('major capsid protein'), 'description_available')

    def test_portable_fasta_snapshot_and_no_false_taxonomic_consensus(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'predictions.jsonl'
            text = '>same |full original annotation|\nMeKL*\n>same second annotation\nMEL\n'
            original = list(original_records(text))
            write_original_snapshot(root / 'original_sequences.jsonl', [('a', *original[0]), ('b', *original[1])])
            rows = [dict(seq_id='a', original_id='same', path=['viral', 'phage', 'structural', 'collar'],
                         cluster_nearest_seq_id='near', nearest_neighbors=[dict(rank=1, seq_id='near', cluster_id=1, similarity=.9, genus='G', family='F'),
                                                                          dict(rank=2, seq_id='other', cluster_id=2, similarity=.89, genus='H', family='F')]),
                    dict(seq_id='b', original_id='same', path=['viral', 'eukariota', '372'],
                         viral_euk_class_metadata=dict(class_number='372', protein_description='hypothetical protein', protein_function_class='Hypothetical'))]
            source.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            document = write_interactive_report(source, root, {}).read_text()
            def payload(name):
                return json.loads(re.search(f'<script type="application/json" data-el="{name}">(.*?)</script>', document, re.S)[1])
            data = {r['id']: r for r in payload('data')}
            self.assertEqual(data['a']['nearest'], 'near')
            self.assertEqual(data['a']['neighbor_genus'], '')
            self.assertEqual(data['a']['neighbor_family'], 'F')
            self.assertEqual(data['b']['official']['protein_description'], 'hypothetical protein')
            fasta = payload('fasta')
            restored = [json.loads(line) for line in gzip.decompress(base64.b64decode(fasta['data'])).decode().splitlines()]
            self.assertEqual(restored[0]['header'], original[0][0])
            self.assertEqual(restored[0]['sequence'], 'MeKL*')
            self.assertTrue(all(r['fasta_available'] for r in data.values()))
            update_report_timing(root, dict(inference_seconds=2, total_processing_seconds=3))
            self.assertTrue((root / 'tiempos.csv').is_file())

    def test_folder_snapshot_restores_excluded_record_order_and_terminal_stop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / 'input'; inputs.mkdir()
            outputs = root / 'out'; outputs.mkdir()
            (inputs / 'a.faa').write_text('>duplicate long | metadata |\nMeKLL*\n>dna\nACGT\n>duplicate short\nMEL\n')
            _, _, manifest, _ = prepare_inputs(inputs, outputs)
            records = [json.loads(line) for line in (outputs / 'original_sequences.jsonl').read_text().splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]['header'], 'duplicate long | metadata |')
            self.assertEqual(records[0]['sequence'], 'MeKLL*')
            self.assertEqual(records[1]['seq_id'], 'F001_R0000003')
            self.assertTrue(manifest[0]['terminal_stop_removed'])

    def test_relative_snapshot_and_embedding_input_do_not_reuse_original_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_original_snapshot(root / 'original_sequences.jsonl', [('a', 'header', 'MEK')])
            relative = Path(os.path.relpath(root / 'predictions.jsonl'))
            rows = [{'id': 'a'}]
            self.assertEqual(fasta_payload(relative, rows, {})['records'], 1)
            self.assertEqual(fasta_payload(relative, rows, {'input_type': 'embedding'})['records'], 0)
            self.assertFalse(rows[0]['fasta_available'])


class ExactRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from vydra_core import engine
        cls.engine = engine

    def bank(self, n=6):
        engine = self.engine
        vectors = np.zeros((n, engine.EMB_DIM), dtype=np.float32)
        for i in range(n):
            vectors[i, :2] = [1, i/10]
        vectors = engine.normalize_matrix(vectors)
        from vydra_core.gpu_faiss import build_index
        bank = {'collar': dict(index=build_index(vectors, device='cpu'), dataset_type='structural',
                seq_ids=np.array([f'ref{i}' for i in range(n)]), cluster_ids=np.array([i%2 for i in range(n)]),
                metadata=[dict(product='hypothetical protein' if i==0 else 'collar protein', family='F') for i in range(n)])}
        return vectors[0], bank

    def test_top_five_include_alternative_clusters_and_keep_assignment(self):
        query, bank = self.bank()
        previous = self.engine.assign_cluster_prototype(query, 'collar', bank)
        result = self.engine.retrieve_reference_neighbors(query, 'collar', bank)
        self.assertEqual(len(result), 5)
        self.assertEqual((result[0]['cluster_id'], result[0]['similarity'], result[0]['seq_id']), previous)
        self.assertEqual({r['cluster_id'] for r in result}, {0, 1})
        self.assertEqual(result[0]['function_annotation_status'], 'unspecified')
        self.assertEqual([r['similarity'] for r in result], sorted([r['similarity'] for r in result], reverse=True))

    def test_small_or_missing_bank(self):
        query, bank = self.bank(2)
        self.assertEqual(len(self.engine.retrieve_reference_neighbors(query, 'collar', bank)), 2)
        self.assertEqual(self.engine.retrieve_reference_neighbors(query, 'unknown', bank), [])

    def test_equal_score_ties_keep_legacy_nearest(self):
        query, bank = self.bank(2)
        searches = [(np.array([[1., 1.]]), np.array([[1, 0]])), (np.array([[1.]]), np.array([[0]]))]
        with patch.object(self.engine.gpu_faiss, 'search_index', side_effect=searches):
            result = self.engine.retrieve_reference_neighbors(query, 'collar', bank)
        self.assertEqual([r['seq_id'] for r in result], ['ref0', 'ref1'])

    def test_cellular_and_viral_euk_never_retrieve_neighbors(self):
        for predictions in [[('cellular', .9), ('bacteria', .9)], [('viral', .9), ('eukariota', .9), ('372', .9)]]:
            with patch.object(self.engine, 'release_prost_t5'), patch.object(self.engine, 'predict_step', side_effect=predictions), patch.object(self.engine, 'retrieve_reference_neighbors') as retrieve:
                row = self.engine.run_hierarchy(np.ones(self.engine.EMB_DIM))
                self.assertEqual(row['nearest_neighbors'], [])
                retrieve.assert_not_called()


if __name__ == '__main__':
    unittest.main()
