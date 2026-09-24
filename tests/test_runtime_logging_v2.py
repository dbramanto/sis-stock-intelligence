from pathlib import Path
import unittest

SRC = (Path(__file__).resolve().parents[1] / 'app_v2.py').read_text(encoding='utf-8')

class RuntimeLoggingContract(unittest.TestCase):
    def test_console_and_rotating_file_handlers_exist(self):
        self.assertIn('logging.StreamHandler(sys.stdout)', SRC)
        self.assertIn('RotatingFileHandler(_LOG_FILE', SRC)
        self.assertIn('logger.propagate = False', SRC)

    def test_pipeline_stage_markers_exist(self):
        for marker in ('[RUN] START', '[S1] START', '[S1] END', '[S2] START', '[S2] END', '[P10] START', '[P10] END', '[S3] START', '[S3] END', '[SNAPSHOT] AUTO-SAVED', '[SNAPSHOT] FINALIZED', '[RUN] COMPLETE'):
            self.assertIn(marker, SRC)

    def test_fail_closed_stops_are_logged(self):
        self.assertIn('[RUN] STOP | Stage2/Stage3 NOT EXECUTED', SRC)
        self.assertIn('[RUN] STOP | Stage3 NOT EXECUTED', SRC)
        self.assertIn('[RUN] STOP | validated snapshot retained', SRC)
        self.assertIn('_log_issues("S1", s1.get("issues", []))', SRC)

if __name__ == '__main__': unittest.main()
