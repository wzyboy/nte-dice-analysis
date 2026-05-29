# NTE Dice Analysis

Small OCR pipeline for extracting NTE gacha/dice records from screenshots.

## Run

The pipeline is intentionally split into separate steps so OCR and export bugs
can be debugged from intermediate files.

Crop full screenshots into table images:

```bash
uv run nte-crop 2026-05-25_21-06-03_NTE.png
```

By default this writes a cropped table image beside the source screenshot. The
pool type is detected from the fixed dropdown crop and included in the filename:

```text
2026-05-25_21-06-03_NTE.table.标准棋盘.png
```

Recognize cropped table images into per-image JSON files:

```bash
uv run nte-recognize 2026-05-25_21-06-03_NTE.table.标准棋盘.png --debug-dir debug
```

By default this writes:

```text
2026-05-25_21-06-03_NTE.table.标准棋盘.json
```

Export recognized JSON files into a deduplicated workbook:

```bash
uv run nte-export-xlsx *.table.*.json --xlsx-out records.xlsx
```

Export a deduplicated PNG summary:

```bash
uv run nte-export-png *.table.*.json --png-out records.png
```

Check whether recognized JSON files contain item names missing from
`known_items.txt`:

```bash
uv run nte-check-known-items *.table.*.json
```

You can pass either files or directories. Directories are expanded in sorted
order. `nte-crop` expands supported image files; `nte-recognize` expands cropped
table images with `.table.` in the name; `nte-export-xlsx`, `nte-export-png`, and
`nte-check-known-items` expand JSON files.
`nte-crop` and `nte-recognize` skip existing deterministic outputs by default;
pass `--overwrite` to regenerate them.

The OCR commands default to `--device auto`, which uses `gpu:0` when Paddle is
built with CUDA and a GPU is visible, otherwise CPU. PaddleX resolves and
downloads the default PP-OCRv5 server detection and recognition models
automatically. Use `--det-model-dir` or `--rec-model-dir` only when pointing at
an existing local model directory.

The crop defaults are tuned for screenshots with the same layout as
`sample.png`. If the game window size or table position changes, adjust the
crop:

```bash
uv run nte-crop sample.png --table-crop 0.1823,0.4259,0.8281,0.7870
```

`--table-crop` accepts either normalized coordinates from `0` to `1`, or pixel coordinates.
`--pool-crop` works the same way for the `棋盘类型` dropdown used to populate
the pool type in cropped filenames.

The `rarity` output column is detected from the item-name text color: gold is
`S-Class`, purple is `A-Class`, and gray is `B-Class`.

The XLSX workbook has one sheet per `pool_type`, shows records oldest-first,
splits item type and item name into separate columns, adds `rarity`, `保底内`,
and `总抽数`, and colors rows by rarity.

The PNG summary has one panel per `pool_type`, with a rarity pie chart, total
pull count, current pulls since the latest S-Class character, S-Class character
history, and average pulls per S-Class character.

The wheel includes a default `known_items.txt` fuzzy correction dictionary for
item names. Use `--known-items path/to/known_items.txt` to override it; the
script keeps the raw OCR text in `item_name_raw` for auditing.

`nte-recognize` does not deduplicate. `nte-export-xlsx` and `nte-export-png`
deduplicate after loading all JSON files. The merge keeps the reverse
chronological table order, aligns overlapping screenshots by pool type,
timestamp, and row content, treats single-pull timestamps as one record or one
record plus `集点赠礼`, and requires multi-pull timestamps to have 10 rolls plus
one `集点赠礼`. Missing timestamps or invalid pull groups stop the export so the
source crop/OCR can be investigated.
Use `--no-dedup` if you need to inspect every raw OCR row and the raw rows still
satisfy those timestamp rules.

## Development

Run the unit tests with the dev dependency group:

```bash
uv run --group dev pytest
```
