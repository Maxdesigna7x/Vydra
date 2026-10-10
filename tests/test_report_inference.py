import csv
import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('report_inference', Path(__file__).resolve().parents[1] / 'Vydra_Docker_HF/inference_report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ReportInferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / 'predictions.jsonl'
        self.taxonomy = {'7': {'best_taxonomic_level': 'family', 'dominant_family': 'FamilyV',
                               'family_purity': '.99', 'family_coverage': '1', 'dominant_virus_name': 'Reference V'}}
        self.rows = [
            {'seq_id': 'a', 'path': ['cellular', 'bacteria'], 'sample_id': 'S1'},
            {'seq_id': 'b', 'path': ['viral', 'eukariota', '7'], 'sample_id': 'S1'},
            {'seq_id': 'c', 'path': ['viral', 'phage', 'non_structural'], 'sample_id': 'S2',
             'cluster_similarity': .9, 'cluster_similarity_threshold': .95,
             'cluster_annotation': {'best_taxonomic_level': 'genus', 'dominant_genus': 'GenusP',
                                    'dominant_family': 'FamilyP', 'family_purity': 1, 'family_coverage': 1,
                                    'dominant_virus_name': 'Reference P'}},
            {'seq_id': 'd', 'path': ['viral', 'phage', 'non_structural'], 'sample_id': 'S2',
             'cluster_annotation': {'best_taxonomic_level': 'mixed_or_functional', 'dominant_genus': 'Untrusted',
                                    'dominant_family': 'Untrusted', 'dominant_virus_name': 'Reference P'}},
        ]
        self.write_rows()

    def tearDown(self):
        self.temp.cleanup()

    def write_rows(self):
        self.input.write_text(''.join(json.dumps(row)+'\n' for row in self.rows))

    def collect(self):
        return report.collect(self.input, self.taxonomy, self.root / 'audit.csv')

    def test_parent_percentages_and_exclusive_levels(self):
        data = self.collect()
        hierarchy, resolution, rankings, _ = report.tables(self.root, data)
        root = [r for r in hierarchy if r['scope'] == 'GLOBAL' and r['parent'] == 'TOTAL']
        self.assertEqual(sum(r['count'] for r in root), 4)
        self.assertEqual(sum(r['percent_parent'] for r in root), 100)
        viral = [r for r in hierarchy if r['scope'] == 'GLOBAL' and r['parent'] == 'viral']
        self.assertAlmostEqual(next(r['percent_parent'] for r in viral if r['child'] == 'viral/phage'), 200/3)
        self.assertEqual(data[3][('GLOBAL', 'phage', 'genus')], 1)
        self.assertEqual(data[3][('GLOBAL', 'viral_euk', 'family')], 1)
        self.assertNotIn('species', [r['level'] for r in resolution])
        with (self.root / 'resolucion_control_umbral.csv').open() as stream:
            self.assertNotIn('species', [r['level'] for r in csv.DictReader(stream)])
        self.assertEqual(sum(r['count'] for r in resolution if r['scope'] == 'GLOBAL' and r['class'] == 'phage'), 2)
        self.assertNotIn('Untrusted', [r['taxon'] for r in rankings if r['rank'] != 'virus_name_context'])
        self.assertEqual(data[7][('GLOBAL', 'phage', 'below_threshold')], 1)
        self.assertEqual(data[5][('GLOBAL', 'viral_euk', 'local_class_summary_reconstructed')], 1)
        self.assertEqual(data[2][('muestra:S2', 'phage')], 2)

    def test_family_is_not_inferred_from_genus_without_evidence(self):
        annotation = {'best_taxonomic_level': 'genus', 'dominant_genus': 'G', 'dominant_family': 'F', 'family_coverage': .1, 'family_purity': 1}
        self.assertEqual(report.rank_value(annotation, 'genus'), 'G')
        self.assertEqual(report.rank_value(annotation, 'family'), '')

    def test_csv_matches_jsonl(self):
        flat = [report.flatten(row) for row in self.rows]
        fields = sorted({key for row in flat for key in row})
        for row in flat:
            row['path'] = '/'.join(row['path'])
        csv_path = self.root / 'predictions.csv'
        report.write_csv(csv_path, flat, fields)
        csv_data = report.collect(csv_path, self.taxonomy, self.root / 'csv_audit.csv')
        self.assertEqual(csv_data, self.collect())

    def test_duplicate_ids_rejected(self):
        self.rows.append(self.rows[0])
        self.write_rows()
        with self.assertRaisesRegex(ValueError, 'duplicado'):
            self.collect()

    def test_all_sequences_preserve_origin_and_late_prediction_fields(self):
        for row in self.rows:
            row.update(source_relative_path='NW/sample.faa', source_folder='NW',
                       source_file='sample.faa', original_id='original_' + row['seq_id'],
                       original_header='header, with detail', source_file_sha256='checksum')
        self.rows[-1]['confidences'] = {'M6': .98}
        self.write_rows()
        data = self.collect()
        origins, complete = report.sequence_sources(self.input, self.root, '/data/proteins')
        with gzip.open(self.root / 'secuencias.csv.gz', 'rt') as stream:
            sequences = list(csv.DictReader(stream))
        self.assertEqual(len(sequences), 4)
        self.assertEqual(sequences[0]['path'], 'cellular/bacteria')
        self.assertEqual(sequences[0]['source_path'], '/data/proteins/NW/sample.faa')
        self.assertEqual(sequences[0]['original_header'], 'header, with detail')
        self.assertEqual(sequences[-1]['confidences.M6'], '0.98')
        self.assertEqual(complete, 4)
        self.assertEqual(origins[0]['cellular'], 1)
        self.assertEqual(origins[0]['viral'], 3)
        self.assertEqual(data[0][('carpeta:NW', ())], 4)
        with (self.root / 'audit.csv').open() as stream:
            audit = list(csv.DictReader(stream))
        self.assertEqual(audit[0]['original_id'], 'original_b')
        self.assertEqual(audit[0]['source_folder'], 'NW')

    def test_report_links_complete_sequence_table_and_origins(self):
        result = report.generate_report(self.input, self.root / 'output', taxonomy_path=None)
        self.assertEqual(result['proteins'], 4)
        self.assertEqual(result['proteins_with_source_and_original_id'], 0)
        document = (self.root / 'output/informe.html').read_text()
        self.assertIn('href="secuencias.csv.gz"', document)
        self.assertIn('href="origen_archivos.csv"', document)
        self.assertNotIn('dominancia_todos_', document)
        self.assertIn('Full reference distribution', document)
        self.assertIn('Cumulative % of labeled proteins', document)
        readme = (self.root / 'output/README.txt').read_text()
        self.assertIn('losslessly compressed', readme)
        self.assertLess(len(readme.splitlines()), 45)
        self.assertNotIn('**', readme)
        self.assertNotIn('href="README.md"', document)
        self.assertIn('href="README_en.txt"', document)
        self.assertIn('<html lang="en" data-theme="dark">', document)
        self.assertIn('data-el="view-categories"', document)
        self.assertIn('Classification overview', document)
        self.assertNotIn('<img', document)
        self.assertTrue((self.root / 'output/es/cascada_jerarquica.svg').is_file())
        self.assertIn('Analyzed proteins', (self.root / 'output/cascada_jerarquica.svg').read_text())
        self.assertIn('Proteínas de inferencia', (self.root / 'output/es/cascada_jerarquica.svg').read_text())
        for path in (self.root / 'output').iterdir():
            self.assertIn(path.name, readme)

    def test_interactive_ui_is_english_with_spanish_export_guides(self):
        out = self.root / 'output'
        result = report.generate_report(self.input, out, taxonomy_path=None, sequence_export='none', language='es')
        self.assertEqual(result['default_language'], 'en')
        self.assertEqual(result['report_languages'], ['en'])
        document = (out / 'informe.html').read_text()
        self.assertIn('<html lang="en"', document)
        self.assertIn('href="README_en.txt"', document)
        self.assertTrue((out / 'README.txt').read_text().startswith('INFORME VYDRA'))
        self.assertTrue((out / 'README_en.txt').read_text().startswith('VYDRA REPORT'))
        self.assertEqual(result['report_design'], 'interactive')

    def test_legacy_manifest_restores_origins_for_csv_and_jsonl(self):
        manifest = [dict(seq_id=r['seq_id'], sample_id=r['sample_id'], source_file='sample.fasta',
                         original_id='original_' + r['seq_id'], original_header='header ' + r['seq_id'],
                         original_length='50', source_sha256='checksum') for r in self.rows]
        report.write_csv(self.root / 'manifest_secuencias.csv', manifest, list(manifest[0]))
        (self.root / 'metadata_inferencia.json').write_text(json.dumps({'input_directory': '/original/input'}))
        enriched = list(report.iter_rows(self.input))
        self.assertEqual(enriched[0]['source_path'], '/original/input/sample.fasta')
        self.assertEqual(enriched[0]['source_file_sha256'], 'checksum')
        self.assertEqual(enriched[0]['source_folder'], '.')
        self.assertEqual(enriched[0]['original_id'], 'original_a')
        self.assertEqual(self.collect()[0][('carpeta:.', ())], 4)
        self.rows.pop()
        self.write_rows()
        with self.assertRaisesRegex(ValueError, 'Faltan predicciones'):
            list(report.iter_rows(self.input))

    def test_disabling_export_removes_only_generated_sequence_copies(self):
        out = self.root / 'output'
        out.mkdir()
        (out / 'secuencias.csv').write_text('old generated export')
        (out / 'dominancia_todos_phage.png').write_text('old curve')
        original = self.input.read_bytes()
        report.generate_report(self.input, out, taxonomy_path=None, sequence_export='none')
        self.assertFalse((out / 'secuencias.csv').exists())
        self.assertFalse((out / 'secuencias.csv.gz').exists())
        self.assertFalse((out / 'dominancia_todos_phage.png').exists())
        self.assertEqual(self.input.read_bytes(), original)

    def test_running_inference_rejected_before_output(self):
        (self.root / 'metadata_inferencia.json').write_text('{"status":"running"}')
        with self.assertRaisesRegex(ValueError, 'no está completa'):
            report.generate_report(self.input, self.root / 'output')
        self.assertFalse((self.root / 'output').exists())

    def test_empty_inference_rejected(self):
        self.input.write_text('')
        with self.assertRaisesRegex(ValueError, 'vacía'):
            self.collect()

    def test_similarity_threshold_boundary_and_empty_structural_class(self):
        self.rows[2].update(cluster_class='phage_non_struct', cluster_id=1)
        self.rows[3].update(cluster_class='phage_non_struct', cluster_id=2,
                            cluster_similarity=.95, cluster_similarity_threshold=.95)
        self.write_rows()
        import os
        os.environ.setdefault('MPLCONFIGDIR', '/tmp/vydra-report-matplotlib')
        import matplotlib
        matplotlib.use('Agg')
        rows = report.similarity_report(self.input, self.root)
        nonstruct = next(r for r in rows if r['class_name']=='phage_non_struct')
        self.assertEqual(nonstruct['passing'], 1)
        self.assertEqual(nonstruct['below'], 1)
        self.assertAlmostEqual(nonstruct['median_similarity'], .925)
        empty = next(r for r in rows if r['class_name']=='head-tail_joining')
        self.assertEqual(empty['proteins'], 0)
        self.assertEqual(empty['threshold_source'], 'current_config_no_comparable_predictions')
        self.assertEqual(len(rows), 11)

    def test_missing_taxonomy_does_not_fabricate_ranks(self):
        self.assertEqual(report.annotation_for({}, ('viral', 'eukaryota', '999'), self.taxonomy), ({}, 'missing'))


if __name__ == '__main__':
    unittest.main()
