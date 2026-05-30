# NTE Dice Analysis 异环抽卡记录分析

语言：中文 | [English](./README.en.md)

使用 OCR 将异环抽卡记录截图解析成 JSON，然后生成 XLSX 和 PNG 报告。

示例输出：

![screenshot](./example.png)

UI 仿自 [StarRailWarpExport](https://github.com/biuuu/star-rail-warp-export) 项目。

代码大部分是 Codex 写的。

目前只能处理简体中文版本的游戏截图。

## 使用

### 图形界面

Windows 用户可以从 release 下载便携版 ZIP，解压后双击 `NTE Dice Analysis.exe`。不需要安装 Python 或 uv。
release 会提供一个 Windows 便携版 ZIP：

- `NTE-Dice-Analysis-windows-x64-vX.Y.Z.zip` 使用 CPU OCR，适合大多数 Windows 机器。

便携版 ZIP 会内置默认的 PP-OCRv5 mobile 检测和识别模型，所以默认流程不需要首次运行时下载模型。运行日志会写入用户文档目录下的
`nte-dice-analysis/logs` 文件夹。

从源码运行：

```bash
uv run nte-gui
```

OCR 始终使用 CPU。

第一个标签页是简单模式：添加完整截图，然后运行分析，
直接生成 `records.xlsx` 和 `records.png`。GUI 默认使用用户文档目录下的 `nte-dice-analysis` 文件夹，
也可以按需选择其他输出目录。裁剪后的表格图片和 JSON 文件会保留在输出目录中，后续再次生成时可复用。
需要调试 OCR 或导出问题时，可以使用高级标签页中的裁剪、识别和导出流程。

### 命令行

这套流水线有意拆分为多个独立步骤，便于通过中间文件调试 OCR 和导出问题。

将完整截图裁剪为表格图片：

```bash
uv run nte-crop 2026-05-25_21-06-03_NTE.png
```

默认情况下，这会在源截图旁写入一张裁剪后的表格图片。池类型会从固定的下拉框裁剪区域中识别，并包含在文件名中：

```text
2026-05-25_21-06-03_NTE.table.标准棋盘.png
```

将裁剪后的表格图片识别为每张图片对应的 JSON 文件：

```bash
uv run nte-recognize 2026-05-25_21-06-03_NTE.table.标准棋盘.png
```

默认情况下，这会写入：

```text
2026-05-25_21-06-03_NTE.table.标准棋盘.json
```

将识别出的 JSON 文件导出为去重后的 XLSX 工作簿：

```bash
uv run nte-export-xlsx *.table.*.json --xlsx-out records.xlsx
```

也可以导出 PNG 汇总图：

```bash
uv run nte-export-png *.table.*.json --png-out records.png
```

你可以传入文件或目录。目录会按排序后的顺序展开。`nte-crop` 会展开受支持的图片文件；`nte-recognize` 会展开文件名中带有 `.table.` 的裁剪表格图片；`nte-export-xlsx`、`nte-export-png` 和 `nte-check-known-items` 会展开 JSON 文件。`nte-crop` 和 `nte-recognize` 默认会跳过已存在的确定性输出；传入 `--overwrite` 可重新生成。

OCR 始终使用 CPU。默认模型是 PP-OCRv5 mobile 检测和识别模型；便携版 ZIP 会内置这些模型，源码运行时由 PaddleX 自动解析或下载。仅在指向已存在的本地模型目录时才使用 `--det-model-dir` 或 `--rec-model-dir`。

默认裁剪参数针对 3840x2160 的 Windows 游戏客户端截图进行了调校。如果游戏窗口大小或表格位置发生变化，请调整裁剪区域：

```bash
uv run nte-crop sample.png --table-crop 0.1823,0.4259,0.8281,0.7870
```

`--table-crop` 既接受 `0` 到 `1` 的归一化坐标，也接受像素坐标。`--pool-crop` 的工作方式相同，用于裁剪 `棋盘类型` 下拉框，并将其结果填入裁剪文件名中的池类型。

`rarity` 输出列根据物品名称的文本颜色检测：金色为 `S-Class`，紫色为 `A-Class`，灰色为 `B-Class`。

XLSX 工作簿会为每个 `pool_type` 创建一个工作表，记录按最早在前显示，将物品类型和物品名称拆分为独立列，添加 `稀有度`、`保底内` 和 `总抽数`，并按稀有度给行着色。

PNG 汇总图会为每个 `pool_type` 创建一个面板，包含稀有度饼图、总抽数、距离最新 S-Class 角色的当前抽数、S-Class 角色历史，以及每个 S-Class 角色的平均抽数。

`nte-recognize` 不会去重。`nte-export-xlsx` 和 `nte-export-png` 会在加载所有 JSON 文件后去重。合并过程会保留表格的逆时间顺序，按池类型、时间戳和行内容对齐重叠截图，将单抽时间戳视为一条记录，或一条记录加 `集点赠礼`，并要求十连时间戳包含 10 抽加一条 `集点赠礼`。缺失时间戳或无效抽取分组会停止导出，以便调查源裁剪/OCR 问题。


## 开发与维护

运行单元测试：

```bash
uv run pytest
```

在 Windows x64 机器上构建便携版 ZIP：

```powershell
.\scripts\build_windows.ps1
```

发布 GitHub Release 时，先更新 `pyproject.toml` 里的 `project.version`，
提交后创建并推送匹配的 tag：

```bash
git tag v0.1.0
git push origin v0.1.0
```

release 工作流以 tag 为准。例如 `v0.1.0` 会发布
`NTE-Dice-Analysis-windows-x64-v0.1.0.zip`。如果需要重新构建已有 release，
可以在 GitHub Actions 里手动运行 `Release Windows ZIP` 工作流并填写已有 tag；
已有 ZIP 资源会被替换。

项目中自带了一个 `known_items.txt` 文件，用于修正 OCR 中可能出现的错误。检查识别出的 JSON 文件是否包含不在 `known_items.txt` 中的物品名称：

```bash
uv run nte-check-known-items *.table.*.json
```

该文件需要跟着卡池更新而更新。
