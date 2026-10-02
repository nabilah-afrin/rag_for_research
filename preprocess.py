import hashlib
from pathlib import Path

def remove_duplicate_files(directory):
    """Delete duplicate PDFs in directory, keeping the first of each group."""
    groups = {}
    for path in Path(directory).glob('*.pdf'):
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        groups.setdefault(digest, []).append(path)

    removed = 0
    for files in groups.values():
        for dup in files[1:]:
            print(f"Removing: {dup.name}")
            dup.unlink()
            removed += 1

    print(f"Removed {removed} duplicate files")
