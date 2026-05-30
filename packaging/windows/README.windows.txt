NTE Dice Analysis for Windows
=============================

Quick start
-----------
1. Extract the ZIP file.
2. Double-click "NTE Dice Analysis.exe".
3. Add one or more full game screenshots on the Simple tab.
4. Click "Run Analysis".

The app writes records.xlsx, records.png, cropped table images, JSON files, and
logs under your Documents\nte-dice-analysis folder by default.

CPU and CUDA builds
-------------------
The CPU ZIP works on the widest range of Windows machines.

The CUDA ZIP requires a working NVIDIA CUDA setup. If CUDA is not available, the
app stops before OCR. Install or update NVIDIA drivers/CUDA from:

    https://www.nvidia.com/en-us/drivers/

or download the CPU ZIP instead.

OCR models
----------
This portable build includes the default PP-OCRv5 mobile detection and
recognition models, so the default workflow does not need a first-run model
download.

Troubleshooting
---------------
If the app fails, check:

    Documents\nte-dice-analysis\logs\nte-dice-analysis.log
