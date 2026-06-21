import os
import tempfile
from pathlib import Path

TEST_DB_DIR = Path(tempfile.mkdtemp(prefix='gasmeter_pytest_'))
os.environ.setdefault('GASMETER_DB_DIR', str(TEST_DB_DIR))
