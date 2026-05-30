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

First OCR run
-------------
The first OCR run may take several minutes and requires internet access because
PaddleOCR downloads its PP-OCRv5 models into your user profile. Later runs reuse
those model files.

Troubleshooting
---------------
If the app fails, check:

    Documents\nte-dice-analysis\logs\nte-dice-analysis.log

This portable build uses the CPU OCR runtime for broad Windows compatibility.
Developers can still run the project from source with a GPU Paddle runtime.
