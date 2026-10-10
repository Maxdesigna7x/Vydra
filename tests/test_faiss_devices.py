import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vydra_core'))
import gpu_faiss as backend

class DeviceTests(unittest.TestCase):
    def test_cpu_never_initializes_cuda_and_search_matches_numpy(self):
        vectors = np.array([[1, 0], [0, 1], [-1, 0]], dtype=np.float32)
        queries = np.array([[.8, .2], [.1, .9]], dtype=np.float32)
        with patch.object(backend, 'require_gpu', side_effect=AssertionError('CUDA called')):
            self.assertEqual(backend.select_device('cpu').type, 'cpu')
            index = backend.build_index(vectors, device='cpu')
            scores, ids = backend.search_index(index, queries, 2)
        expected = queries @ vectors.T
        order = np.argsort(-expected, axis=1)[:, :2]
        np.testing.assert_array_equal(ids, order)
        np.testing.assert_allclose(scores, np.take_along_axis(expected, order, axis=1))

    def test_auto_without_cuda_uses_cpu(self):
        with patch.object(torch.cuda, 'is_available', return_value=False):
            self.assertEqual(backend.select_device('auto').type, 'cpu')
            with self.assertRaises(RuntimeError):
                backend.select_device('cuda')

    def test_auto_with_cpu_only_faiss_uses_cpu(self):
        with patch.object(backend.faiss, 'StandardGpuResources', None, create=True):
            self.assertEqual(backend.select_device('auto').type, 'cpu')
            with self.assertRaises(RuntimeError):
                backend.select_device('cuda')

    def test_gpu_cpu_search_parity(self):
        try:
            backend.require_gpu()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        rng = np.random.default_rng(42)
        vectors = rng.normal(size=(200, 32)).astype(np.float32)
        queries = rng.normal(size=(11, 32)).astype(np.float32)
        cpu = backend.search_index(backend.build_index(vectors, device='cpu'), queries, 5)
        gpu = backend.search_index(backend.build_index(vectors, device='cuda'), queries, 5)
        np.testing.assert_array_equal(cpu[1], gpu[1])
        np.testing.assert_allclose(cpu[0], gpu[0], atol=1e-5, rtol=1e-5)

if __name__ == '__main__':
    unittest.main()
