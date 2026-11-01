"""Process-wide resources shared by practice jobs and song breakdowns."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading

ROOT = Path(tempfile.mkdtemp(prefix='fretwork-'))
LOCK = threading.RLock()
# One audio worker: separation models are memory-heavy, so jobs and songs queue together.
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='audio')
TTL_SECONDS = 3600
