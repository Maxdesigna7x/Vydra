import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vydra_core'))
from folder_inputs import resolve_model_path, model_is_complete
from huggingface_hub.errors import LocalEntryNotFoundError

class ModelLoadingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        (self.path/'config.json').write_text('{}');(self.path/'spiece.model').write_bytes(b'tokenizer');(self.path/'model.safetensors').write_bytes(b'weights')
        self.env=patch.dict(os.environ,{},clear=False);self.env.start();os.environ.pop('VYDRA_PROSTT5_PATH',None)
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def test_explicit_local_model_never_downloads(self):
        with patch('huggingface_hub.snapshot_download') as download:
            self.assertEqual(resolve_model_path(self.path,False),self.path)
            download.assert_not_called()
    def test_cache_is_used_with_or_without_permission(self):
        with patch('huggingface_hub.snapshot_download',return_value=str(self.path)) as download:
            for offline in [False,True]:self.assertEqual(resolve_model_path(None,offline),self.path)
            self.assertTrue(all(call.kwargs['local_files_only'] for call in download.call_args_list))
    def test_offline_missing_model_does_not_download(self):
        with patch('huggingface_hub.snapshot_download',side_effect=LocalEntryNotFoundError('missing')) as download:
            with self.assertRaisesRegex(FileNotFoundError,'No complete local'):resolve_model_path(None,True)
            self.assertEqual(download.call_count,1);self.assertTrue(download.call_args.kwargs['local_files_only'])
    def test_allowed_download_occurs_only_after_cache_miss(self):
        with patch('huggingface_hub.snapshot_download',side_effect=[LocalEntryNotFoundError('missing'),str(self.path)]) as download:
            self.assertEqual(resolve_model_path(None,False),self.path)
            self.assertTrue(download.call_args_list[0].kwargs['local_files_only'])
            self.assertNotIn('local_files_only',download.call_args_list[1].kwargs)
    def test_incomplete_shards_rejected(self):
        (self.path/'model.safetensors.index.json').write_text('{"weight_map":{"layer":"missing.safetensors"}}')
        self.assertFalse(model_is_complete(self.path))
        with self.assertRaisesRegex(FileNotFoundError,'incomplete'):resolve_model_path(self.path,False)

if __name__=='__main__':unittest.main()
