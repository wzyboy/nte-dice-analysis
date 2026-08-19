import tomllib
from dataclasses import field
from dataclasses import dataclass


@dataclass(frozen=True)
class KnownItems:
    by_pool: dict[str, tuple[str, ...]]
    limited_s_by_pool: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def item_count(self) -> int:
        return sum(len(items) for items in self.by_pool.values())

    def __bool__(self) -> bool:
        return self.item_count > 0

    def items_for_pool(self, pool_type: str) -> tuple[str, ...]:
        return self.by_pool.get(pool_type.strip(), ())

    def contains(self, pool_type: str, item_name: str) -> bool:
        return item_name.strip() in self.items_for_pool(pool_type)

    def limited_s_items_for_pool(self, pool_type: str) -> tuple[str, ...]:
        return self.limited_s_by_pool.get(pool_type.strip(), ())

    def is_limited_s_item(self, pool_type: str, item_name: str) -> bool:
        return item_name.strip() in self.limited_s_items_for_pool(pool_type)


def parse_known_items_toml(content: bytes, source: str) -> KnownItems:
    try:
        data = tomllib.loads(content.decode('utf-8-sig'))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f'invalid known-items TOML at {source}: {error}') from error

    pools = data.get('pools')
    if not isinstance(pools, dict) or not pools:
        raise ValueError(f'known-items TOML at {source} must contain a non-empty [pools] table')

    by_pool: dict[str, tuple[str, ...]] = {}
    limited_s_by_pool: dict[str, tuple[str, ...]] = {}
    for pool_type, pool_data in pools.items():
        pool_name = pool_type.strip()
        if not pool_name:
            raise ValueError(f'known-items TOML at {source} contains an empty pool name')
        if not isinstance(pool_data, dict):
            raise ValueError(f'known-items TOML at {source} pool {pool_name} must be a table')

        parsed_items = parse_item_array(pool_data.get('items'), source, pool_name, 'items', required=True)
        limited_s_items = parse_item_array(
            pool_data.get('limited_s_items'),
            source,
            pool_name,
            'limited_s_items',
            required=False,
        )

        by_pool[pool_name] = (*parsed_items, *limited_s_items)
        limited_s_by_pool[pool_name] = limited_s_items

    return KnownItems(by_pool=by_pool, limited_s_by_pool=limited_s_by_pool)


def parse_item_array(
    value: object,
    source: str,
    pool_name: str,
    field_name: str,
    *,
    required: bool,
) -> tuple[str, ...]:
    if value is None and not required:
        return ()
    if not isinstance(value, list):
        requirement = 'must contain' if required else 'must use'
        raise ValueError(
            f'known-items TOML at {source} pool {pool_name} {requirement} a {field_name} array',
        )

    parsed_items: list[str] = []
    item_label = 'item' if field_name == 'items' else f'{field_name} item'
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str):
            raise ValueError(
                f'known-items TOML at {source} pool {pool_name} {item_label} {index} must be a string',
            )
        item_name = item.strip()
        if not item_name:
            raise ValueError(
                f'known-items TOML at {source} pool {pool_name} {item_label} {index} must not be empty',
            )
        parsed_items.append(item_name)
    return tuple(parsed_items)
