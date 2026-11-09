"""Bounded, read-only browsing; recursion never follows linked folders."""

import os
from pathlib import Path

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MAX_IMAGES = 5000
MAX_ENTRIES = 50000
MAX_DIRECTORIES = 2048


def scan(folder, *, recursive=False, cancelled=lambda: False):
    root = Path(folder).absolute()
    images, pending, visited = [], [root], []
    entries = directories = 0
    limited = False
    while pending and not cancelled():
        current = pending.pop()
        directories += 1
        if directories > MAX_DIRECTORIES:
            limited = True
            break
        # A missing/unmounted root must be an error, not an empty replacement.
        try:
            with os.scandir(current) as listing:
                visited.append(str(current))
                for item in listing:
                    if cancelled():
                        break
                    entries += 1
                    if entries > MAX_ENTRIES or len(images) >= MAX_IMAGES:
                        limited = True
                        break
                    if item.name.startswith("."):
                        continue
                    if recursive and item.is_dir(follow_symlinks=False):
                        pending.append(Path(item.path))
                    elif Path(item.name).suffix.lower() in EXTENSIONS and item.is_file() and os.access(item.path, os.R_OK):
                        path = str(Path(item.path))
                        images.append({"fileName": item.name, "filePath": path,
                                       "relativePath": str(Path(path).relative_to(root)),
                                       "fileUrl": Path(path).as_uri()})
        except OSError:
            if current == root:
                raise
            # Report incomplete recursion, while retaining readable branches.
            limited = True
        if entries > MAX_ENTRIES or len(images) >= MAX_IMAGES:
            break
    images.sort(key=lambda image: (image["relativePath"].casefold(), image["relativePath"]))
    return {"path": str(root), "images": images, "total": len(images),
            "recursive": recursive, "limited": limited, "directories": visited}


def filtered(images, query):
    terms = query.casefold().split()
    return [image for image in images
            if all(term in image.get("relativePath", image["fileName"]).casefold() for term in terms)]
