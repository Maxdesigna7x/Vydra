import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Vydra_Docker_HF'))
from interactive_report import write_interactive_report

class InteractiveReportTests(unittest.TestCase):
    def test_current_data_safe_embedding_and_distinct_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'input.jsonl'
            rows=[dict(seq_id='a</script><script>alert(1)</script>',original_id='original',source_relative_path='A/sample.faa',source_folder='A',length=30,path=['cellular','bacteria']),dict(seq_id='b',source_relative_path='B/sample.faa',source_folder='B',length=40,path=['viral','phage','non_structural'],cluster_similarity=.95,cluster_similarity_threshold=.95,cluster_annotation=dict(best_taxonomic_level='genus',dominant_genus='Example',dominant_family='Unsupported',family_coverage=.1,family_purity=1))]
            source.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            document=write_interactive_report(source,root,{}).read_text()
            data=json.loads(re.search(r'<script type="application/json" data-el="data">(.*?)</script>',document,re.S)[1])
            self.assertEqual(len(data),2);self.assertEqual(data[0]['id'],rows[0]['seq_id'])
            self.assertNotIn('a</script>',document);self.assertNotIn('Preview with 293',document)
            self.assertEqual([r['file'] for r in data],['A/sample.faa','B/sample.faa'])
            self.assertEqual(data[1]['status'],'supera');self.assertEqual(data[1]['genus'],'Example');self.assertEqual(data[1]['family'],'')
            self.assertIn('view-categories',document);self.assertIn('2 proteins',document)

if __name__=='__main__':unittest.main()
