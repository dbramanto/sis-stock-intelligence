import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from stage1.history import _find_sis_root, _default_history_root, save_validated_snapshot, list_snapshots

class PersistentSnapshotRootTests(unittest.TestCase):
    def test_sis_ancestor_is_storage_anchor(self):
        p=Path('/tmp/SIS/SIS_NEW/build/stage1/history.py')
        self.assertEqual(_find_sis_root(p), Path('/tmp/SIS'))

    def test_env_override_persists_across_builds(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {'SIS_DATA_DIR': td}):
                self.assertEqual(_default_history_root(), Path(td)/'input_history')
                raw={i:'raw'+str(i) for i in range(1,12)}
                canonical=[{'symbol':'AAA'}]
                snap=save_validated_snapshot(raw, canonical, 'PASS', metadata={'expected_total':1,'filter_fingerprint':'X'})
                self.assertTrue((Path(td)/'input_history'/(snap['snapshot_id']+'.json')).exists())
                self.assertEqual(list_snapshots(validated_only=True)[0]['snapshot_id'], snap['snapshot_id'])

if __name__=='__main__': unittest.main()
