NTE Dice Analysis for Windows
=============================

Quick start
-----------
1. Extract the ZIP file.
2. Double-click "NTE Dice Analysis.exe".
3. Add one or more full game screenshots on the "简单" tab.
4. Click "开始分析".

Game capture
------------
Use "获取游戏截图" to capture the foreground game window with F9 and finish with
F10. If the game is running as administrator, Windows will show a UAC prompt
when capture starts so the helper can capture that elevated window.

The app writes records.xlsx, records.png, cropped table images, JSON files, and
logs under your Documents\nte-dice-analysis folder by default.

OCR
---
This build uses CPU OCR and works on the widest range of Windows machines.

OCR models
----------
This portable build includes the default PP-OCRv5 mobile detection and
recognition models, so the default workflow does not need a first-run model
download.

Troubleshooting
---------------
If the app fails, check:

    Documents\nte-dice-analysis\logs\nte-dice-analysis.log
