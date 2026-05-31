from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GuiText:
    activity_log: str = '活动日志'
    add_files: str = '添加文件'
    add_folder: str = '添加文件夹'
    advanced_crop_settings: str = '高级裁剪设置'
    advanced_ocr_settings: str = '高级 OCR 设置'
    advanced_tab: str = '高级'
    browse: str = '浏览'
    clear: str = '清空'
    complete: str = '完成'
    crop_tab: str = '裁剪'
    debug_directory: str = '调试目录'
    detection_model: str = '检测模型'
    export_tab: str = '导出'
    failed: str = '失败'
    file_filter_images: str = '图片 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)'
    file_filter_json: str = 'JSON 文件 (*.json);;所有文件 (*)'
    file_filter_png: str = 'PNG (*.png)'
    file_filter_text: str = '文本文件 (*.txt);;所有文件 (*)'
    file_filter_xlsx: str = 'XLSX (*.xlsx)'
    json_files: str = 'JSON 文件'
    known_items: str = '已知道具'
    log: str = '日志'
    min_score: str = '最低分数'
    open_folder: str = '打开文件夹'
    open_log_file: str = '打开日志文件'
    open_png: str = '打开 PNG'
    open_selected: str = '打开选中项'
    open_xlsx: str = '打开 XLSX'
    output_directory: str = '输出目录'
    output_folder: str = '输出文件夹'
    outputs: str = '输出'
    overwrite_existing_json_files: str = '覆盖已有 JSON 文件'
    overwrite_existing_table_images: str = '覆盖已有表格图片'
    pool_crop: str = '卡池裁剪区域'
    pool_type_override: str = '卡池类型覆盖'
    ready: str = '准备就绪'
    recognition_model: str = '识别模型'
    recognize_tab: str = '识别'
    records: str = '记录'
    row_boundaries: str = '行边界'
    run_analysis: str = '开始分析'
    run_crop: str = '开始裁剪'
    run_export: str = '开始导出'
    run_ocr: str = '开始 OCR'
    running: str = '正在运行...'
    screenshots: str = '截图'
    select_file: str = '选择文件'
    select_folder: str = '选择文件夹'
    select_json_files: str = '选择 JSON 文件'
    select_output_file: str = '选择输出文件'
    select_screenshots: str = '选择截图'
    select_table_images: str = '选择表格图片'
    simple_tab: str = '简单'
    table_crop: str = '表格裁剪区域'
    table_images: str = '表格图片'
    task_failed: str = '任务失败'
    warning_title: str = 'NTE Dice Analysis'
    working: str = '正在处理...'
    write_png: str = '写入 PNG'
    write_xlsx: str = '写入 XLSX'


@dataclass(frozen=True, slots=True)
class WarningText:
    select_screenshot_or_folder: str = '请至少选择一张截图或一个文件夹。'
    select_output_folder: str = '请选择输出文件夹。'
    select_table_image_or_folder: str = '请至少选择一张表格图片或一个文件夹。'
    select_json_file_or_folder: str = '请至少选择一个 JSON 文件或一个文件夹。'
    task_already_running: str = '已有任务正在运行。'
    select_output_first: str = '请先选择一个输出项。'
    output_missing: str = '输出不存在：{path}'
    log_open_failed: str = '无法打开日志文件：{path}'
    select_output_folder_first: str = '请先选择输出文件夹。'
    output_folder_missing: str = '输出文件夹不存在：{path}'


GUI_TEXT = GuiText()
WARNING_TEXT = WarningText()

OUTPUT_FIELD_LABELS: dict[str, str] = {
    'pool_type': '卡池类型',
    'source_image': '来源截图',
    'page_row': '页内行',
    'roll_points': '投掷点数',
    'item_name': '道具名称',
    'rarity': '稀有度',
    'item_name_raw': 'OCR 原始名称',
    'quantity': '数量',
    'obtained_at': '获得时间',
    'obtained_at_raw': 'OCR 原始时间',
    'confidence': '置信度',
}
