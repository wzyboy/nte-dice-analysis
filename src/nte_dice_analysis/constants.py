DEFAULT_TABLE_CROP = '0.1823,0.4259,0.8281,0.7870'
DEFAULT_POOL_CROP = '0.2700,0.3350,0.8200,0.4000'
DEFAULT_ROW_BOUNDARIES = '0.1994,0.3660,0.5147,0.6647,0.8135,0.9853'
ARC_ROW_BOUNDARIES = '0,0.2195,0.3925,0.5650,0.7370,0.9000'
DEFAULT_DET_MODEL = 'PP-OCRv5_mobile_det'
DEFAULT_REC_MODEL = 'PP-OCRv5_mobile_rec'
GIFT_ROLL_POINTS = '集点赠礼'
SLEEPING_LAND_ROLL_POINTS = '沉眠地'
BONUS_ROLL_POINTS = {GIFT_ROLL_POINTS, SLEEPING_LAND_ROLL_POINTS}
IMAGE_EXTENSIONS = {'.bmp', '.jpeg', '.jpg', '.png', '.webp'}
LIMITED_POOL_TYPE = '限定棋盘'
STANDARD_POOL_TYPE = '标准棋盘'
ARC_POOL_TYPE = '弧盘研募'
DICE_POOL_TYPES = [LIMITED_POOL_TYPE, STANDARD_POOL_TYPE]
POOL_TYPES = [*DICE_POOL_TYPES, ARC_POOL_TYPE]
S_CLASS = 'S-Class'
A_CLASS = 'A-Class'
B_CLASS = 'B-Class'

COLUMN_BOUNDS = {
    'roll_points': (0.00, 0.22),
    'item_name': (0.22, 0.50),
    'quantity': (0.50, 0.68),
    'obtained_at': (0.68, 1.00),
}

ARC_COLUMN_BOUNDS = {
    'item_name': (0.00, 0.40),
    'research_type': (0.40, 0.68),
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
    'research_type',
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

ARC_XLSX_HEADERS = [
    '研募类型',
    '弧盘名称',
    '稀有度',
    '研募时间',
    '保底内',
    '总研募数',
]
