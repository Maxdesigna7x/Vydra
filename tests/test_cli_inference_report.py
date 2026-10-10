import csv
import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vydra_cli', ROOT / 'Vydra_Docker_HF/vydra_cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class CliReportTests(unittest.TestCase):
    def test_saved_prediction_generates_report_and_preserves_duplicate_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fasta = root / 'proteins.faa'
            fasta.write_text('>same first protein\nMEK\n>same second protein\nMEL\n')
            output = root / 'predictions.csv'
            records = [SimpleNamespace(seq_id='same', original_length=3, chunked=False)] * 2
            engine = SimpleNamespace(
                require_faiss_gpu=lambda: None, device='fake',
                parse_fasta_text=lambda text: records,
                embed_records=lambda records, **kwargs: [0, 0],
                run_hierarchy=lambda embedding: {'path': ['cellular', 'bacteria'], 'confidences': {'M1': .9}},
            )
            with patch.object(cli, 'import_engine', return_value=engine):
                status = cli.main(['predict', '--fasta', str(fasta), '--format', 'csv', '--output', str(output)])
            self.assertEqual(status, 0)
            report_dir = root / 'informe_inferencia_predictions'
            self.assertTrue((report_dir / 'informe.html').is_file())
            with gzip.open(report_dir / 'secuencias.csv.gz', 'rt') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len({r['seq_id'] for r in rows}), 2)
            self.assertEqual([r['original_id'] for r in rows], ['same', 'same'])
            self.assertEqual(rows[1]['original_header'], 'same second protein')
            self.assertEqual(rows[0]['source_path'], str(fasta))
            self.assertEqual(rows[0]['source_folder'], str(root))
            self.assertEqual(rows[0]['source_file_sha256'], cli.sha256_file(fasta))
            self.assertEqual(json.loads((report_dir / 'procedencia.json').read_text())['proteins'], 2)
            self.assertIn('predictions.csv', (root / 'README_ARCHIVOS.txt').read_text())

    def test_no_report_option_for_internal_folder_inference(self):
        args = cli.build_parser().parse_args(['predict', '--seq', 'MEK', '--no-report'])
        self.assertFalse(args.report)
        self.assertEqual(args.language, 'en')

    def test_language_option_and_help(self):
        args = cli.build_parser('es').parse_args(['predict', '--seq', 'MEK', '--language', 'es'])
        self.assertEqual(args.language, 'es')
        self.assertIn('Local hierarchical protein classifier', cli.build_parser().format_help())
        self.assertIn('Clasificador jerarquico', cli.build_parser('es').format_help())


if __name__ == '__main__':
    unittest.main()
