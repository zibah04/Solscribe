"""Small durable file operations; no Qt or application-state dependencies."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile


@contextmanager
def atomic_destination(destination: Path):
    destination = Path(destination)
    handle, name = tempfile.mkstemp(prefix='.solscribe-', suffix=destination.suffix,
                                  dir=destination.parent)
    os.close(handle)
    temporary = Path(name)
    try:
        yield temporary
        # Windows _commit (used by os.fsync) requires a writable descriptor.
        with temporary.open('r+b') as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(destination: Path, value) -> None:
    with atomic_destination(destination) as temporary:
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def contained_file(path: Path, root: Path) -> bool:
    path, root = Path(path).resolve(), Path(root).resolve()
    return path != root and path.is_relative_to(root)
