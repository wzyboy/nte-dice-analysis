# NTE Dice Analysis 异环抽卡记录分析

<p align="center">
  <img src="src/nte_dice_analysis/assets/app_icon.png" alt="NTE Dice Analysis app icon" width="128" height="128">
</p>

本地识别并分析《异环》的抽卡记录截图，并可导出 PNG 图片和 XLSX 表格。

目前只支持简体中文版本的游戏截图。

程序界面（由 [@uucky](https://github.com/uucky) 设计）：

![ui screenshot](./screenshots/ui.png)

图片输出示例（设计参考了 [StarRailWarpExport](https://github.com/biuuu/star-rail-warp-export)）：

![png output](./screenshots/output-summary.png)

表格输出示例：

![spreadsheet output](./screenshots/output-spreadsheet.png)

## Windows 快速使用

1. 打开 [Releases](https://github.com/wzyboy/nte-dice-analysis/releases) 页面。
1. 下载 `NTE-Dice-Analysis-windows-x64-vX.Y.Z.zip` 并解压。
1. 双击运行 `NTE Dice Analysis.exe`。
1. 在主界面点击 `添加文件` 或 `添加文件夹`，选择完整的游戏内抽卡界面的截图。
1. 点击 `分析`。

分析数据和结果会保存到「文档」目录下的 `nte-dice-analysis` 文件夹。再次打开程序时，只需要添加新增的截图即可，程序会自动校验、去重，并显示新旧数据合并后的分析结果。

常见文件：

- `records.xlsx`：Excel 表格
- `records.png`：汇总图片
- 裁剪后的表格图片和 JSON 文件：用于下次复用，也方便排查 OCR 问题
- `logs` 文件夹：运行日志

## 使用提示

- 请在主界面添加完整游戏截图（16∶9），不需要自己提前裁剪。
- OCR 使用 CPU，截图多的时候需要等一会儿。
- Windows 便携版已经内置默认 OCR 模型，正常情况下首次运行也不需要下载模型。
- 在 `高级模式` 中，用户可以对裁剪、识别、导出的每一步进行微调。

## 命令行 / Linux 使用

从源码运行：

```bash
uv run nte-gui
```

也可以分别运行裁剪、识别和导出命令：

```bash
uv run nte-crop --help
uv run nte-recognize --help
uv run nte-export-xlsx --help
uv run nte-export-png --help
```

## 开发

运行测试：

```bash
uv run pytest
```

构建 Windows 便携版 ZIP：

```powershell
.\scripts\build_windows.ps1
```

`src/nte_dice_analysis/known_items.toml` 用于修正 OCR 中可能出现的物品名错误，卡池更新后可能也需要更新。
