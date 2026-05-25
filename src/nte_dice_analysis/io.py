from __future__ import annotations

import csv
import json
from pathlib import Path

from .constants import CSV_FIELDS, IMAGE_EXTENSIONS


def resolve_image_paths(paths: list[Path]) -> list[Path]:
    image_paths: list[Path] = []
    for path in paths:
        if path.is_dir():
            image_paths.extend(
                child
                for child in path.iterdir()
                if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS
            )
        else:
            image_paths.append(path)

    return sorted(image_paths, key=lambda path: str(path).casefold())


def write_csv(path: Path, records: list[dict[str, str]]) -> None:
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)


def write_json(path: Path, records: list[dict[str, str]]) -> None:
    with path.open('w', encoding='utf-8') as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
        file.write('\n')


def load_known_items(path: Path) -> list[str]:
    if not path.exists():
        return []

    return [
        line.strip()
        for line in path.read_text(encoding='utf-8-sig').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ]
