import json
from pathlib import Path
from importlib import resources

from .models import Record
from .constants import IMAGE_EXTENSIONS

KNOWN_ITEMS_RESOURCE = 'known_items.txt'


def resolve_image_paths(paths: list[Path]) -> list[Path]:
    image_paths: list[Path] = []
    for path in paths:
        if path.is_dir():
            image_paths.extend(
                child for child in path.iterdir() if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS
            )
        else:
            image_paths.append(path)

    return sorted(image_paths, key=lambda path: str(path).casefold())


def write_json(path: Path, records: list[Record]) -> None:
    with path.open('w', encoding='utf-8') as file:
        json.dump([record.to_output_row() for record in records], file, ensure_ascii=False, indent=2)
        file.write('\n')


def load_known_items(path: Path | None = None) -> list[str]:
    if path is None:
        try:
            text = resources.files(__package__).joinpath(KNOWN_ITEMS_RESOURCE).read_text(encoding='utf-8-sig')
        except FileNotFoundError:
            return []
    else:
        if not path.exists():
            return []
        text = path.read_text(encoding='utf-8-sig')

    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
