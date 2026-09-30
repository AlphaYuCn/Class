"""星座 → 四象元素 + 互补矩阵

四象元素:
- 火象: 白羊/狮子/射手
- 风象: 双子/天秤/水瓶
- 土象: 金牛/处女/摩羯
- 水象: 巨蟹/天蝎/双鱼

互补规则: 火↔风, 土↔水
"""
from datetime import date

# 星座判定表: (起始月日, 结束月日, 星座名, 元素)
# 起始结束都用 (month, day) 元组, 摩羯跨年单独处理
ZODIAC_RANGES = [
    ((3, 21), (4, 19), "白羊座", "火"),
    ((4, 20), (5, 20), "金牛座", "土"),
    ((5, 21), (6, 21), "双子座", "风"),
    ((6, 22), (7, 22), "巨蟹座", "水"),
    ((7, 23), (8, 22), "狮子座", "火"),
    ((8, 23), (9, 22), "处女座", "土"),
    ((9, 23), (10, 23), "天秤座", "风"),
    ((10, 24), (11, 22), "天蝎座", "水"),
    ((11, 23), (12, 21), "射手座", "火"),
    ((12, 22), (1, 19), "摩羯座", "土"),  # 跨年
    ((1, 20), (2, 18), "水瓶座", "风"),
    ((2, 19), (3, 20), "双鱼座", "水"),
]

# 四象元素简写
FIRE = "火"
WIND = "风"
EARTH = "土"
WATER = "水"
ELEMENTS = (FIRE, WIND, EARTH, WATER)

# 四象互补矩阵: 行=本人, 列=对方
# 火↔风=1.0, 土↔水=1.0, 同象=0.2(轻微相容), 跨象=0.0
ZODIAC_COMPAT = {
    FIRE:  {FIRE: 0.2, WIND: 1.0, EARTH: 0.0, WATER: 0.0},
    WIND:  {FIRE: 1.0, WIND: 0.2, EARTH: 0.0, WATER: 0.0},
    EARTH: {FIRE: 0.0, WIND: 0.0, EARTH: 0.2, WATER: 1.0},
    WATER: {FIRE: 0.0, WIND: 0.0, EARTH: 1.0, WATER: 0.2},
}

ELEMENT_LABEL = {FIRE: "火象", WIND: "风象", EARTH: "土象", WATER: "水象"}


def calc_zodiac(birth: date) -> tuple:
    """根据出生日期返回 (星座名, 四象元素)"""
    if not birth:
        return (None, None)
    m, d = birth.month, birth.day
    for (sm, sd), (em, ed), name, elem in ZODIAC_RANGES:
        if name == "摩羯座":
            # 跨年: 12.22 - 1.19
            if (m == 12 and d >= 22) or (m == 1 and d <= 19):
                return (name, elem)
        elif sm < em:
            # 同年内: 起始月 <= m <= 结束月, 端点按日判定
            if (m == sm and d >= sd) or (m == em and d <= ed) or (sm < m < em):
                return (name, elem)
        # 其他不匹配, 继续
    return (None, None)


def compat_score(elem_a: str, elem_b: str) -> float:
    """四象元素兼容性分数 [0,1]"""
    if not elem_a or not elem_b:
        return 0.0
    return ZODIAC_COMPAT.get(elem_a, {}).get(elem_b, 0.0)
