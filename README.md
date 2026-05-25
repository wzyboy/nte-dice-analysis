# NTE Dice Analysis

Small OCR pipeline for extracting NTE gacha/dice records from screenshots.

## Run

```powershell
uv run nte-ocr sample.png --out records.csv --json-out records.json --debug-dir debug
```

You can pass either image files or a directory of screenshots. Directories are
expanded to supported image files in sorted order:

```powershell
uv run nte-ocr debug/sample_full_screenshots --out records.csv --json-out records.json --debug-dir debug/crops
```

The script defaults to `--device auto`, which uses `gpu:0` when Paddle is built
with CUDA and a GPU is visible, otherwise CPU.

The defaults are tuned for screenshots with the same layout as `sample.png`. If the game window size or table position changes, adjust the crop:

```powershell
uv run nte-ocr sample.png --table-crop 0.1823,0.4259,0.8281,0.7870
```

`--table-crop` accepts either normalized coordinates from `0` to `1`, or pixel coordinates.
`--pool-crop` works the same way for the `棋盘类型` dropdown used to populate
the `pool_type` output column.

The `rarity` output column is detected from the item-name text color: gold is
`S-Class`, purple is `A-Class`, and gray is `B-Class`.

`known_items.txt` is used as a fuzzy correction dictionary for item names. Add new item names there as you encounter them; the script keeps the raw OCR text in `item_name_raw` for auditing.

The output is deduplicated after OCR. The merge keeps the reverse chronological
table order, aligns overlapping screenshots by pool type, timestamp, and row
content, treats single-pull timestamps as one record, and validates multi-pull
timestamps as 10 rolls plus one `集点赠礼`. Use `--no-dedup` if you need to
inspect every raw OCR row.
