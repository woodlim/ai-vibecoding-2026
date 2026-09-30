"""Atomic local PAPER snapshots; a failed save must not acknowledge a trade."""
from functools import wraps
from pathlib import Path
import os
import tempfile

from .models import PaperState


def save_state(path: Path, state: PaperState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(state.model_dump_json(indent=2))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def persisted(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            outer = self._state_path is not None and self._mutation_depth == 0
            before = self.snapshot() if outer else None
            self._mutation_depth += 1
            try:
                result = method(self, *args, **kwargs)
                if outer:
                    save_state(self._state_path, self.snapshot())
                return result
            except Exception:
                if before is not None:
                    self.restore(before)
                raise
            finally:
                self._mutation_depth -= 1
    return wrapped
