import argparse
from pathlib import Path
from dataclasses import dataclass
from collections.abc import Callable

from tqdm import tqdm

from .io import load_json
from .io import load_known_items
from .io import resolve_json_paths
from .models import Record
from .console import configure_stdout
from .known_items import KnownItems

type LoadProgressCallback = Callable[[Path, int, int], None]
type MissingItemKey = tuple[str, str]


@dataclass(frozen=True)
class MissingItemReference:
    json_path: Path
    source_image: Path
    page_row: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Check NTE records JSON item names against known_items.toml.',
    )
    parser.add_argument('json_files', nargs='+', type=Path)
    parser.add_argument(
        '--known-items',
        type=Path,
        default=None,
        help='known-item dictionary TOML file; defaults to the packaged known_items.toml',
    )
    return parser.parse_args(argv)


def load_records_by_path(
    json_paths: list[Path],
    progress: LoadProgressCallback | None = None,
) -> dict[Path, list[Record]]:
    records_by_path: dict[Path, list[Record]] = {}
    for index, json_path in enumerate(json_paths, start=1):
        if progress is not None:
            progress(json_path, index, len(json_paths))
        if not json_path.exists():
            raise ValueError(f'JSON file not found: {json_path}')
        records_by_path[json_path] = load_json(json_path)
    return records_by_path


def find_missing_items(
    records_by_path: dict[Path, list[Record]],
    known_items: KnownItems,
) -> dict[MissingItemKey, list[MissingItemReference]]:
    missing_items: dict[MissingItemKey, list[MissingItemReference]] = {}
    for json_path, records in records_by_path.items():
        for record in records:
            pool_type = record.pool_type.strip()
            item_name = record.item_name.strip()
            if not item_name or known_items.contains(pool_type, item_name):
                continue

            missing_items.setdefault((pool_type, item_name), []).append(
                MissingItemReference(
                    json_path=json_path,
                    source_image=record.source_image,
                    page_row=record.page_row,
                ),
            )

    return missing_items


def format_reference(reference: MissingItemReference) -> str:
    return f'{reference.json_path} ({reference.source_image}, row {reference.page_row})'


def format_missing_item_key(pool_type: str, item_name: str) -> str:
    return f'{pool_type or "<unknown pool>"}: {item_name}'


def print_missing_items(missing_items: dict[MissingItemKey, list[MissingItemReference]]) -> None:
    print('missing known items:')
    for pool_type, item_name in sorted(missing_items, key=lambda key: (key[0].casefold(), key[1].casefold())):
        references = missing_items[(pool_type, item_name)]
        label = format_missing_item_key(pool_type, item_name)
        print(f'- {label} ({len(references)} occurrence{"s" if len(references) != 1 else ""})')
        for reference in references[:3]:
            print(f'  - {format_reference(reference)}')
        if len(references) > 3:
            print(f'  - ... {len(references) - 3} more')


def main(argv: list[str] | None = None) -> None:
    configure_stdout()
    args = parse_args(argv)
    json_paths = resolve_json_paths(args.json_files)

    try:
        with tqdm(total=len(json_paths), desc='Loading JSON', unit='file') as progress:

            def report_json_progress(json_path: Path, index: int, total: int) -> None:
                progress.set_postfix_str(json_path.name)
                progress.update(1)

            records_by_path = load_records_by_path(json_paths, progress=report_json_progress)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    try:
        known_items = load_known_items(args.known_items)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    missing_items = find_missing_items(records_by_path, known_items)
    record_count = sum(len(records) for records in records_by_path.values())

    if missing_items:
        print_missing_items(missing_items)
        raise SystemExit(1)

    print(
        f'all item names are present in known items; checked {record_count} records from {len(json_paths)} JSON files'
    )
