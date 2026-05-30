DEFAULT_TABLE_CROP = '0.1823,0.4259,0.8281,0.7870'
DEFAULT_POOL_CROP = '0.2700,0.3350,0.8200,0.4000'
DEFAULT_DET_MODEL = 'PP-OCRv5_mobile_det'
DEFAULT_REC_MODEL = 'PP-OCRv5_mobile_rec'
GIFT_ROLL_POINTS = '集点赠礼'
IMAGE_EXTENSIONS = {'.bmp', '.jpeg', '.jpg', '.png', '.webp'}
POOL_TYPES = ['限定棋盘', '标准棋盘']
S_CLASS = 'S-Class'
A_CLASS = 'A-Class'
B_CLASS = 'B-Class'

COLUMN_BOUNDS = {
    'roll_points': (0.00, 0.22),
    'item_name': (0.22, 0.50),
    'quantity': (0.50, 0.68),
    'obtained_at': (0.68, 1.00),
}

OUTPUT_FIELDS = [
    'pool_type',
    'source_image',
    'page_row',
    'roll_points',
    'item_name',
    'rarity',
    'item_name_raw',
    'quantity',
    'obtained_at',
    'obtained_at_raw',
    'confidence',
]

XLSX_HEADERS = [
    '投掷点数',
    '道具类型',
    '道具名称',
    '稀有度',
    '数量',
    '获得时间',
    '保底内',
    '总抽数',
]
