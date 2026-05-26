# NTE Dice Analysis

Small OCR pipeline for extracting NTE gacha/dice records from screenshots.

## Run

```bash
uv run nte-ocr sample.png --json-out records.json --xlsx-out records.xlsx --debug-dir debug
```

By default this writes raw JSON plus a user-friendly workbook:

```text
records.json
records.xlsx
```

`records.json` is also the incremental state file. If it already exists, the
script loads those records, merges in records from the screenshots passed on
this run, deduplicates the combined list, and regenerates both outputs. Use
`--overwrite` to ignore an existing `records.json` and start a fresh export.

You can pass either image files or a directory of screenshots. Directories are
expanded to supported image files in sorted order:

```bash
uv run nte-ocr debug/sample_full_screenshots --json-out records.json --xlsx-out records.xlsx --debug-dir debug/crops
```

The script defaults to `--device auto`, which uses `gpu:0` when Paddle is built
with CUDA and a GPU is visible, otherwise CPU.
PaddleX resolves and downloads the default PP-OCRv5 server detection and
recognition models automatically. Use `--det-model-dir` or `--rec-model-dir`
only when pointing at an existing local model directory.

The defaults are tuned for screenshots with the same layout as `sample.png`. If the game window size or table position changes, adjust the crop:

```bash
uv run nte-ocr sample.png --table-crop 0.1823,0.4259,0.8281,0.7870
```

`--table-crop` accepts either normalized coordinates from `0` to `1`, or pixel coordinates.
`--pool-crop` works the same way for the `棋盘类型` dropdown used to populate
the `pool_type` output column.

The `rarity` output column is detected from the item-name text color: gold is
`S-Class`, purple is `A-Class`, and gray is `B-Class`.

The XLSX workbook has one sheet per `pool_type`, splits item type and item name
into separate columns, adds `rarity` and `保底内`, and colors rows by rarity.

The wheel includes a default `known_items.txt` fuzzy correction dictionary for
item names. Use `--known-items path/to/known_items.txt` to override it; the
script keeps the raw OCR text in `item_name_raw` for auditing.

The output is deduplicated after OCR. The merge keeps the reverse chronological
table order, aligns overlapping screenshots by pool type, timestamp, and row
content, treats single-pull timestamps as one record, and validates multi-pull
timestamps as 10 rolls plus one `集点赠礼`. Use `--no-dedup` if you need to
inspect every raw OCR row.

## Development

Run the unit tests with the dev dependency group:

```bash
uv run --group dev pytest
```
