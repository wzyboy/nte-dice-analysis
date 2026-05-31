import json
from pathlib import Path
from importlib import resources

from .models import Record
from .constants import IMAGE_EXTENSIONS

KNOWN_ITEMS_RESOURCE = 'known_items.txt'


def resolve_file_paths(paths: list[Path], extensions: set[str]) -> list[Path]:
    file_paths: list[Path] = []
    for path in paths:
        if path.is_dir():
            file_paths.extend(
                child for child in path.iterdir() if child.is_file() and child.suffix.lower() in extensions
            )
        else:
            file_paths.append(path)

    return sorted(file_paths, key=lambda path: str(path).casefold())


def resolve_image_paths(paths: list[Path]) -> list[Path]:
    return resolve_file_paths(paths, IMAGE_EXTENSIONS)


def resolve_json_paths(paths: list[Path]) -> list[Path]:
    return resolve_file_paths(paths, {'.json'})


def resolve_cropped_table_paths(paths: list[Path]) -> list[Path]:
    image_paths: list[Path] = []
    for path in paths:
        if path.is_dir():
            image_paths.extend(
                child
                for child in path.iterdir()
                if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS and '.table.' in child.stem
            )
        else:
            image_paths.append(path)

    return sorted(image_paths, key=lambda path: str(path).casefold())


def write_json(path: Path, records: list[Record]) -> None:
    with path.open('w', encoding='utf-8') as file:
        json.dump([record.to_output_row() for record in records], file, ensure_ascii=False, indent=2)
        file.write('\n')


def load_json(path: Path) -> list[Record]:
    if not path.exists():
        return []

    try:
        rows = json.loads(path.read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError as error:
        raise ValueError(f'invalid records JSON at {path}: {error}') from error

    if not isinstance(rows, list):
        raise ValueError(f'records JSON at {path} must contain a list of objects')

    records: list[Record] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f'records JSON at {path} row {index} must be an object')

        record_row: dict[str, str] = {}
        for key, value in row.items():
            if not isinstance(key, str):
                raise ValueError(f'records JSON at {path} row {index} must have string keys')
            record_row[key] = str(value) if value is not None else ''
        records.append(Record.from_output_row(record_row))

    return records


def load_known_items(path: Path | None = None) -> list[str]:
    if path is None:
        text = resources.files(__package__).joinpath(KNOWN_ITEMS_RESOURCE).read_text(encoding='utf-8-sig')
    else:
        text = path.read_text(encoding='utf-8-sig')

    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
