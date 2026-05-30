# NTE Dice Analysis 异环抽卡记录分析

使用 OCR 将异环抽卡记录截图解析成 JSON，然后生成 XLSX 和 PNG 报告。

示例输出：

![screenshot](./example.png)

UI 仿自 [StarRailWarpExport](https://github.com/biuuu/star-rail-warp-export) 项目。

代码大部分是 Codex 写的。

目前试过处理 3860x2140 分辨率的截图，并且只能处理中文 UI。

If you ever need to process game languages other than Simplified Chinese, you are welcome to fork and modify the code yourself.

## 运行

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

检查识别出的 JSON 文件是否包含不在 `known_items.txt` 中的物品名称：

```bash
uv run nte-check-known-items *.table.*.json
```

这个文件用于修正 OCR 中的错误，它需要跟着卡池更新而更新。使用 `--known-items path/to/known_items.txt` 可以覆盖它；脚本会在 JSON 文件的 `item_name_raw` 字段中保留原始 OCR 文本，便于审计。

你可以传入文件或目录。目录会按排序后的顺序展开。`nte-crop` 会展开受支持的图片文件；`nte-recognize` 会展开文件名中带有 `.table.` 的裁剪表格图片；`nte-export-xlsx`、`nte-export-png` 和 `nte-check-known-items` 会展开 JSON 文件。`nte-crop` 和 `nte-recognize` 默认会跳过已存在的确定性输出；传入 `--overwrite` 可重新生成。

OCR 命令默认使用 `--device auto`：当 Paddle 使用 CUDA 构建且可以看到 GPU 时使用 `gpu:0`，否则使用 CPU。PaddleX 会自动解析并下载默认的 PP-OCRv5 服务端检测和识别模型。仅在指向已存在的本地模型目录时才使用 `--det-model-dir` 或 `--rec-model-dir`。

默认裁剪参数针对 3840x2160 的 Windows 游戏客户端截图进行了调校。如果游戏窗口大小或表格位置发生变化，请调整裁剪区域：

```bash
uv run nte-crop sample.png --table-crop 0.1823,0.4259,0.8281,0.7870
```

`--table-crop` 既接受 `0` 到 `1` 的归一化坐标，也接受像素坐标。`--pool-crop` 的工作方式相同，用于裁剪 `棋盘类型` 下拉框，并将其结果填入裁剪文件名中的池类型。

`rarity` 输出列根据物品名称的文本颜色检测：金色为 `S-Class`，紫色为 `A-Class`，灰色为 `B-Class`。

XLSX 工作簿会为每个 `pool_type` 创建一个工作表，记录按最早在前显示，将物品类型和物品名称拆分为独立列，添加 `稀有度`、`保底内` 和 `总抽数`，并按稀有度给行着色。

PNG 汇总图会为每个 `pool_type` 创建一个面板，包含稀有度饼图、总抽数、距离最新 S-Class 角色的当前抽数、S-Class 角色历史，以及每个 S-Class 角色的平均抽数。

`nte-recognize` 不会去重。`nte-export-xlsx` 和 `nte-export-png` 会在加载所有 JSON 文件后去重。合并过程会保留表格的逆时间顺序，按池类型、时间戳和行内容对齐重叠截图，将单抽时间戳视为一条记录，或一条记录加 `集点赠礼`，并要求十连时间戳包含 10 抽加一条 `集点赠礼`。缺失时间戳或无效抽取分组会停止导出，以便调查源裁剪/OCR 问题。

## 开发

使用 dev 依赖组运行单元测试：

```bash
uv run --group dev pytest
```
