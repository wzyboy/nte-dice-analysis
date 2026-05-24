# NTE Dice Analysis

Small OCR pipeline for extracting NTE gacha/dice records from screenshots.

## Setup

This project reuses the PaddleOCR dependency set from `C:\Users\wzyboy\git\paddle`.

```powershell
uv sync --locked
```

PaddleOCR will use cached models from:

```text
C:\Users\wzyboy\.paddlex\official_models
```

## Run

```powershell
uv run nte-ocr sample.png --out records.csv --json-out records.json --debug-dir debug
```

The defaults are tuned for screenshots with the same layout as `sample.png`. If the game window size or table position changes, adjust the crop:

```powershell
uv run nte-ocr sample.png --table-crop 0.1823,0.4259,0.8281,0.7870
```

`--table-crop` accepts either normalized coordinates from `0` to `1`, or pixel coordinates.

`known_items.txt` is used as a fuzzy correction dictionary for item names. Add new item names there as you encounter them; the script keeps the raw OCR text in `item_name_raw` for auditing.
