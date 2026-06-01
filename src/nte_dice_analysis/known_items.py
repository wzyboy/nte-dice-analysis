import tomllib
from dataclasses import dataclass


@dataclass(frozen=True)
class KnownItems:
    by_pool: dict[str, tuple[str, ...]]

    @property
    def item_count(self) -> int:
        return sum(len(items) for items in self.by_pool.values())

    def __bool__(self) -> bool:
        return self.item_count > 0

    def items_for_pool(self, pool_type: str) -> tuple[str, ...]:
        return self.by_pool.get(pool_type.strip(), ())

    def contains(self, pool_type: str, item_name: str) -> bool:
        return item_name.strip() in self.items_for_pool(pool_type)


def parse_known_items_toml(content: bytes, source: str) -> KnownItems:
    try:
        data = tomllib.loads(content.decode('utf-8-sig'))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f'invalid known-items TOML at {source}: {error}') from error

    pools = data.get('pools')
    if not isinstance(pools, dict) or not pools:
        raise ValueError(f'known-items TOML at {source} must contain a non-empty [pools] table')

    by_pool: dict[str, tuple[str, ...]] = {}
    for pool_type, pool_data in pools.items():
        pool_name = pool_type.strip()
        if not pool_name:
            raise ValueError(f'known-items TOML at {source} contains an empty pool name')
        if not isinstance(pool_data, dict):
            raise ValueError(f'known-items TOML at {source} pool {pool_name} must be a table')

        items = pool_data.get('items')
        if not isinstance(items, list):
            raise ValueError(f'known-items TOML at {source} pool {pool_name} must contain an items array')

        parsed_items: list[str] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, str):
                raise ValueError(
                    f'known-items TOML at {source} pool {pool_name} item {index} must be a string',
                )
            item_name = item.strip()
            if not item_name:
                raise ValueError(
                    f'known-items TOML at {source} pool {pool_name} item {index} must not be empty',
                )
            parsed_items.append(item_name)

        by_pool[pool_name] = tuple(parsed_items)

    return KnownItems(by_pool=by_pool)
