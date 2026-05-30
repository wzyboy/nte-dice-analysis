import argparse
from pathlib import Path
from dataclasses import dataclass

from .io import load_json
from .io import load_known_items
from .io import resolve_json_paths
from .models import Record
from .console import configure_stdout


@dataclass(frozen=True)
class MissingItemReference:
    json_path: Path
    source_image: Path
    page_row: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Check NTE records JSON item names against known_items.txt.',
    )
    parser.add_argument('json_files', nargs='+', type=Path)
    parser.add_argument(
        '--known-items',
        type=Path,
        default=None,
        help='known-item dictionary file; defaults to the packaged known_items.txt',
    )
    return parser.parse_args(argv)


def load_records_by_path(json_paths: list[Path]) -> dict[Path, list[Record]]:
    records_by_path: dict[Path, list[Record]] = {}
    for json_path in json_paths:
        if not json_path.exists():
            raise ValueError(f'JSON file not found: {json_path}')
        records_by_path[json_path] = load_json(json_path)
    return records_by_path


def find_missing_items(
    records_by_path: dict[Path, list[Record]],
    known_items: list[str],
) -> dict[str, list[MissingItemReference]]:
    known_item_set = set(known_items)
    missing_items: dict[str, list[MissingItemReference]] = {}
    for json_path, records in records_by_path.items():
        for record in records:
            item_name = record.item_name.strip()
            if not item_name or item_name in known_item_set:
                continue

            missing_items.setdefault(item_name, []).append(
                MissingItemReference(
                    json_path=json_path,
                    source_image=record.source_image,
                    page_row=record.page_row,
                ),
            )

    return missing_items


def format_reference(reference: MissingItemReference) -> str:
    return f'{reference.json_path} ({reference.source_image}, row {reference.page_row})'


def print_missing_items(missing_items: dict[str, list[MissingItemReference]]) -> None:
    print('missing known items:')
    for item_name in sorted(missing_items, key=str.casefold):
        references = missing_items[item_name]
        print(f'- {item_name} ({len(references)} occurrence{"s" if len(references) != 1 else ""})')
        for reference in references[:3]:
            print(f'  - {format_reference(reference)}')
        if len(references) > 3:
            print(f'  - ... {len(references) - 3} more')


def main(argv: list[str] | None = None) -> None:
    configure_stdout()
    args = parse_args(argv)
    json_paths = resolve_json_paths(args.json_files)

    try:
        records_by_path = load_records_by_path(json_paths)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    known_items = load_known_items(args.known_items)
    missing_items = find_missing_items(records_by_path, known_items)
    record_count = sum(len(records) for records in records_by_path.values())

    if missing_items:
        print_missing_items(missing_items)
        raise SystemExit(1)

    print(
        f'all item names are present in known items; checked {record_count} records from {len(json_paths)} JSON files'
    )
