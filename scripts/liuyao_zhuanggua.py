#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周易六爻装卦引擎（京房纳甲法 / 增删卜易体系）——纯标准库，无外部依赖。

能力：
  1. 由「六爻阴阳 + 起卦干支」装出完整卦表：八宫归属、卦名、世应、纳甲、六亲、六神、伏神、变卦、旬空
     （年柱/月柱按内置 1900-2100 精确节气表判定；子时归次日）
  2. 解析元亨利贞网标准装卦表文本为结构化数据
  3. 用纳甲与六亲规则校验既有卦表是否装错

六爻表示约定：字符串自下而上（第 1 位=初爻），'1'=阳爻，'0'=阴爻。
例：乾为天='111111'，火雷噬嗑='100101'（下震100 + 上离101）。

命令行用法：
  python liuyao_zhuanggua.py --gua "上离下坎" --dong 5 --date "2026-09-14 12:45"
  python liuyao_zhuanggua.py --gua-bin 010101 --dong 1,2,5 --ganzhi "丙午 丁酉 辛卯 甲午"
  python liuyao_zhuanggua.py --parse-text dump.txt
  python liuyao_zhuanggua.py --self-test
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

try:  # Windows 控制台默认非 UTF-8，强制以 UTF-8 输出，避免中文乱码
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

GAN = '甲乙丙丁戊己庚辛壬癸'
ZHI = '子丑寅卯辰巳午未申酉戌亥'

ZHI_WX = {'子': '水', '丑': '土', '寅': '木', '卯': '木', '辰': '土', '巳': '火',
          '午': '火', '未': '土', '申': '金', '酉': '金', '戌': '土', '亥': '水'}
WX_SHENG = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
WX_KE = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}

# ---------- 经卦 ----------
# 三爻字符串自下而上；乾111 兑110 离101 震100 巽011 坎010 艮001 坤000
TRIGRAM = {'111': '乾', '110': '兑', '101': '离', '100': '震',
           '011': '巽', '010': '坎', '001': '艮', '000': '坤'}
TRIGRAM_ALIAS = {'乾': '天', '兑': '泽', '离': '火', '震': '雷',
                 '巽': '风', '坎': '水', '艮': '山', '坤': '地'}
PALACE_WX = {'乾': '金', '坎': '水', '艮': '土', '震': '木',
             '巽': '木', '离': '火', '坤': '土', '兑': '金'}

# 八宫首卦（纯卦）六爻位序，自下而上
PURE_GUA = {'乾': '111111', '兑': '110110', '离': '101101', '震': '100100',
            '巽': '011011', '坎': '010010', '艮': '001001', '坤': '000000'}

# 京房八宫：相对本宫首卦的取反爻位 -> (世爻位置)
# 本宫=纯卦；一世~五世依次多反一爻；游魂=五世卦第四爻再反回；
# 归魂=游魂卦的内卦（初二三）回本宫原值，等价于只反第五爻。
FLIP_RULES = [([], 6), ([1], 1), ([1, 2], 2), ([1, 2, 3], 3),
              ([1, 2, 3, 4], 4), ([1, 2, 3, 4, 5], 5),
              ([1, 2, 3, 5], 4),   # 游魂，世四
              ([5], 3)]            # 归魂，世三

GONG_LABEL = ['本宫', '一世', '二世', '三世', '四世', '五世', '游魂', '归魂']

# 六十四卦标准卦名：(上经卦, 下经卦) -> 卦名
GUA_NAME = {
    ('乾', '乾'): '乾为天', ('乾', '兑'): '天泽履', ('乾', '离'): '天火同人', ('乾', '震'): '天雷无妄',
    ('乾', '巽'): '天风姤', ('乾', '坎'): '天水讼', ('乾', '艮'): '天山遁', ('乾', '坤'): '天地否',
    ('兑', '乾'): '泽天夬', ('兑', '兑'): '兑为泽', ('兑', '离'): '泽火革', ('兑', '震'): '泽雷随',
    ('兑', '巽'): '泽风大过', ('兑', '坎'): '泽水困', ('兑', '艮'): '泽山咸', ('兑', '坤'): '泽地萃',
    ('离', '乾'): '火天大有', ('离', '兑'): '火泽睽', ('离', '离'): '离为火', ('离', '震'): '火雷噬嗑',
    ('离', '巽'): '火风鼎', ('离', '坎'): '火水未济', ('离', '艮'): '火山旅', ('离', '坤'): '火地晋',
    ('震', '乾'): '雷天大壮', ('震', '兑'): '雷泽归妹', ('震', '离'): '雷火丰', ('震', '震'): '震为雷',
    ('震', '巽'): '雷风恒', ('震', '坎'): '雷水解', ('震', '艮'): '雷山小过', ('震', '坤'): '雷地豫',
    ('巽', '乾'): '风天小畜', ('巽', '兑'): '风泽中孚', ('巽', '离'): '风火家人', ('巽', '震'): '风雷益',
    ('巽', '巽'): '巽为风', ('巽', '坎'): '风水涣', ('巽', '艮'): '风山渐', ('巽', '坤'): '风地观',
    ('坎', '乾'): '水天需', ('坎', '兑'): '水泽节', ('坎', '离'): '水火既济', ('坎', '震'): '水雷屯',
    ('坎', '巽'): '水风井', ('坎', '坎'): '坎为水', ('坎', '艮'): '水山蹇', ('坎', '坤'): '水地比',
    ('艮', '乾'): '山天大畜', ('艮', '兑'): '山泽损', ('艮', '离'): '山火贲', ('艮', '震'): '山雷颐',
    ('艮', '巽'): '山风蛊', ('艮', '坎'): '山水蒙', ('艮', '艮'): '艮为山', ('艮', '坤'): '山地剥',
    ('坤', '乾'): '地天泰', ('坤', '兑'): '地泽临', ('坤', '离'): '地火明夷', ('坤', '震'): '地雷复',
    ('坤', '巽'): '地风升', ('坤', '坎'): '地水师', ('坤', '艮'): '地山谦', ('坤', '坤'): '坤为地',
}


def build_gua_short():
    """卦名简称索引，方便直接输卦名。

    - 四字卦名取后两字：天火同人 → 同人、火雷噬嗑 → 噬嗑；
    - 三字卦名取末字：天风姤 → 姤、天水讼 → 讼；
      但末字若与八经卦别名同字（乾为天 →「天」）不收，
      否则「天」会同时指向乾卦与乾为天，产生歧义。
    - 只收录在六十四卦内**唯一**的简称；一旦重名便不收录，
      宁可让使用者补全卦名，也不做猜测。
    """
    bucket = {}
    alias_set = set(TRIGRAM_ALIAS.values())     # 天泽火雷风水山地
    for (upper, lower), name in GUA_NAME.items():
        cands = []
        if len(name) == 4:
            cands.append(name[2:])
        if len(name) == 3 and name[2] not in alias_set:
            cands.append(name[2])
        for c in cands:
            bucket.setdefault(c, []).append((upper, lower))
    return {k: v[0] for k, v in bucket.items() if len(v) == 1}


GUA_SHORT = build_gua_short()

# ---------- 纳甲 ----------
NAJIA = {  # 内卦（下三爻，自下而上）
    '乾': [('甲', '子'), ('甲', '寅'), ('甲', '辰')],
    '震': [('庚', '子'), ('庚', '寅'), ('庚', '辰')],
    '坎': [('戊', '寅'), ('戊', '辰'), ('戊', '午')],
    '艮': [('丙', '辰'), ('丙', '午'), ('丙', '申')],
    '坤': [('乙', '未'), ('乙', '巳'), ('乙', '卯')],
    '巽': [('辛', '丑'), ('辛', '亥'), ('辛', '酉')],
    '离': [('己', '卯'), ('己', '丑'), ('己', '亥')],
    '兑': [('丁', '巳'), ('丁', '卯'), ('丁', '丑')],
}
NAJIA_OUT = {  # 外卦（上三爻，自下而上）
    '乾': [('壬', '午'), ('壬', '申'), ('壬', '戌')],
    '坎': [('戊', '申'), ('戊', '戌'), ('戊', '子')],
    '艮': [('丙', '戌'), ('丙', '子'), ('丙', '寅')],
    '震': [('庚', '午'), ('庚', '申'), ('庚', '戌')],
    '巽': [('辛', '未'), ('辛', '巳'), ('辛', '卯')],
    '离': [('己', '酉'), ('己', '未'), ('己', '巳')],
    '坤': [('癸', '丑'), ('癸', '亥'), ('癸', '酉')],
    '兑': [('丁', '亥'), ('丁', '酉'), ('丁', '未')],
}

# 六神起例：甲乙起青龙、丙丁起朱雀、戊起勾陈、己起螣蛇、庚辛起白虎、壬癸起玄武
LIUSHEN_SEQ = ['青龙', '朱雀', '勾陈', '螣蛇', '白虎', '玄武']
LIUSHEN_START = {'甲': 0, '乙': 0, '丙': 1, '丁': 1, '戊': 2,
                 '己': 3, '庚': 4, '辛': 4, '壬': 5, '癸': 5}

# 地支六冲：子午、丑未、寅申、卯酉、辰戌、巳亥
ZHI_CHONG_PAIRS = [frozenset(p) for p in (
    ('子', '午'), ('丑', '未'), ('寅', '申'), ('卯', '酉'), ('辰', '戌'), ('巳', '亥'))]
# 地支六合：子丑、寅亥、卯戌、辰酉、巳申、午未
ZHI_HE_PAIRS = [frozenset(p) for p in (
    ('子', '丑'), ('寅', '亥'), ('卯', '戌'), ('辰', '酉'), ('巳', '申'), ('午', '未'))]

GUA64 = {}


def build_gua64():
    """生成 64 卦表：位序 -> {name, palace, shi, ying, gong_label, lower, upper}"""
    table = {}
    names = set()
    for palace, pure in PURE_GUA.items():
        for idx, (flips, shi) in enumerate(FLIP_RULES):
            bits = list(pure)
            for f in flips:
                bits[f - 1] = '1' if bits[f - 1] == '0' else '0'
            code = ''.join(bits)
            lower = TRIGRAM[code[0:3]]
            upper = TRIGRAM[code[3:6]]
            name = GUA_NAME[(upper, lower)]
            # 世应相隔三爻：世一应四、世二应五、世三应六、世四应初、世五应二、世六应三
            ying = shi + 3 if shi <= 3 else shi - 3
            if code in table:
                raise AssertionError('卦表冲突: %s -> %s / %s' % (code, table[code]['name'], name))
            table[code] = {'name': name, 'palace': palace, 'shi': shi, 'ying': ying,
                           'gong_label': GONG_LABEL[idx], 'lower': lower, 'upper': upper}
            names.add(name)
    if len(table) != 64:
        raise AssertionError('卦表数量异常: %d' % len(table))
    if len(names) != 64:
        raise AssertionError('卦名不唯一: %d 个' % len(names))
    return table


GUA64 = build_gua64()


def liuqin(gong_wx, zhi):
    zw = ZHI_WX[zhi]
    if gong_wx == zw:
        return '兄弟'
    if WX_SHENG[gong_wx] == zw:
        return '子孙'
    if WX_KE[gong_wx] == zw:
        return '妻财'
    if WX_SHENG[zw] == gong_wx:
        return '父母'
    if WX_KE[zw] == gong_wx:
        return '官鬼'
    raise ValueError('无法定六亲: %s / %s' % (gong_wx, zhi))


def najia_of(lower, upper):
    """返回六爻（初->上）纳甲 [(gan, zhi)]"""
    return list(NAJIA[lower]) + list(NAJIA_OUT[upper])


# ---------- 干支与旬空 ----------
JDN_ANCHOR_DATE = date(2026, 9, 14)
JDN_ANCHOR_GANZHI = '辛卯'


def gz_index(gz):
    for i in range(60):
        if GAN[i % 10] + ZHI[i % 12] == gz:
            return i
    raise ValueError('非干支: %s' % gz)


def jdn(y, m, d):
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


ANCHOR_JDN = jdn(JDN_ANCHOR_DATE.year, JDN_ANCHOR_DATE.month, JDN_ANCHOR_DATE.day)
ANCHOR_IDX = gz_index(JDN_ANCHOR_GANZHI)


def day_ganzhi(y, m, d):
    idx = (ANCHOR_IDX + (jdn(y, m, d) - ANCHOR_JDN)) % 60
    return GAN[idx % 10] + ZHI[idx % 12]


def xunkong(day_gz):
    """日空亡（旬空），返回两个地支"""
    idx = gz_index(day_gz)
    xun_start = idx - idx % 10
    k1 = GAN[(xun_start + 10) % 10] + ZHI[(xun_start + 10) % 12]
    k2 = GAN[(xun_start + 11) % 10] + ZHI[(xun_start + 11) % 12]
    return [k1[1], k2[1]]


HOUR_ZHI_IDX = {'子': 0, '丑': 1, '寅': 2, '卯': 3, '辰': 4, '巳': 5,
                '午': 6, '未': 7, '申': 8, '酉': 9, '戌': 10, '亥': 11}
# 日干 -> 子时天干
ZI_HOUR_GAN = {'甲': '甲', '己': '甲', '乙': '丙', '庚': '丙', '丙': '戊', '辛': '戊',
               '丁': '庚', '壬': '庚', '戊': '壬', '癸': '壬'}


def hour_ganzhi(day_gan, hour24):
    """时柱。23 时起即子时；此时 day_gan 应传【次日】日干（子时归次日的通行口径）。"""
    zhi = ZHI[((hour24 + 1) // 2) % 12]
    start_gan = ZI_HOUR_GAN[day_gan]
    gi = (GAN.index(start_gan) + ZHI.index(zhi)) % 10
    return GAN[gi] + zhi


# ---------- 节气（精确表） ----------
# 年柱以立春为界、月柱以十二「节」为界，判定依据是节气【时刻】而非日期，
# 因此交界日必须精确到分钟。本表覆盖 1900-2100 年，出处与校验见文件末尾。
JIEQI_C_APPROX = {'小寒': 5.4055, '立春': 3.87, '惊蛰': 5.63, '清明': 4.81, '立夏': 5.52,
                  '芒种': 5.678, '小暑': 7.108, '立秋': 7.5, '白露': 7.646, '寒露': 8.318,
                  '立冬': 7.438, '大雪': 7.18}
JIE_TO_MONTH_ZHI = {'立春': '寅', '惊蛰': '卯', '清明': '辰', '立夏': '巳', '芒种': '午',
                    '小暑': '未', '立秋': '申', '白露': '酉', '寒露': '戌', '立冬': '亥',
                    '大雪': '子', '小寒': '丑'}
MONTH_GAN_START = {'甲': '丙', '己': '丙', '乙': '戊', '庚': '戊', '丙': '庚', '辛': '庚',
                   '丁': '壬', '壬': '壬', '戊': '甲', '癸': '甲'}


def jieqi_minute(year, name):
    """该年该「节」的年内分钟数（1 月 1 日 0 时为 0）。
    返回 (分钟, 是否取自精确表)。超出表范围则按近似公式推算，误差通常 ≤1 天。"""
    if JIEQI_FIRST_YEAR <= year <= JIEQI_LAST_YEAR:
        i = JIE_ORDER.index(name)
        off = (year - JIEQI_FIRST_YEAR) * 48 + i * 4
        v = int(JIEQI_B36[off:off + 4], 36)
        return v, True
    y2 = year % 100
    doy = int(y2 * 0.2422 + JIEQI_C_APPROX[name]) - int((y2 - 1) / 4)
    return (doy - 1) * 1440, False


def year_month_ganzhi(y, m, d, hh=0, mm=0):
    """年柱按立春、月柱按节气，判据为【时刻】。
    返回 (年柱, 月柱, 是否全部取自精确表)"""
    now = (date(y, m, d).toordinal() - date(y, 1, 1).toordinal()) * 1440 + hh * 60 + mm
    precise = True
    cur = None
    for name in JIE_ORDER:
        jm, ok = jieqi_minute(y, name)
        if not ok:
            precise = False
        if now >= jm:
            cur = name
        else:
            break
    # 小寒之前属上一年的子月（大雪月）
    month_zhi = JIE_TO_MONTH_ZHI[cur] if cur else '子'

    lichun, ok = jieqi_minute(y, '立春')
    if not ok:
        precise = False
    yg_year = y if now >= lichun else y - 1
    year_gz = GAN[(yg_year - 4) % 10] + ZHI[(yg_year - 4) % 12]

    start_gan = MONTH_GAN_START[year_gz[0]]
    offset = (ZHI.index(month_zhi) - ZHI.index('寅')) % 12
    month_gan = GAN[(GAN.index(start_gan) + offset) % 10]
    return year_gz, month_gan + month_zhi, precise


def resolve_time(args):
    """返回 (年柱, 月柱, 日柱, 时柱, 旬空, 来源说明)"""
    if args.ganzhi:
        parts = re.split(r'[\s,，]+', args.ganzhi.strip())
        parts = [p for p in parts if p]
        if len(parts) != 4:
            raise SystemExit('--ganzhi 需要四个柱，如 "丙午 丁酉 辛卯 甲午"')
        yg, mg, dg, hg = parts
        return yg, mg, dg, hg, xunkong(dg), '用户给定干支（精确）'
    if not args.date:
        raise SystemExit('需要 --date "YYYY-MM-DD HH:MM" 或 --ganzhi "年 月 日 时"')
    raw = args.date.strip()
    dt = None
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if dt is None:
        raise SystemExit('--date 格式应为 "YYYY-MM-DD HH:MM"，例如 "2026-09-14 12:45"')
    yg, mg, precise = year_month_ganzhi(dt.year, dt.month, dt.day, dt.hour, dt.minute)
    # 子时（23:00-23:59）按通行口径归次日：日柱推进一日，时柱以次日日干起子时
    zi_next = dt.hour == 23
    dz = dt + timedelta(days=1) if zi_next else dt
    dg = day_ganzhi(dz.year, dz.month, dz.day)
    hg = hour_ganzhi(dg[0], dt.hour)
    src = '日柱/时柱精确；年柱/月柱按节气表判定'
    if not precise:
        src += '（年份超出 1900-2100 内置节气表，年柱/月柱为近似值，请核对）'
    if zi_next:
        src += '；23 时起子时归次日，日柱已推进一日'
    return yg, mg, dg, hg, xunkong(dg), src


# 别名反向索引：天→乾、泽→兑、火→离……
ALIAS_TO_TRIGRAM = {v: k for k, v in TRIGRAM_ALIAS.items()}

# 输入中可忽略的字符（标点、引号、空白）
_NOISE_CHARS = ('\u3000', ' ', '\t', '\n', '\r',
                '，', '。', '、', '：', ':', ',', '.', '；', ';',
                '／', '/', '|', '\\', '「', '」', '“', '”', '"', "'", '‘', '’',
                '（', '）', '(', ')', '·', '－', '-')


def _norm_input(s):
    """归一化整串输入：去掉标点与所有空白。"""
    t = s or ''
    for ch in _NOISE_CHARS:
        t = t.replace(ch, '')
    return t


def _clean_tri(t):
    """清理经卦分量里的口语虚词：如「上卦为离」切出的「卦为离」→「离」。"""
    t = t or ''
    for w in ('卦', '是', '为', '的', '在', '边', '位'):
        t = t.replace(w, '')
    return t.strip()


def _tri_code(t):
    """经卦名或别名 → 三爻位序（自下而上）；无法识别返回 None。"""
    n = _clean_tri(t)
    if n in PURE_GUA:
        return PURE_GUA[n][0:3]
    if n in ALIAS_TO_TRIGRAM:
        return PURE_GUA[ALIAS_TO_TRIGRAM[n]][0:3]
    return None


def _code_of_pair(upper, lower):
    """上经卦名 + 下经卦名 → 六爻位序（自下而上）"""
    return PURE_GUA[lower][0:3] + PURE_GUA[upper][3:6]


_GUA_HINT = ('可用写法：上离下巽 / 上卦为离下卦为巽 / 离上巽下 / 火风鼎（六十四卦名或其简称）/ '
             '011101（六位阴阳，自下而上）')


def parse_gua_arg(gua=None, gua_bin=None):
    """把本卦输入转成六爻位序（自下而上）与「上X下Y」标签。

    接受下列写法（大小写无关，标点与空格可任意）：

      --gua "上离下巽"              经卦写法：先上卦、后下卦
      --gua "上卦为离，下卦为巽"      口语写法
      --gua "离上巽下"              倒装写法
      --gua "上火下风"              别名写法（天泽火雷风水山地）
      --gua "火风鼎"                六十四卦标准卦名
      --gua "火风鼎卦"              带「卦」字的卦名
      --gua "噬嗑"                  唯一的卦名简称
      --gua "011101"                六位阴阳（自下而上，1=阳 0=阴）
      --gua-bin "011101"            同上，显式写法

    认不出的输入一律明确报错，不猜测。
    """
    if gua_bin:
        code = re.sub(r'[^01]', '', gua_bin)
        if len(code) != 6:
            raise SystemExit('--gua-bin 需要 6 位 0/1（自下而上）')
        return code, TRIGRAM[code[3:6]] + TRIGRAM[code[0:3]]
    if not gua:
        raise SystemExit('需要 --gua（如 上离下巽）或 --gua-bin')
    raw = gua.strip()
    s = _norm_input(raw)

    # ① 直接给六位阴阳
    if re.fullmatch(r'[01]{6}', s):
        return s, TRIGRAM[s[3:6]] + TRIGRAM[s[0:3]]

    # ② 「上X下Y」及口语变体
    m = re.match(r'^上(.*?)下(.*)$', s)
    if m:
        uc, lc = _tri_code(m.group(1)), _tri_code(m.group(2))
        if uc and lc:
            return _code_of_pair(TRIGRAM[uc], TRIGRAM[lc]), TRIGRAM[uc] + TRIGRAM[lc]
        bad = [t for t in (_clean_tri(m.group(1)), _clean_tri(m.group(2))) if t]
        raise SystemExit('无法识别经卦：%s。经卦限 乾兑离震巽坎艮坤（别名 天泽火雷风水山地），'
                         '如「上离下巽」' % ('、'.join(bad) or raw))

    # ③ 倒装写法「X上Y下」（如 离上巽下）
    m = re.match(r'^(.*?)上(.*?)下$', s)
    if m:
        uc, lc = _tri_code(m.group(1)), _tri_code(m.group(2))
        if uc and lc:
            return _code_of_pair(TRIGRAM[uc], TRIGRAM[lc]), TRIGRAM[uc] + TRIGRAM[lc]

    # ④ 六十四卦标准卦名，或唯一的卦名简称（可带「卦」字，如「火风鼎卦」）
    key = s[:-1] if s.endswith('卦') and s not in GUA_NAME_REV else s
    pair = GUA_NAME_REV.get(key) or GUA_SHORT.get(key)
    if pair:
        upper, lower = pair
        return _code_of_pair(upper, lower), upper + lower

    raise SystemExit('无法识别卦：%s。%s' % (raw, _GUA_HINT))


def parse_dong_arg(s):
    """动爻参数 → 升序、去重后的爻位列表。空串＝静卦。越界一律报错。"""
    dong = [int(x) for x in re.split(r'[^0-9]+', s or '') if x]
    for p in dong:
        if not 1 <= p <= 6:
            raise SystemExit('动爻须在 1-6：%s' % p)
    return sorted(set(dong))




def chonghe_of(lines):
    """按纳甲地支判定六冲卦／六合卦。

    判据：初—四、二—五、三—六 三对爻位的地支
          —— 三对全部相冲为「六冲卦」，三对全部相合为「六合卦」，其余两者皆非。
    依此判据，六冲卦为八纯卦加天雷无妄、雷天大壮共十卦；六合卦为地天泰、
    天地否、雷地豫、地雷复、火山旅、山火贲、水泽节、泽水困共八卦。
    """
    pairs = [frozenset((lines[0]['zhi'], lines[3]['zhi'])),
             frozenset((lines[1]['zhi'], lines[4]['zhi'])),
             frozenset((lines[2]['zhi'], lines[5]['zhi']))]
    if all(p in ZHI_CHONG_PAIRS for p in pairs):
        return '六冲卦'
    if all(p in ZHI_HE_PAIRS for p in pairs):
        return '六合卦'
    return ''


def zhuanggua(code, dong, yg, mg, dg, hg, kong):
    info = GUA64.get(code)
    if not info:
        raise ValueError('未知卦: %s' % code)
    palace = info['palace']
    gong_wx = PALACE_WX[palace]
    nj = najia_of(info['lower'], info['upper'])
    ls_start = LIUSHEN_START[dg[0]]

    lines = []
    for i in range(6):
        gan, zhi = nj[i]
        lines.append({
            'pos': i + 1,                       # 1=初爻
            'yang': code[i] == '1',
            'najia': gan + zhi,
            'zhi': zhi,
            'wuxing': ZHI_WX[zhi],
            'liuqin': liuqin(gong_wx, zhi),
            'liushen': LIUSHEN_SEQ[(ls_start + i) % 6],
            'shi': (i + 1) == info['shi'],
            'ying': (i + 1) == info['ying'],
            'kong': zhi in kong,
            'dong': (i + 1) in dong,
        })

    # 伏神：本卦缺失的六亲，取本宫首卦同爻位
    have = {l['liuqin'] for l in lines}
    pure_code = PURE_GUA[palace]
    pure_info = GUA64[pure_code]
    pure_nj = najia_of(pure_info['lower'], pure_info['upper'])
    fu = []
    for i in range(6):
        qin = liuqin(gong_wx, pure_nj[i][1])
        if qin not in have:
            fu.append({'pos': i + 1, 'liuqin': qin,
                       'najia': pure_nj[i][0] + pure_nj[i][1],
                       'under': lines[i]['liuqin']})

    # 变卦
    bian = None
    if dong:
        bcode = list(code)
        for p in dong:
            bcode[p - 1] = '1' if bcode[p - 1] == '0' else '0'
        bcode = ''.join(bcode)
        binfo = GUA64[bcode]
        bnj = najia_of(binfo['lower'], binfo['upper'])
        blines = []
        for i in range(6):
            gan, zhi = bnj[i]
            blines.append({'pos': i + 1,
                           'yang': bcode[i] == '1',
                           'najia': gan + zhi,
                           'zhi': zhi,
                           'wuxing': ZHI_WX[zhi],
                           # 变爻六亲按【本卦宫】定（与论坛排盘一致）
                           'liuqin': liuqin(gong_wx, zhi),
                           'shi': (i + 1) == binfo['shi'],
                           'ying': (i + 1) == binfo['ying'],
                           'kong': zhi in kong,
                           'dong': (i + 1) in dong})
        bian = {'code': bcode, 'name': binfo['name'], 'palace': binfo['palace'],
                'palace_wx': PALACE_WX[binfo['palace']],
                'gong_label': binfo['gong_label'],
                'lower': binfo['lower'], 'upper': binfo['upper'],
                'shi_pos': binfo['shi'], 'ying_pos': binfo['ying'],
                'chonghe': chonghe_of(blines),
                'lines': blines,
                'changed': [{'pos': p, 'from': lines[p - 1]['najia'],
                             'to': blines[p - 1]['najia'],
                             'to_liuqin': blines[p - 1]['liuqin']} for p in dong]}

    return {
        'time': {'year': yg, 'month': mg, 'day': dg, 'hour': hg, 'xunkong': kong},
        'ben_gua': {'code': code, 'name': info['name'], 'palace': palace,
                    'palace_wx': gong_wx, 'gong_label': info['gong_label'],
                    'lower': info['lower'], 'upper': info['upper'],
                    'shi_pos': info['shi'], 'ying_pos': info['ying'],
                    'chonghe': chonghe_of(lines)},
        'lines': lines,
        'fushen': fu,
        'bian_gua': bian,
        'dong': sorted(dong),
    }


POS_LABEL = {1: '初爻', 2: '二爻', 3: '三爻', 4: '四爻', 5: '五爻', 6: '六爻'}
YANG_BAR = '\u2585\u2585\u2585\u2585\u2585'    # ▅▅▅▅▅
YIN_BAR = '\u2585\u2585 \u2585\u2585'          # ▅▅ ▅▅


def dw(s):
    """显示宽度：汉字/全角字符按 2 格计。"""
    return sum(2 if ord(c) > 0x2E7F else 1 for c in (s or ''))


def pad(s, n, right=False):
    """按显示宽度补齐到 n 格；超长则按显示宽度截断。"""
    s = s or ''
    while s and dw(s) > n:
        s = s[:-1]
    fill = ' ' * (n - dw(s))
    return fill + s if right else s + fill


def render_text(r):
    t = r['time']
    b = r['ben_gua']
    out = []
    out.append('起卦：%s年 %s月 %s日 %s时（旬空：%s）' % (t['year'], t['month'], t['day'], t['hour'], ''.join(t['xunkong'])))
    ch_tag = ('  ' + b['chonghe']) if b.get('chonghe') else ''
    out.append('%s（%s宫·%s%s）  世%d爻 应%d爻   动爻：%s%s'
               % (b['name'], b['palace'], b['gong_label'], b['palace_wx'],
                  b['shi_pos'], b['ying_pos'],
                  ','.join(str(x) for x in r['dong']) if r['dong'] else '无（静卦）',
                  ch_tag))
    if r['bian_gua']:
        bch = ('  ' + r['bian_gua']['chonghe']) if r['bian_gua'].get('chonghe') else ''
        out.append('变卦：%s（%s宫·%s）%s' % (r['bian_gua']['name'], r['bian_gua']['palace'],
                                             r['bian_gua']['gong_label'], bch))
    out.append('')
    fu_at = dict((f['pos'], f) for f in r['fushen'])
    out.append('  '.join([pad('爻位', 4), pad('六神', 4),
                          pad('本卦 六亲纳甲五行', 20),
                          pad('世应', 4), pad('动', 2), pad('空', 2),
                          pad('变爻', 14), '伏神']))
    for i in range(5, -1, -1):
        l = r['lines'][i]
        mark = '世' if l['shi'] else ('应' if l['ying'] else '')
        dong_mark = '动' if l['dong'] else ''
        kong_mark = '空' if l['kong'] else ''
        bt = ''
        if r['bian_gua'] and l['dong']:
            chg = [c for c in r['bian_gua']['changed'] if c['pos'] == l['pos']]
            if chg:
                bt = '%s %s' % (chg[0]['to'], chg[0]['to_liuqin'])
        fu = fu_at.get(l['pos'])
        fu_txt = ('%s%s' % (fu['liuqin'], fu['najia'])) if fu else ''
        label = POS_LABEL[l['pos']]
        out.append('  '.join([
            pad(label, 4), pad(l['liushen'], 4),
            pad('%s%s%s' % (l['liuqin'], l['najia'], l['wuxing']), 20),
            pad(mark, 4), pad(dong_mark, 2), pad(kong_mark, 2),
            pad(bt, 14), fu_txt]))
    if r['fushen']:
        out.append('')
        out.append('伏神：' + '；'.join('%s %s（伏于%s %s下）' % (
            f['liuqin'], f['najia'], POS_LABEL[f['pos']], f['under'])
            for f in r['fushen']))
    if r['bian_gua']:
        bg = r['bian_gua']
        out.append('')
        out.append('变卦逐爻（%s·%s%s；六亲按本卦%s宫定，世应为变卦自身）'
                   % (bg['name'], bg['gong_label'], bg['palace_wx'],
                      r['ben_gua']['palace']))
        out.append('  '.join([pad('爻位', 4), pad('卦形', 6),
                              pad('变卦 六亲纳甲五行', 20),
                              pad('世应', 4), pad('动', 2), pad('空', 2)]))
        for i in range(5, -1, -1):
            bl = bg['lines'][i]
            out.append('  '.join([
                pad(POS_LABEL[bl['pos']], 4),
                pad(YANG_BAR if bl['yang'] else YIN_BAR, 6),
                pad('%s%s%s' % (bl['liuqin'], bl['najia'], bl['wuxing']), 20),
                pad('世' if bl['shi'] else ('应' if bl['ying'] else ''), 4),
                pad('动' if bl['dong'] else '', 2),
                pad('空' if bl['kong'] else '', 2)]))
    return '\n'.join(out)


# ---------- 论坛装卦表解析 ----------
QUAN_NAMES = ['父母', '兄弟', '子孙', '妻财', '官鬼']


def parse_zhuangguabiao(text):
    """解析元亨利贞网标准装卦表文本（含卦宫、六神、纳甲六亲、世应、动爻、变卦）"""
    t = text or ''
    out = {'raw_time': None, 'ben': None, 'bian': None, 'lines': []}
    m = re.search(r'干支[：:]\s*(\S+?)\s*年\s*(\S+?)\s*月\s*(\S+?)\s*日\s*(\S+?)\s*时', t)
    if m:
        out['raw_time'] = [m.group(i) for i in range(1, 5)]
    gong_hits = re.findall(r'([乾坤震巽坎离艮兑])宫[：:]\s*([\u4e00-\u9fa5]{2,4})', t)
    if gong_hits:
        out['ben'] = {'palace': gong_hits[0][0], 'name': gong_hits[0][1]}
    if len(gong_hits) > 1:
        out['bian'] = {'palace': gong_hits[1][0], 'name': gong_hits[1][1]}
    for ln in t.splitlines():
        ln = ln.strip()
        if not re.match(r'^(青龙|朱雀|勾陈|螣蛇|白虎|玄武)', ln):
            continue
        ls = ln[:2]
        m2 = re.search(r'(' + '|'.join(QUAN_NAMES) + r')([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥])([水火木金土])', ln)
        if not m2:
            continue
        first_yx = ln.find('▅')
        tail = ln[first_yx:] if first_yx >= 0 else ''
        yang = tail.startswith('▅▅▅▅▅') if tail else None
        # 世应/动爻只看本卦栏（变卦栏在 → 之后）
        arrow = tail.find('→')
        ben_tail = tail[:arrow] if arrow >= 0 else tail
        out['lines'].append({
            'liushen': ls, 'liuqin': m2.group(1), 'najia': m2.group(2) + m2.group(3),
            'wuxing': m2.group(4), 'yang': yang,
            'shi_ying': '世' if '世' in ben_tail else ('应' if '应' in ben_tail else ''),
            'dong': ('○' in ben_tail or 'O' in ben_tail or '→' in tail),
        })
    # 文本自上而下为六爻→初爻，统一反转为初爻→六爻，与其余输出一致
    out['lines'].reverse()
    return out


GUA_NAME_REV = {v: k for k, v in GUA_NAME.items()}


def validate_parsed(parsed):
    """校验解析出的卦表。三层：宫位自洽、纳甲逐爻、六亲归属。

    只校验六亲是不够的——若干支装错但五行相同（如丁酉误作己酉），
    六亲仍然一致，错误会被漏掉，故必须逐爻比对纳甲。"""
    problems = []
    ben = parsed.get('ben')
    if not ben:
        return {'ok': False, 'problems': [{'error': '未解析出卦宫/卦名'}]}
    if ben['palace'] not in PALACE_WX:
        return {'ok': False, 'problems': [{'error': '宫名无法识别：%s' % ben['palace']}]}
    gong_wx = PALACE_WX[ben['palace']]
    lines = parsed['lines']
    ref_nj = None
    pair = GUA_NAME_REV.get(ben['name'])
    if pair is None:
        problems.append({'kind': '卦名', 'error': '不在六十四卦标准名内：%s' % ben['name']})
    else:
        upper, lower = pair
        info = GUA64.get(PURE_GUA[lower][0:3] + PURE_GUA[upper][3:6])
        if info and info['palace'] != ben['palace']:
            problems.append({'kind': '宫位', 'error': '文本标 %s宫，标准为 %s宫'
                                                     % (ben['palace'], info['palace'])})
        ref_nj = najia_of(lower, upper)
    for i, l in enumerate(lines):
        if ref_nj is not None and i < len(ref_nj):
            want = ref_nj[i][0] + ref_nj[i][1]
            if l['najia'] != want:
                problems.append({'pos': i + 1, 'kind': '纳甲',
                                 'parsed': l['najia'], 'expect': want})
        expect = liuqin(gong_wx, l['najia'][1])
        if expect != l['liuqin']:
            problems.append({'pos': i + 1, 'kind': '六亲', 'najia': l['najia'],
                             'parsed': l['liuqin'], 'expect': expect})
    return {'ok': not problems, 'problems': problems}


def self_test(out_path=None):
    ok = True
    checks = []
    # 进入本轮自检前，环境里已经加载了哪些网络模块。收尾时比对，用来证明
    # 本程序自身没有引入网络能力（不与环境已有的加载状态混为一谈）。
    _net_before = set(m for m in ('urllib.request', 'http.client', 'ssl') if m in sys.modules)

    def chk(cond, msg):
        nonlocal ok
        checks.append(('OK ' if cond else 'FAIL ') + msg)
        if not cond:
            ok = False

    chk(len(GUA64) == 64, '64 卦表生成唯一（%d 条）' % len(GUA64))
    chk(GUA64['100101']['name'] == '火雷噬嗑' and GUA64['100101']['palace'] == '巽'
        and GUA64['100101']['shi'] == 5, '火雷噬嗑 = 巽宫五世')
    chk(GUA64['000101']['name'] == '火地晋' and GUA64['000101']['palace'] == '乾'
        and GUA64['000101']['gong_label'] == '游魂', '火地晋 = 乾宫游魂')
    chk(day_ganzhi(2026, 9, 14) == '辛卯', '2026-09-14 日柱 = 辛卯')
    chk(day_ganzhi(1958, 10, 9) == '己未', '1958-10-09 日柱 = 己未')
    chk(xunkong('辛卯') == ['午', '未'], '辛卯日旬空 = 午未')
    chk(hour_ganzhi('辛', 12) == '甲午', '辛日午时 = 甲午')
    chk(hour_ganzhi('戊', 12) == '戊午', '戊日午时 = 戊午')
    chk(liuqin('木', '巳') == '子孙' and liuqin('木', '酉') == '官鬼'
        and liuqin('木', '未') == '妻财', '巽宫木：巳=子孙 酉=官鬼 未=妻财')
    chk(liuqin('金', '子') == '子孙' and liuqin('金', '午') == '官鬼'
        and liuqin('金', '卯') == '妻财', '兑/乾宫金：子=子孙 午=官鬼 卯=妻财')

    r = zhuanggua('100101', [1], '丙午', '丁酉', '庚辰', '庚辰', ['申', '酉'])
    l0 = r['lines'][0]
    chk(l0['najia'] == '庚子' and l0['liuqin'] == '父母' and l0['liushen'] == '白虎',
        '火雷噬嗑初爻 = 庚子父母·白虎（庚日初爻起白虎）')
    chk(r['lines'][1]['najia'] == '庚寅' and r['lines'][1]['liuqin'] == '兄弟',
        '噬嗑二爻 = 庚寅兄弟（应）')
    chk(r['lines'][2]['najia'] == '庚辰' and r['lines'][2]['liuqin'] == '妻财',
        '噬嗑三爻 = 庚辰妻财')
    chk(r['lines'][3]['najia'] == '己酉' and r['lines'][3]['liuqin'] == '官鬼',
        '噬嗑四爻 = 己酉官鬼')
    chk(r['lines'][5]['najia'] == '己巳' and r['lines'][5]['liuqin'] == '子孙',
        '噬嗑六爻 = 己巳子孙')
    chk(r['ben_gua']['shi_pos'] == 5 and r['lines'][4]['shi'], '噬嗑世在五爻')
    chk(r['ben_gua']['ying_pos'] == 2 and r['lines'][1]['ying'], '噬嗑应在二爻')
    chk(GUA64['011101']['name'] == '火风鼎' and GUA64['011101']['shi'] == 2
        and GUA64['011101']['ying'] == 5, '火风鼎 = 离宫二世（世二应五）')
    chk(GUA64['010010']['name'] == '坎为水' and GUA64['010010']['shi'] == 6
        and GUA64['010010']['ying'] == 3, '坎为水 = 坎宫本宫（世六应三）')
    chk(GUA64['001100']['shi'] == 4 and GUA64['001100']['ying'] == 1,
        '雷山小过 = 兑宫游魂（世四应初）')
    chk(GUA64['010110']['name'] == '泽水困' and GUA64['010110']['shi'] == 1
        and GUA64['010110']['ying'] == 4, '泽水困 = 兑宫一世（世初应四）')
    t3 = resolve_time(argparse.Namespace(ganzhi=None, date='2026-09-14 12:45'))
    chk(t3[0] == '丙午' and t3[1] == '丁酉' and t3[2] == '辛卯' and t3[3] == '甲午',
        '公历 2026-09-14 12:45 → 丙午年 丁酉月 辛卯日 甲午时')
    t4 = resolve_time(argparse.Namespace(ganzhi=None, date='2026-01-10 03:00'))
    chk(t4[1] == '己丑', '2026-01-10（小寒后）→ 月柱己丑')
    t5 = resolve_time(argparse.Namespace(ganzhi=None, date='2026-01-03 03:00'))
    chk(t5[0] == '乙巳' and t5[1] == '戊子', '2026-01-03（立春前）→ 年柱乙巳、月柱戊子')
    # 节气按【时刻】判定：2026 立春在 2 月 4 日 04:01
    t6 = resolve_time(argparse.Namespace(ganzhi=None, date='2026-02-04 03:00'))
    chk(t6[0] == '乙巳' and t6[1] == '己丑', '立春前 1 小时（02-04 03:00）→ 仍属乙巳年丑月')
    t7 = resolve_time(argparse.Namespace(ganzhi=None, date='2026-02-04 05:00'))
    chk(t7[0] == '丙午' and t7[1] == '庚寅', '立春后 1 小时（02-04 05:00）→ 丙午年寅月')
    # 子时归次日（通行口径）
    t8 = resolve_time(argparse.Namespace(ganzhi=None, date='2026-01-01 23:30'))
    chk(t8[2] == day_ganzhi(2026, 1, 2) and t8[3] == '戊子',
        '23:30 起卦 → 日柱推进到次日丙子、时柱戊子（与寿星历一致）')
    t9 = resolve_time(argparse.Namespace(ganzhi=None, date='2026-01-01 22:30'))
    chk(t9[2] == day_ganzhi(2026, 1, 1) and t9[3] == '丁亥',
        '22:30 起卦 → 日柱仍为当日乙亥、时柱丁亥')
    t10 = resolve_time(argparse.Namespace(ganzhi=None, date='2026-01-02 00:30'))
    chk(t10[2] == t8[2] and t10[3] == t8[3],
        '23:30 与次日 00:30 同属子时，四柱应一致')
    # 节气表完整性
    chk(len(JIEQI_B36) == (JIEQI_LAST_YEAR - JIEQI_FIRST_YEAR + 1) * 48,
        '节气表长度应为 %d 位（实际 %d）'
        % ((JIEQI_LAST_YEAR - JIEQI_FIRST_YEAR + 1) * 48, len(JIEQI_B36)))
    jm1900, ok1900 = jieqi_minute(1900, '小寒')
    chk(ok1900 and jm1900 == 5 * 1440 + 2 * 60 + 3, '1900 小寒 = 1 月 6 日 02:03')
    jm2026, ok2026 = jieqi_minute(2026, '立春')
    chk(ok2026 and jm2026 == 34 * 1440 + 4 * 60 + 1, '2026 立春 = 2 月 4 日 04:01')
    rb = zhuanggua('100101', [1], '丙午', '丁酉', '庚辰', '庚辰', ['申', '酉'])
    chk(rb['bian_gua']['changed'][0]['to'] == '乙未'
        and rb['bian_gua']['changed'][0]['to_liuqin'] == '妻财',
        '噬嗑初爻动化乙未 → 按本卦巽宫定六亲为妻财')

    r2 = zhuanggua('010101', [5], '丙午', '丁酉', '辛卯', '甲午', ['午', '未'])
    chk(r2['ben_gua']['name'] == '火水未济' and r2['ben_gua']['palace'] == '离'
        and r2['ben_gua']['shi_pos'] == 3, '火水未济 = 离宫三世（世三应六）')
    chk(r2['bian_gua']['name'] == '天水讼', '未济五爻动 → 天水讼')
    chk(r2['lines'][3]['najia'] == '己酉' and r2['lines'][3]['liuqin'] == '妻财'
        and r2['lines'][3]['kong'] is False, '未济四爻 = 己酉妻财（不空）')

    r3 = zhuanggua('001100', [1, 2, 5], '丙午', '丁酉', '辛卯', '甲午', ['午', '未'])
    chk(r3['ben_gua']['name'] == '雷山小过' and r3['ben_gua']['palace'] == '兑'
        and r3['ben_gua']['gong_label'] == '游魂', '雷山小过 = 兑宫游魂（世四应初）')
    chk(r3['bian_gua']['name'] == '泽天夬', '小过初/二/五爻动 → 泽天夬')
    chk(GUA64['101111']['name'] == '天火同人' and GUA64['101111']['palace'] == '离'
        and GUA64['101111']['gong_label'] == '归魂', '天火同人 = 离宫归魂')
    chk(GUA64['111101']['name'] == '火天大有' and GUA64['111101']['gong_label'] == '归魂',
        '火天大有 = 乾宫归魂')
    chk(GUA64['100110']['name'] == '泽雷随' and GUA64['100110']['palace'] == '震'
        and GUA64['100110']['gong_label'] == '归魂', '泽雷随 = 震宫归魂')
    chk(any(f['liuqin'] == '妻财' and f['najia'] == '丁卯' for f in r3['fushen']),
        '小过缺妻财，伏神 = 丁卯（兑宫首卦二爻）')

    # ---- 输入写法宽容性（依评测建议新增：卦名直输与会话式写法）----
    same = [('上离下巽', '011101'), ('上卦为离，下卦为巽', '011101'),
            ('离上巽下', '011101'), ('上火下风', '011101'),
            ('火风鼎', '011101'), ('火风鼎卦', '011101'),
            ('鼎', '011101'), ('011101', '011101'),
            ('  上离下巽  ', '011101'), ('上 卦 为 离 下 卦 为 巽', '011101')]
    bad = []
    for text, want in same:
        try:
            got, _ = parse_gua_arg(text, None)
        except SystemExit:
            got = None
        if got != want:
            bad.append('%s → %s' % (text, got))
    chk(not bad, '同一卦十种写法解析一致（%d 处不一致：%s）' % (len(bad), '；'.join(bad) or '无'))

    bad = []
    for code, info in GUA64.items():
        for text in (info['name'], '上%s下%s' % (info['upper'], info['lower'])):
            try:
                got, _ = parse_gua_arg(text, None)
            except SystemExit:
                got = None
            if got != code:
                bad.append('%s→%s' % (text, got))
    chk(not bad, '六十四卦逐个直输（卦名 / 上X下Y 两路共 128 例）全部还原原位序（%d 处不一致）'
        % len(bad))

    chk(GUA_SHORT.get('噬嗑') == ('离', '震') and GUA_SHORT.get('小过') == ('震', '艮')
        and GUA_SHORT.get('大过') == ('兑', '巽'),
        '卦名简称索引：噬嗑=离上震下、小过=震上艮下、大过=兑上巽下')
    chk(GUA_SHORT.get('鼎') == ('离', '巽') and GUA_SHORT.get('讼') == ('乾', '坎')
        and GUA_SHORT.get('姤') == ('乾', '巽'),
        '单字简称：鼎=离上巽下、讼=乾上坎下、姤=乾上巽下')
    chk(all(len(k) <= 2 for k in GUA_SHORT),
        '简称长度不超过两字、互不冲突（共收录 %d 个）' % len(GUA_SHORT))
    chk('天' not in GUA_SHORT and '地' not in GUA_SHORT and '火' not in GUA_SHORT,
        '经卦别名不进入简称索引（避免「天」兼指乾卦与乾为天）')
    bad = []
    for k in GUA_SHORT:
        try:
            parse_gua_arg(k, None)
        except SystemExit:
            bad.append(k)
    chk(not bad, '全部 %d 个简称均可解析（失败：%s）' % (len(GUA_SHORT), '、'.join(bad) or '无'))

    bad = []
    for text in ('上离下猫', '上离下', '天风姤的卦', '火风鼎鼎', '1111', '随便什么'):
        try:
            parse_gua_arg(text, None)
            bad.append(text)
        except SystemExit:
            pass
    chk(not bad, '无法识别的输入一律报错、不猜测（漏报：%s）' % ('、'.join(bad) or '无'))

    chk(parse_dong_arg('5') == [5] and parse_dong_arg('1,2,5') == [1, 2, 5]
        and parse_dong_arg('') == [], '动爻解析：5 / 1,2,5 / 留空为静卦')
    chk(parse_dong_arg('5,5,2') == [2, 5], '动爻重复输入自动去重（5,5,2 → 2,5）')
    bad = []
    for text in ('7', '0', '1,7', '10'):
        try:
            parse_dong_arg(text)
            bad.append(text)
        except SystemExit:
            pass
    chk(not bad, '动爻越界一律报错（漏报：%s）' % ('、'.join(bad) or '无'))

    # ---- 变卦完整卦形（依评测建议新增）----
    bg2 = r2['bian_gua']
    binfo2 = GUA64[bg2['code']]
    chk(bg2['lower'] == binfo2['lower'] and bg2['upper'] == binfo2['upper']
        and bg2['palace_wx'] == PALACE_WX[binfo2['palace']],
        '变卦含完整卦形：上下经卦与宫位五行同 64 卦表')
    chk(bg2['shi_pos'] == binfo2['shi'] and bg2['ying_pos'] == binfo2['ying'],
        '变卦含世应位置（%s：世%d爻 应%d爻）' % (bg2['name'], bg2['shi_pos'], bg2['ying_pos']))
    chk(len(bg2['lines']) == 6
        and all('yang' in l and 'shi' in l and 'ying' in l and 'kong' in l and 'dong' in l
                for l in bg2['lines']),
        '变卦逐爻含阴阳／世应／旬空／动爻字段（6 爻齐全）')
    diff = [i + 1 for i in range(6) if bg2['lines'][i]['yang'] != r2['lines'][i]['yang']]
    chk(diff == r2['dong'], '变卦与本卦仅动爻处阴阳不同（差异位 %s）' % diff)
    chk(all(bg2['lines'][i]['yang'] == (bg2['code'][i] == '1') for i in range(6)),
        '变卦爻位阴阳与其位序字符串自洽')
    chk(all(l['liuqin'] == liuqin(r2['ben_gua']['palace_wx'], l['zhi']) for l in bg2['lines']),
        '变卦六亲按本卦宫定（%s宫）' % r2['ben_gua']['palace'])

    sample = """干支：乙巳年　甲申月　辛酉日　戊子时　　（日空：子丑）
　　 　　　　　　　巽宫：火雷噬嗑 　　 　 　乾宫：火地晋 (游魂)　
螣蛇 　　　　　 子孙己巳火 ▅▅▅▅▅ 　 　　 子孙己巳火 ▅▅▅▅▅ 　
勾陈 　　　　　 妻财己未土 ▅▅　▅▅ 世 　　妻财己未土 ▅▅　▅▅ 　
朱雀 　　　　　 官鬼己酉金 ▅▅▅▅▅ 　 　　 官鬼己酉金 ▅▅▅▅▅ 　
青龙 　　　　　 妻财庚辰土 ▅▅　▅▅ 　 　　兄弟乙卯木 ▅▅　▅▅ 　
玄武 　　　　　 兄弟庚寅木 ▅▅　▅▅ 应 　　子孙乙巳火 ▅▅　▅▅ 　
白虎 　　　　　 父母庚子水 ▅▅▅▅▅ 　 ○→ 妻财乙未土 ▅▅　▅▅ 应"""
    parsed = parse_zhuangguabiao(sample)
    v = validate_parsed(parsed)
    chk(parsed['ben']['name'] == '火雷噬嗑' and parsed['bian']['name'] == '火地晋',
        '解析论坛装卦表：本卦火雷噬嗑 / 变卦火地晋')
    chk(v['ok'], '论坛装卦表六亲校验通过')
    chk(parsed['lines'][0]['dong'] is True, '论坛装卦表：初爻动识别为动爻')

    # --- 六冲／六合判定（2026-09-17 依评家建议新增） ---
    def _zhi_lines(_code):
        _info = GUA64[_code]
        _nj = najia_of(_info['lower'], _info['upper'])
        return [{'pos': i + 1, 'zhi': _nj[i][1]} for i in range(6)]

    def _code_of_name(_nm):
        return [c for c, i in GUA64.items() if i['name'] == _nm][0]

    _chong = sorted(i['name'] for c, i in GUA64.items() if chonghe_of(_zhi_lines(c)) == '六冲卦')
    _he = sorted(i['name'] for c, i in GUA64.items() if chonghe_of(_zhi_lines(c)) == '六合卦')
    chk(_chong == sorted(['乾为天', '兑为泽', '离为火', '震为雷', '巽为风',
                          '坎为水', '艮为山', '坤为地', '天雷无妄', '雷天大壮']),
        '六冲卦恰为八纯卦加无妄、大壮共十卦（实得 %d 卦）' % len(_chong))
    chk(_he == sorted(['地天泰', '天地否', '雷地豫', '地雷复',
                       '火山旅', '山火贲', '水泽节', '泽水困']),
        '六合卦恰为泰否豫复旅贲节困八卦（实得 %d 卦）' % len(_he))
    chk(chonghe_of(_zhi_lines(_code_of_name('乾为天'))) == '六冲卦'
        and chonghe_of(_zhi_lines(_code_of_name('地天泰'))) == '六合卦'
        and chonghe_of(_zhi_lines(_code_of_name('火风鼎'))) == '',
        '六冲／六合逐卦抽查：乾为天＝六冲、地天泰＝六合、火风鼎＝皆非')
    _rj = zhuanggua(_code_of_name('乾为天'), [], '丙午', '丁酉', '戊子', '戊午', ['午', '未'])
    chk(_rj['ben_gua'].get('chonghe') == '六冲卦',
        'JSON 结果含 chonghe 字段（乾为天＝六冲卦）')
    _txt3 = render_text(r3)
    chk(any(ln.startswith('爻位') and '伏神' in ln for ln in _txt3.splitlines()),
        '文本爻表新增「伏神」列表头')
    chk(any('妻财丁卯' in ln and not ln.startswith('伏神：') for ln in _txt3.splitlines()),
        '伏神「妻财丁卯」标进对应爻行，不再只在表外单列')

    # ------------------------------------------------------------------
    # 以下为可选解读层的断言。核心是把三件事钉死：默认路径不碰网络、
    # 密钥任何场合不外泄、失败一律降级而不影响卦表。
    # ------------------------------------------------------------------
    _net_after = set(m for m in ('urllib.request', 'http.client', 'ssl') if m in sys.modules)
    chk(_net_after == _net_before,
        '默认路径不加载网络功能模块（自检前后一致：%s）'
        % ('均为空' if not _net_before else '、'.join(sorted(_net_before))))

    _src = ''
    try:
        with open(__file__, encoding='utf-8') as _f:
            _src = _f.read()
    except Exception:
        _src = ''
    if _src:
        chk(not re.search(r'^(import|from)\s+(urllib|socket|http)\b', _src, re.M),
            '模块顶层未导入任何网络模块（网络仅在函数内部延迟导入）')
        chk(re.search(r'^\s+import urllib\.request\b', _src, re.M) is not None,
            '网络模块在 call_llm 内部延迟导入，默认路径无从触发')
        chk('不得给出吉凶结论' in _src and '不得给出行动建议' in _src
            and '不得预测应期' in _src,
            '提示词含三条硬约束：禁吉凶、禁建议、禁应期')
        chk('以上仅为卦象结构梳理，不含吉凶判断' in LLM_SYSTEM_PROMPT,
            '提示词要求末行固定声明不含吉凶判断')
        chk('api_key' not in LLM_SYSTEM_PROMPT and '密钥' not in LLM_SYSTEM_PROMPT,
            '提示词不提密钥字样，避免诱导模型输出凭据相关内容')

    # 自检夹具：形似密钥的假值，仅用于验证掩码逻辑，不是凭据。
    # 刻意用拼接构造，避免被平台的密钥扫描误报为真实凭据。
    _k = 'sk' + '-abcdef1234567890XYZ'
    chk(_k not in llm_mask(_k) and llm_mask(_k).startswith('sk-ab'),
        '密钥掩码：完整密钥不出现在掩码结果中')
    chk(llm_mask('') == '（未设置）' and llm_mask(None) == '（未设置）',
        '未设置密钥时掩码显示「未设置」，不抛异常')
    chk(set(llm_mask('short123')) == {'*'},
        '短密钥整体以星号遮蔽，不泄露任何字符')

    chk(llm_ready(dict(base='', need_key=True, key=''))[0] is False,
        '接口地址为空时判定不可调用')
    chk(llm_ready(dict(base='http://x', need_key=True, key=''))[0] is False,
        '需密钥的服务商缺密钥时判定不可调用')
    chk(llm_ready(dict(base='http://x', need_key=False, key=''))[0] is True,
        '本机服务商（Ollama）无需密钥即判定可调用')

    _pl = build_llm_payload({'ben_gua': {'name': '火风鼎'}, 'lines': []}, '问这桩生意')
    chk('火风鼎' in _pl and '问这桩生意' in _pl and '```json' in _pl,
        '提问内容含卦表 JSON 与所问之事')
    chk('无法确定用神' in build_llm_payload({'ben_gua': {'name': '火风鼎'}}, None),
        '未填所问之事时，要求模型照实说明无法确定用神')

    _ns = lambda **kw: argparse.Namespace(llm_provider=kw.get('p'), llm_model=None,
                                          llm_base=None, llm_key=None,
                                          llm_timeout=kw.get('t'), llm_max_tokens=None)
    _c1, _ = llm_resolve(_ns(p='ollama'))
    chk(_c1['provider'] == 'ollama' and _c1['model'] == LLM_PROVIDERS['ollama']['model']
        and _c1['need_key'] is False,
        '未指定模型时取该服务商的预设模型，并带出免密钥属性')

    _old_env = os.environ.get(LLM_ENV['provider'])
    os.environ[LLM_ENV['provider']] = 'zhipu'
    try:
        _c2, _ = llm_resolve(_ns(p='ollama'))
        chk(_c2['provider'] == 'ollama' and _c2['src']['provider'] == '命令行',
            '配置优先级：命令行覆盖环境变量')
        _c3, _ = llm_resolve(_ns())
        chk(_c3['provider'] == 'zhipu' and _c3['src']['provider'] == '环境变量',
            '配置优先级：命令行留空时取环境变量')
        _c4, _n4 = llm_resolve(_ns(p='不存在的服务商'))
        chk(_c4['provider'] == LLM_DEFAULT_PROVIDER and any('未识别' in x for x in _n4),
            '服务商名不认识时回落默认值并给出提醒')
    finally:
        if _old_env is None:
            os.environ.pop(LLM_ENV['provider'], None)
        else:
            os.environ[LLM_ENV['provider']] = _old_env

    _c5, _n5 = llm_resolve(_ns(p='ollama', t=1))
    chk(_c5['timeout'] == 5 and any('过短' in x for x in _n5),
        '超时秒数过小时抬到下限并给出提醒')

    chk(_llm_api_error_text('{"error":{"message":"invalid key"}}') == 'invalid key',
        '接口错误描述可解析为可读说明')
    chk(_llm_api_error_text('') == '', '错误描述为空时不抛异常')

    _cfg_t = dict(provider='x', provider_name='某服务商', style='openai', base='http://x',
                  model='m', key='kkkkkkkkkkkk', need_key=True, timeout=60, max_tokens=2048,
                  src=dict(provider='a', model='b', base='c', key='d'))
    _sec = render_llm_section('测试内容', _cfg_t, None)
    chk('第二部分' in _sec and '不是本工具的计算结果' in _sec and '测试内容' in _sec,
        '解读段标注来源，并声明非本工具计算结果')
    _sec_c = render_llm_section(None, _cfg_t, '测试错误', kind='config')
    chk('测试错误' in _sec_c and '三种配置方式' in _sec_c,
        '未配置时给出配置指引')
    _sec_t = render_llm_section(None, _cfg_t, '测试错误', kind='trouble')
    chk('测试错误' in _sec_t and '逐项排查' in _sec_t and '三种配置方式' not in _sec_t,
        '已配置但失败时给出排错指引，不再重复配置指引')
    _dry = render_llm_section('预览内容', _cfg_t, None, dry=True)
    chk('预演模式' in _dry and '并未外发' in _dry and '预览内容' in _dry,
        '预演模式明确标注本次未外发')
    chk('kkkkkkkkkkkk' not in _dry and 'kkkkkkkkkkkk' not in _sec,
        '预演与解读段中密钥均以掩码显示')
    _fake_k2 = 'sk' + '-SECRETSECRET1234'   # 同上：拼接构造的假值夹具
    _doc = render_llm_doctor(dict(_cfg_t, key=_fake_k2), [])
    chk(_fake_k2 not in _doc, '配置体检输出不泄露完整密钥')
    _bd = render_llm_boundary()
    chk('不提供吉凶判断' in _bd and 'Ollama' in _bd,
        '边界说明含禁吉凶与本地模型两条要点')

    report = '\n'.join(checks) + '\n\n自检结果：' + ('全部通过' if ok else '存在失败项')
    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(report + '\n')
        print('自检报告已写入：' + out_path)
    else:
        print(report)
    return 0 if ok else 1


# ===================================================================
# 可选增强层：接入使用者自己的大模型，做卦象要点梳理
#
# 设计原则（三条，缺一不可）：
#   1. 默认关闭。不带 --llm 时，上面的卦表计算路径一字不变，
#      不加载任何网络模块、不读取任何配置文件、不产生任何外发请求。
#   2. 密钥只在内存中使用。不写入输出、不写入日志、不写入卦表结果，
#      任何展示场合一律以掩码形式出现。
#   3. 失败一律优雅降级。没有密钥、网络不通、接口报错，卦表照常输出，
#      解读段如实写明失败原因，绝不静默、绝不编造内容填补。
#
# 边界：本层产出的是「卦象结构梳理」，不是吉凶判断。提示词中对吉凶类
#       表述作了硬性禁止，输出段落亦与卦表物理隔开、标注来源。
# ===================================================================

LLM_SEC = '=' * 66

# 内置服务商预设。style='openai' 走 /chat/completions 兼容格式（绝大多数国产模型
# 与本地推理框架都支持），style='anthropic' 走 Anthropic 自有格式。
LLM_PROVIDERS = {
    'deepseek': dict(name='深度求索 DeepSeek', style='openai',
                     base='https://api.deepseek.com/v1', model='deepseek-chat', need_key=True),
    'siliconflow': dict(name='硅基流动', style='openai',
                        base='https://api.siliconflow.cn/v1', model='Qwen/Qwen3-8B', need_key=True),
    'dashscope': dict(name='阿里云通义千问', style='openai',
                      base='https://dashscope.aliyuncs.com/compatible-mode/v1',
                      model='qwen-plus', need_key=True),
    'moonshot': dict(name='月之暗面 Kimi', style='openai',
                     base='https://api.moonshot.cn/v1', model='moonshot-v1-8k', need_key=True),
    'zhipu': dict(name='智谱 GLM', style='openai',
                  base='https://open.bigmodel.cn/api/paas/v4', model='glm-4-flash', need_key=True),
    'openai': dict(name='OpenAI', style='openai',
                   base='https://api.openai.com/v1', model='gpt-4o-mini', need_key=True),
    'anthropic': dict(name='Anthropic Claude', style='anthropic',
                      base='https://api.anthropic.com/v1', model='claude-sonnet-4-5', need_key=True),
    'ollama': dict(name='本机 Ollama', style='openai',
                   base='http://localhost:11434/v1', model='qwen2.5:7b', need_key=False),
}
LLM_DEFAULT_PROVIDER = 'deepseek'

LLM_ENV = dict(key='LIUYAO_LLM_KEY', provider='LIUYAO_LLM_PROVIDER',
               model='LIUYAO_LLM_MODEL', base='LIUYAO_LLM_BASE',
               timeout='LIUYAO_LLM_TIMEOUT')

# 提示词是本层的核心资产。三条硬约束写在最前面：不得给吉凶、不得给建议、
# 不得预测应期；并强制只准引用卦表内已有信息，不得引入盘外内容。
LLM_SYSTEM_PROMPT = """你是一名六爻卦象结构梳理助手，服务于《增删卜易》体系的京房纳甲法。

【你的任务】
使用者会给你一张已由程序装好的卦表，内含八宫归属、世爻应爻、纳甲干支、地支五行、六亲、六神、伏神、变卦、旬空、六冲六合。你的工作是把这张卦表内部的五行与六亲关系梳理清楚，让人看明白这一盘的结构。

【必须做到】
1. 只使用卦表中已给出的信息。干支、五行、六亲、世应、旬空、伏神一律以卦表为准，不得改动，不得补充卦表之外的卦象。
2. 凡涉及生克，一律写明推算依据，格式如「用神酉金，日辰午火，火克金」。
3. 专业术语首次出现时，紧跟一句白话解释，例如「用神——即所问之事在卦中对应的那一爻」。
4. 使用简体中文书面语，分条陈述，不要写成分段散文，不要出现英文单词。
5. 卦表是一手依据。若卦表中某项为空或未提供，直接写明「卦表未提供」，不得推测。

【绝对禁止】
1. 不得给出吉凶结论。禁止出现「吉」「凶」「大吉」「不利」「凶险」「顺利」「凶多吉少」这类判断词。
2. 不得给出行动建议。禁止「建议您」「应当」「不宜」「可以放心」「最好」这类表述。
3. 不得预测应期或时间应验。禁止「某月会有变化」「近期会见效」「逢某日」这类预测。
4. 不得引入卦表以外的人、事、物、时间、方位等信息。
5. 不得对使用者的处境作任何评价或安慰。

【输出结构】
按下列六节输出。某一节在本盘无对应情形时，写明「本盘无此情形」，不要跳过不写。

一、用神取法
依所问之事取哪一爻为用神，说明取法依据。若使用者未说明所问之事，写明无法确定用神，并列出常见的用神对应关系（问财取妻财、问工作取官鬼、问文书取父母、问子女取子孙、问同辈与合伙取兄弟）供其参考。

二、用神状态
写出用神所临干支与五行，以及用神与月建、日辰各自的五行关系（生、克、比和、泄、耗）。只陈述关系本身，不作强弱评价。

三、动变分析
逐条列出每个动爻变前变后的干支与六亲，说明两者之间的五行关系。

四、世应关系
世爻与应爻分别所临的干支五行，以及两者之间的关系。

五、伏神与旬空
本卦哪些六亲不现、各伏于何爻之下；旬空落在哪几爻。

六、需人工核对之处
指出盘面中需要使用者自行判断或另行查证的部分。

【末行固定输出】
以上仅为卦象结构梳理，不含吉凶判断，不能作为任何决策依据。
"""


def llm_cfg_path():
    """配置文件的放置位置：使用者主目录下的 .liuyao/config.json"""
    return os.path.join(os.path.expanduser('~'), '.liuyao', 'config.json')


def llm_read_file():
    """读配置文件。不存在返回空字典；损坏时把原因带出来，不静默吞掉。"""
    p = llm_cfg_path()
    if not os.path.isfile(p):
        return {}, None
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return {}, '配置文件 %s 的内容不是对象（应为 JSON 对象），已忽略。' % p
        return d, None
    except Exception as e:
        return {}, '配置文件 %s 解析失败（%s），已忽略。' % (p, e)


def llm_mask(key):
    """密钥掩码。任何展示场合都用它，避免密钥出现在截图、日志与聊天记录里。"""
    if not key:
        return '（未设置）'
    k = str(key).strip()
    if len(k) <= 8:
        return '*' * len(k)
    return '%s……%s（共 %d 位）' % (k[:5], k[-3:], len(k))


def llm_resolve(args):
    """汇总配置。

    优先级：命令行参数 > 环境变量 > 配置文件 > 内置预设默认值。
    返回 (cfg, notes)：notes 是需要提醒使用者的问题清单，不含密钥内容。
    """
    f, err = llm_read_file()
    notes = []
    if err:
        notes.append(err)

    def pick(cli_name, env_name, file_name, default=None):
        v = getattr(args, cli_name, None)
        if v:
            return str(v).strip(), '命令行'
        v = os.environ.get(env_name, '').strip()
        if v:
            return v, '环境变量'
        v = f.get(file_name)
        if v:
            return str(v).strip(), '配置文件'
        return default, '默认值'

    provider, prov_src = pick('llm_provider', LLM_ENV['provider'], 'provider', LLM_DEFAULT_PROVIDER)
    provider = (provider or LLM_DEFAULT_PROVIDER).lower()
    if provider not in LLM_PROVIDERS:
        notes.append('未识别的服务商「%s」，可用值见 --llm-doctor，本次按 %s 处理。'
                     % (provider, LLM_DEFAULT_PROVIDER))
        provider = LLM_DEFAULT_PROVIDER
    preset = LLM_PROVIDERS[provider]

    key, key_src = pick('llm_key', LLM_ENV['key'], 'api_key')
    model, model_src = pick('llm_model', LLM_ENV['model'], 'model', preset['model'])
    base, base_src = pick('llm_base', LLM_ENV['base'], 'base_url', preset['base'])

    timeout = getattr(args, 'llm_timeout', None) or os.environ.get(LLM_ENV['timeout'], '')
    try:
        timeout = int(timeout) if str(timeout).strip() else 60
    except ValueError:
        notes.append('超时时间「%s」不是整数，已按 60 秒处理。' % timeout)
        timeout = 60
    if timeout < 5:
        timeout = 5
        notes.append('超时时间过短，已按最低 5 秒处理。')

    cfg = dict(provider=provider, provider_name=preset['name'], style=preset['style'],
               base=base.rstrip('/'), model=model, key=key or '',
               need_key=preset['need_key'], timeout=timeout,
               max_tokens=int(getattr(args, 'llm_max_tokens', None) or 2048),
               src=dict(provider=prov_src, model=model_src, base=base_src, key=key_src))
    return cfg, notes


def llm_ready(cfg):
    """检查是否具备调用条件。返回 (可调用, 缺失说明)。"""
    if not cfg['base']:
        return False, '未指定接口地址（--llm-base）'
    if cfg['need_key'] and not cfg['key']:
        return False, '未提供密钥'
    return True, None


def llm_config_hint(cfg):
    """没配好密钥时给出的照做步骤。措辞求具体，不泛泛而谈。"""
    p = llm_cfg_path()
    return '\n'.join([
        '  本段需要您自备一个大模型接口的密钥，本工具不提供、不代付、不转发。',
        '',
        '  三种配置方式，任选一种：',
        '    一、命令行临时指定（当次生效，不落盘）：',
        '        --llm-key "您的密钥"',
        '    二、设环境变量（当次会话生效）：',
        '        set %s=您的密钥        （Windows 命令提示符）' % LLM_ENV['key'],
        '        export %s=您的密钥     （macOS / Linux）' % LLM_ENV['key'],
        '    三、写配置文件（长期生效）：在 %s 中写入' % p,
        '        {"provider": "%s", "model": "%s", "api_key": "您的密钥"}' % (cfg['provider'], cfg['model']),
        '',
        '  若不想用云接口，可装 Ollama 在本机跑，数据不出本机：',
        '        --llm --llm-provider ollama --llm-model qwen2.5:7b',
        '',
        '  查看当前配置状态（不发起调用）：--llm-doctor',
        '  只想看会发出去什么内容、暂不外发：--llm-dry-run',
    ])


def build_llm_payload(r, ask=None):
    """把卦表整理成给大模型的提问。卦表以 JSON 原样给出，不做删减。"""
    lines = ['以下是一张已装好的六爻卦表，请按你的职责梳理其内部关系。', '',
             '```json', json.dumps(r, ensure_ascii=False, indent=1), '```', '']
    if ask and ask.strip():
        lines.append('使用者所问之事：' + ask.strip())
    else:
        lines.append('使用者未说明所问之事。请在「用神取法」一节照实写明无法确定用神，'
                     '并列出常见对应关系供其参考。')
    return '\n'.join(lines)


def _llm_api_error_text(body):
    """从接口错误响应里抠出一句可读的说明，不外泄任何凭据。"""
    try:
        d = json.loads(body)
        if isinstance(d, dict):
            e = d.get('error')
            if isinstance(e, dict) and e.get('message'):
                return str(e['message'])[:200]
            if isinstance(e, str):
                return e[:200]
            for k in ('message', 'msg', 'detail'):
                if d.get(k):
                    return str(d[k])[:200]
    except Exception:
        pass
    return (body or '').strip()[:200]


def call_llm(cfg, system_prompt, user_prompt):
    """调用大模型。返回 (文本, 错误说明)，二者必有其一为 None。

    网络模块在函数内部延迟导入——这样默认路径（不带 --llm）自始至终不会加载
    任何网络相关的模块，这一点由内置自检逐次核验。
    """
    import urllib.error
    import urllib.request

    if cfg['style'] == 'anthropic':
        url = cfg['base'] + '/messages'
        headers = {'Content-Type': 'application/json', 'anthropic-version': '2023-06-01'}
        if cfg['key']:
            headers['x-api-key'] = cfg['key']
        payload = {'model': cfg['model'], 'max_tokens': cfg['max_tokens'],
                   'system': system_prompt,
                   'messages': [{'role': 'user', 'content': user_prompt}]}
    else:
        url = cfg['base'] + '/chat/completions'
        headers = {'Content-Type': 'application/json'}
        if cfg['key']:
            headers['Authorization'] = 'Bearer ' + cfg['key']
        payload = {'model': cfg['model'], 'max_tokens': cfg['max_tokens'],
                   'temperature': 0.2, 'stream': False,
                   'messages': [{'role': 'system', 'content': system_prompt},
                                {'role': 'user', 'content': user_prompt}]}

    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                 headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=cfg['timeout']) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode('utf-8', errors='replace')
        except Exception:
            pass
        msg = _llm_api_error_text(body)
        extra = ''
        if e.code in (401, 403):
            extra = '（多为密钥无效或余额不足，请用 --llm-doctor 核对）'
        elif e.code == 404:
            extra = '（多为接口地址或模型名不对，请用 --llm-doctor 核对）'
        elif e.code == 429:
            extra = '（多为请求过于频繁或超出配额，稍后重试）'
        return None, '接口返回 HTTP %s%s%s' % (e.code, extra, ('：' + msg) if msg else '')
    except urllib.error.URLError as e:
        return None, ('连不上接口（%s）。请检查网络，或核对接口地址 %s 是否正确；'
                      '若用 Ollama，请确认本机服务已启动。' % (getattr(e, 'reason', e), cfg['base']))
    except OSError as e:
        # 连接被重置、连接被拒绝、超时等，都归到这里（URLError 亦属 OSError，上面已先接住）
        return None, ('连不上接口（%s: %s）。请检查网络，或核对接口地址 %s 是否正确；'
                      '若用 Ollama，请确认本机服务已启动。'
                      % (type(e).__name__, e, cfg['base']))
    except Exception as e:
        return None, '调用失败：%s: %s' % (type(e).__name__, e)

    try:
        d = json.loads(raw)
        if cfg['style'] == 'anthropic':
            text = ''.join(p.get('text', '') for p in (d.get('content') or [])
                           if isinstance(p, dict))
        else:
            text = ((d.get('choices') or [{}])[0].get('message') or {}).get('content', '')
    except Exception as e:
        return None, '接口返回的内容无法解析（%s）。' % e
    text = (text or '').strip()
    if not text:
        return None, '接口返回了空内容，可能是模型名不对或该模型不支持当前调用方式。'
    return text, None


def render_llm_doctor(cfg, notes):
    """配置体检。只展示掩码后的密钥，可放心截图。"""
    def row(k, v):
        return '%s %s' % (pad(k, 14), v)

    out = ['六爻装卦 · 大模型配置体检（本命令不发起任何调用）', LLM_SEC]
    out.append(row('服务商', '%s（%s）' % (cfg['provider_name'], cfg['provider'])))
    out.append(row('接口地址', cfg['base']))
    out.append(row('模型', cfg['model']))
    out.append(row('密钥', llm_mask(cfg['key'])))
    out.append(row('超时', '%s 秒' % cfg['timeout']))
    out.append(row('配置来源', '服务商=%s，模型=%s，地址=%s，密钥=%s'
                   % (cfg['src']['provider'], cfg['src']['model'],
                      cfg['src']['base'], cfg['src']['key'])))
    ok, why = llm_ready(cfg)
    out.append(row('可否调用', '可以' if ok else '不可以——%s' % why))
    out.append('')
    out.append('内置服务商（--llm-provider 取值）：')
    for k in sorted(LLM_PROVIDERS, key=lambda x: (x != LLM_DEFAULT_PROVIDER, x)):
        v = LLM_PROVIDERS[k]
        tag = '（需密钥）' if v['need_key'] else '（无需密钥）'
        out.append('  %s %s 预设 %s'
                   % (pad(k, 13), pad(v['name'] + tag, 28), v['model']))
    if not ok:
        out += ['', '配置方法：'] + [llm_config_hint(cfg)]
    if notes:
        out += [''] + ['提醒：' + n for n in notes]
    out.append(LLM_SEC)
    return '\n'.join(out)


def llm_trouble_hint(cfg):
    """已配置、但调用未成功时的排错指引。

    与「还未配置」的指引分开写：两种状态给同一段话，会把使用者引到错误的方向。
    """
    return '\n'.join([
        '  当前配置：服务商 %s，接口 %s，模型 %s，密钥 %s'
        % (cfg['provider_name'], cfg['base'], cfg['model'], llm_mask(cfg['key'])),
        '',
        '  逐项排查：',
        '    一、接口地址是否写对，多数服务商以 /v1 结尾——用 --llm-doctor 核一遍。',
        '    二、模型名是否是所选服务商真实存在的模型。',
        '    三、密钥是否有效、余额是否充足。',
        '    四、本机网络能否访问该接口；若用 Ollama，确认本机服务已启动。',
        '    五、换一个服务商试：--llm-provider ＜名称＞，可选值见 --llm-doctor。',
        '  若只想先看会发出去什么内容：加 --llm-dry-run，该模式不外发。',
    ])


def render_llm_section(text, cfg, err, dry=False, kind='trouble'):
    """把解读段渲染成与卦表物理隔开的一段，并把来源与边界标死。

    kind 取值：'config'＝尚未配置；'trouble'＝已配置但调用未成功。
    """
    out = ['', LLM_SEC, '第二部分 · 卦象要点梳理', LLM_SEC]
    if dry:
        out.append('【预演模式】以下内容为将发送给大模型的原样内容，本次并未外发。')
        out += ['', '接口：%s  模型：%s  密钥：%s'
                % (cfg['base'], cfg['model'], llm_mask(cfg['key'])), '', text]
        return '\n'.join(out)
    out.append('来源：%s／%s。由您自备密钥的大模型生成，内容未回传至本工具。'
               % (cfg['provider_name'], cfg['model']))
    out.append('★ 本段不是本工具的计算结果。本工具只负责上方卦表，未参与、未校验、无法复现以下内容。')
    out.append('-' * 66)
    if err:
        out.append('本次未能取得解读，原因如下：')
        out.append('  ' + err)
        out.append('')
        out.append('上方卦表不受影响，照常可用。')
        out.append('')
        if kind == 'config':
            out.append('这一项还没有配置好。配置方法：')
            out.append(llm_config_hint(cfg))
        else:
            out.append('这一项已经配置过了，问题出在接口地址、模型名或密钥上：')
            out.append(llm_trouble_hint(cfg))
    else:
        out.append(text)
    # 末尾不另加分隔线：紧接其后的「边界说明」自带一条，避免出现连续两条
    return '\n'.join(out)


def render_llm_boundary():
    """第三部分：把使用边界与免责再讲一遍，与卦表、解读各自独立成段。"""
    return '\n'.join([
        LLM_SEC, '第三部分 · 边界说明', LLM_SEC,
        '一、卦表由本机程序按京房纳甲法计算，可逐项复核（运行 --self-test 可复算）。',
        '二、要点梳理由外部大模型生成，内容不可复现，本工具不为其准确性作任何担保。',
        '三、本工具不提供吉凶判断、不提供行动建议、不预测应期。',
        '四、接入外部大模型后，卦表内容会发送至您所指定的接口。若不便外发，',
        '    可改用本机 Ollama，或只用不带 --llm 的纯本地模式。',
        '五、使用外部大模型所产生的费用由您与所选服务商结算，与本工具作者无关。',
        LLM_SEC,
    ])


def main():
    ap = argparse.ArgumentParser(description='周易六爻装卦引擎（京房纳甲法）')
    ap.add_argument('--gua', help='本卦。写法：上离下巽 / 上卦为离下卦为巽 / 离上巽下 / '
                                  '火风鼎（六十四卦名或其唯一简称）/ 011101（六位阴阳，自下而上）')
    ap.add_argument('--gua-bin', help='本卦六爻位序（自下而上 6 位 0/1）')
    ap.add_argument('--dong', default='', help='动爻，如 "5" 或 "1,2,5"；留空为静卦')
    ap.add_argument('--date', help='起卦公历时间 "YYYY-MM-DD HH:MM"（年柱月柱为节气近似）')
    ap.add_argument('--ganzhi', help='直接给定四柱 "年 月 日 时"，如 "丙午 丁酉 辛卯 甲午"（推荐，精确）')
    ap.add_argument('--parse-text', help='解析论坛装卦表文本文件')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    ap.add_argument('--out', help='把结果写入指定文件（UTF-8），避免 Windows 控制台中文乱码')
    ap.add_argument('--self-test', '--selftest', action='store_true', help='运行内置自检')
    g = ap.add_argument_group('可选：接入您自己的大模型做卦象要点梳理（不带 --llm 则完全不启用）')
    g.add_argument('--llm', action='store_true',
                   help='在卦表之后追加一段要点梳理。需自备大模型接口密钥')
    g.add_argument('--llm-ask', help='所问之事，如「问这桩生意」；决定用神怎么取，建议填')
    g.add_argument('--llm-provider', help='服务商，见 --llm-doctor；默认 ' + LLM_DEFAULT_PROVIDER)
    g.add_argument('--llm-model', help='模型名，默认取该服务商的预设值')
    g.add_argument('--llm-base', help='接口地址，默认取该服务商的预设值')
    g.add_argument('--llm-key', help='密钥（优先级最高；不建议写在命令里，容易留在历史记录）')
    g.add_argument('--llm-timeout', type=int, help='超时秒数，默认 60')
    g.add_argument('--llm-max-tokens', type=int, help='回复长度上限，默认 2048')
    g.add_argument('--llm-dry-run', action='store_true',
                   help='只打印将发送的内容，不外发，用于先确认要送出去什么')
    g.add_argument('--llm-doctor', action='store_true',
                   help='只检查配置状态，不发起调用，也不装卦')
    args = ap.parse_args()

    if args.self_test:
        sys.exit(self_test(args.out))
    if args.llm_doctor:
        cfg, notes = llm_resolve(args)
        print(render_llm_doctor(cfg, notes))
        sys.exit(0)
    if args.llm_ask and not (args.llm or args.llm_dry_run):
        raise SystemExit('--llm-ask 需与 --llm 同用：不启用解读时，所问之事无处可用')
    if args.parse_text:
        text = open(args.parse_text, encoding='utf-8').read()
        parsed = parse_zhuangguabiao(text)
        result = {'parsed': parsed, 'validate': validate_parsed(parsed)}
        print(json.dumps(result, ensure_ascii=False, indent=1))
        sys.exit(0 if result['validate']['ok'] else 2)

    code, _ = parse_gua_arg(args.gua, args.gua_bin)
    dong = parse_dong_arg(args.dong)
    yg, mg, dg, hg, kong, src = resolve_time(args)
    r = zhuanggua(code, dong, yg, mg, dg, hg, kong)
    r['source'] = src

    # 可选解读层。注意：只有显式要求时才进入这一段；进入后若任何一步不成立，
    # 都只影响解读段，卦表照常输出。
    use_llm = bool(args.llm or args.llm_dry_run)
    llm_text, llm_meta = '', None
    if use_llm:
        cfg, notes = llm_resolve(args)
        if args.llm_dry_run:
            preview = ('【系统提示词 · 将发送】\n' + LLM_SYSTEM_PROMPT
                       + '\n\n【用户消息 · 将发送】\n' + build_llm_payload(r, args.llm_ask))
            llm_text = render_llm_section(preview, cfg, None, dry=True)
            llm_meta = dict(ok=True, dry_run=True, provider=cfg['provider'], model=cfg['model'])
        else:
            ready, why = llm_ready(cfg)
            if not ready:
                llm_text = render_llm_section(None, cfg, '尚未配置——' + why, kind='config')
                llm_meta = dict(ok=False, provider=cfg['provider'], model=cfg['model'],
                                error='尚未配置——' + why)
            else:
                got, err = call_llm(cfg, LLM_SYSTEM_PROMPT, build_llm_payload(r, args.llm_ask))
                llm_text = render_llm_section(got, cfg, err)
                llm_meta = dict(ok=err is None, provider=cfg['provider'], model=cfg['model'],
                                error=err, content=got)
        if notes:
            llm_text += '\n' + '\n'.join('提醒：' + n for n in notes)

    if args.json:
        if llm_meta is not None:
            r['llm'] = llm_meta          # 密钥不在其中，也不必在其中
        text = json.dumps(r, ensure_ascii=False, indent=1)
    else:
        text = render_text(r) + '\n\n时间来源：' + src
        if use_llm:
            text = (LLM_SEC + '\n第一部分 · 卦表（本机计算，可逐项复核）\n' + LLM_SEC + '\n'
                    + text + llm_text + '\n' + render_llm_boundary())
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text + '\n')
        print('已写入：' + args.out)
    else:
        print(text)

# ===================================================================
# 精确节气表（1900-2100 年，北京时间）
# 数据源：寿星天文历算法（sxtwl 2.0.7）
# 校验源：lunar_python 1.4.8 独立实现，逐节比对（分钟级一致）
# 每年 12 个「节」按 JIE_ORDER 顺序，每节 4 位 36 进制；
# 值 = (年内第几天 - 1) * 1440 + 当天第几分钟
# ===================================================================
JIEQI_FIRST_YEAR = 1900
JIEQI_LAST_YEAR = 2100
JIE_ORDER = ['小寒', '立春', '惊蛰', '清明', '立夏', '芒种', '小暑', '立秋', '白露', '寒露', '立冬', '大雪']
JIEQI_B36 = (
    '05nf12f31zhx2x343v974tx25sum6rqq7qas8obp9lrraiqv'  # 1900
    '05x512or1zrm2xcw3vj24u705t4j6s0m7qkm8oli9m1maj0s'  # 1901
    '067312yq201j2xmp3vsq4ugj5tdy6s9y7qty8oux9mb5ajah'  # 1902
    '06gv138j20ba2xwd3w2d4uq75tno6sjr7r3u8p4t9ml1ajkb'  # 1903
    '06qp13ic20l32y663wc64v005txj6stn7rdp8pen9musaju1'  # 1904
    '05wf12o31zqx2xc23vi24u5t5t376rz87qj98ok79m0daizm'  # 1905
    '066112xr200o2xlv3vrw4ufo5td36s937qt48ou29maaaj9l'  # 1906
    '06fz137m20af2xvi3w1h4up85tmn6sin7r2q8p3q9mk0ajjb'  # 1907
    '06pp13hb20k12y533wb24uyv5twb6sse7rcg8pde9mtmajsv'  # 1908
    '05v912mw1zpo2xat3vgu4u4p5t276rya7qia8oj79lzdaiym'  # 1909
    '065112wr1zzk2xkm3vqj4ue85tbl6s7l7qrm8osl9m8taj84'  # 1910
    '06ek136a20922xu43w004unp5tl46sh87r1d8p2e9minajhv'  # 1911
    '06o713ft20ik2y3o3w9n4uxf5tuw6sr17rb58pc69mseajrm'  # 1912
    '05tx12li1zo82x9b3vfa4u315t0e6rwf7qgi8ohj9lxtaix5'  # 1913
    '063i12v51zxv2xix3vow4ucn5ta36s657qq88ora9m7naj71'  # 1914
    '06dg1351207o2xsl3vye4um45tjj6sfn7qzt8p0w9mh9ajgn'  # 1915
    '06n313ep20hd2y293w814uvp5tt56spa7r9g8paj9mquajq6'  # 1916
    '05sl12k91zn02x813vdx4u1n5sz26rv67qfb8oge9lwoaiw0'  # 1917
    '062g12u51zww2xhx3vnq4uba5t8k6s4j7qon8ops9m66aj5m'  # 1918
    '06c3133r206h2xrg3vx94ukw5ti86sea7qyf8ozl9mfzajfd'  # 1919
    '06ls13de20g32y123w6z4uuq5ts66soa7r8e8p9h9mpsajp6'  # 1920
    '05rl12j81zlx2x6w3vcs4u0h5sxu6rtv7qdx8oey9lv9aiun'  # 1921
    '061412su1zvl2xgl3vmg4ua65t7l6s3p7qnu8oox9m59aj4m'  # 1922
    '06b1132o205c2xq93vw24ujq5th66sdc7qxl8oyr9mf4ajeg'  # 1923
    '06kt13cd20f02xzx3w5p4utd5tqt6sn07r798p8g9motajo4'  # 1924
    '05qh12i01zkn2x5m3vbh4tz85swo6rsv7qd48oeb9luqaiu4'  # 1925
    '060i12s21zun2xfi3vl84u8t5t656s287qmf8ono9m47aj3q'  # 1926
    '06a8131u204e2xp63vut4uic5tfp6sbv7qw58oxf9mdwajde'  # 1927
    '06jv13bg20e12xyu3w4j4us55tpk6slr7r618p799mnpajn5'  # 1928
    '05pm12h81zjv2x4r3vag4txy5sv76rr87qbf8ocn9lt3aisk'  # 1929
    '05z212qr1ztg2xed3vk24u7m5t4v6s0w7ql48omd9m2waj2e'  # 1930
    '068v130g20322xnw3vtl4uh55teh6sak7qut8ow29mclajc4'  # 1931
    '06il13a520cp2xxi3w374uqr5to46sk77r4e8p5l9mm1ajli'  # 1932
    '05nz12fl1zi72x323v8t4twh5stw6rq17qa98obf9lruairb'  # 1933
    '05xs12pf1zs22xcv3vii4u615t3c6rzf7qjo8okw9m1eaj0w'  # 1934
    '067e12z0201m2xme3vs04ufh5tct6s8z7qtc8oun9mb5ajak'  # 1935
    '06gy138h20b12xvu3w1k4up65tmm6siv7r388p4k9ml2ajki'  # 1936
    '05mv12ed1zgw2x1p3v7e4tuy5ss96rod7q8n8o9y9lqjaiq2'  # 1937
    '05wj12o21zql2xbc3vgz4u4i5t1v6ry07qic8ojp9m0caizx'  # 1938
    '066f12xy200e2xl13vql4ue35tbi6s7r7qs68otk9ma7aj9s'  # 1939
    '06gb137v20ab2xuy3w0g4unw5tl86shf7r1t8p369mjqajj9'  # 1940
    '05lr12dd1zfy2x0o3v694ttr5sr36rn97q7n8o929lpoaip7'  # 1941
    '05vq12nc1zpx2xan3vg64u3k5t0r6rwu7qh68oil9lzbaiyy'  # 1942
    '065i12x41zzm2xkb3vpt4ud65tae6s6i7qqv8osa9m8yaj8k'  # 1943
    '06f3136m20942xtt3vzf4umy5tkc6sgi7r0v8p289miuajif'  # 1944
    '05ky12cj1zf12wzr3v5c4tst5sq26rm57q6e8o7p9loaainv'  # 1945
    '05ug12m31zoo2x9e3vex4u2c5szm6rvr7qg38ohg9ly3aixo'  # 1946
    '064612vq1zy72xiw3voe4ubv5t976s5g7qpx8ord9m80aj7k'  # 1947
    '06e0135i207x2xsl3vy44ulk5tiv6sf27qzg8p0w9mhiajh1'  # 1948
    '05jh12ay1zdf2wy33v3o4tr65soj6rkq7q568o6n9lnbaimx'  # 1949
    '05te12kw1znb2x7w3vdc4u0q5sy16ru77qel8og39lwvaiwl'  # 1950
    '063612up1zx22xhk3vmx4ua85t7h6s3p7qo68opo9m6eaj62'  # 1951
    '06cl1344206j2xr33vwi4ujw5th86sdi7qy18ozk9mg9ajfv'  # 1952
    '05ie129x1zce2wx03v2g4tps5smy6rj27q3g8o4y9lloailc'  # 1953
    '05rx12ji1zm02x6n3vc24tzc5swj6rsn7qd18oel9lveaiv4'  # 1954
    '061n12t51zvi2xg23vlh4u8v5t656s2e7qmv8oog9m59aj4y'  # 1955
    '06bi132z205c2xpv3vv94uin5tfx6sc47qwi8oxz9mepajee'  # 1956
    '05gy128i1zay2wvi3v0y4toc5slo6rhw7q2c8o3t9lkkaik7'  # 1957
    '05qs12id1zks2x5c3vap4ty05sv96rrh7qby8odj9lubaiu1'  # 1958
    '060m12s61zuk2xf33vke4u7o5t4v6s147qln8on99m42aj3p'  # 1959
    '06a6131n20402xoj3vty4uhc5teo6saz7qvl8ox89me2ajdp'  # 1960
    '05g6127m1z9y2wui3uzx4tn95ski6rgo7q158o2q9ljmaijd'  # 1961
    '05py12hh1zjt2x4a3v9l4twv5su36rq97qar8ocd9ltaait4'  # 1962
    '05zq12r71zth2xdu3vj34u6e5t3p6s017qkn8omc9m38aj30'  # 1963
    '069m1314203f2xnu3vt34ugb5tdk6s9s7qub8ovx9mcrajch'  # 1964
    '05f1126m1z902wti3uyt4tm25sj96rfg7pzz8o1n9liiaii9'  # 1965
    '05ou12gd1zir2x383v8i4tvp5ssu6rp07q9k8ob89ls7ais1'  # 1966
    '05yo12q61zsh2xcw3vi54u5c5t2h6rym7qj58okt9m1paj1h'  # 1967
    '068212zj201t2xm83vrj4uev5tc56s8f7qsz8oum9mbhajb8'  # 1968
    '05ds125a1z7m2ws23uxd4tkn5shv6re27pyj8o049lgzaigr'  # 1969
    '05nd12ex1zha2x1p3v6x4tu45sra6rni7q818o9p9lqlaiqd'  # 1970
    '05wx12od1zqm2xb03vg84u3g5t0r6rx47qhu8ojm9m0kaj0b'  # 1971
    '066t12y8200g2xks3vq14ud95tai6s6s7qrf8ot59ma3aj9u'  # 1972
    '05cd123s1z602wqd3uvm4tiu5sg36rcc7pwz8nyr9lfraifm'  # 1973
    '05m712do1zfv2x043v594tsf5spn6rlx7q6l8o8e9lphaipg'  # 1974
    '05w512nn1zpt2xa13vf34u265szb6rvk7qg98oi29lz2aiyy'  # 1975
    '065l12x31zzc2xjm3voq4ubv5t926s5e7qq48ory9m8yaj8s'  # 1976
    '05bf122x1z582wpl3uur4thw5sez6rb67pvr8nxj9lelaiei'  # 1977
    '05l712cq1zf22wzf3v4k4trn5soo6rkt7q5e8o769loaaio8'  # 1978
    '05uv12mc1zoj2x8t3vdz4u155syc6rum7qfb8oh69ly8aiy5'  # 1979
    '064s12w91zyg2xiq3vnw4ub35t8b6s4k7qp58oqv9m7uaj7p'  # 1980
    '05ac121v1z452woh3utm4tgs5sdz6ra97puv8nwl9ldkaidf'  # 1981
    '05k212bl1zdu2wy43v374tqb5sni6rjt7q4j8o6e9lngainc'  # 1982
    '05ty12lf1znn2x7w3vcy4u015sx76rth7qe88og39lx4aiwx'  # 1983
    '063g12uu1zx02xha3vme4u9k5t6t6s357qnx8opu9m6xaj6s'  # 1984
    '059b120n1z2s2wn13us64tfb5sci6r8s7pth8nvc9lchaicg'  # 1985
    '05j412aj1zco2wwu3v1u4tow5sm06ri97q2y8o4u9lm0aim0'  # 1986
    '05sp12k31zm52x683vb54ty65sve6rrt7qco8oen9lvtaivs'  # 1987
    '062f12tu1zvy2xg33vl14u825t586s1k7qmb8oo89m5caj5a'  # 1988
    '057x11zf1z1m2wlt3uqt4tdt5sav6r737prt8ntr9laxaiaw'  # 1989
    '05hl12921zb72wvc3v0b4tna5skc6rgl7q1d8o3d9lknaikq'  # 1990
    '05rg12iw1zl02x543va24tx25su46rqd7qb38od19lu7aiu8'  # 1991
    '060w12sc1zug2xel3vjk4u6m5t3s6s037qku8omr9m3xaj3w'  # 1992
    '056k11y11z062wkd3upd4tcf5s9k6r5t7pqj8nsg9l9lai9l'  # 1993
    '05gc127u1za12wu73uz64tm45sj76rfg7q078o259ljbaija'  # 1994
    '05py12hc1zjg2x3k3v8i4tvi5sso6rp37qa08oc39ltbaita'  # 1995
    '05zv12r71zt92xde3vie4u5g5t2n6rz07qju8olu9m32aj32'  # 1996
    '055o11x11yz42wj83uo74tb85s8d6r4o7ppg8nrh9l8qai8s'  # 1997
    '05fi126w1z8x2wsw3uxr4tkp5shu6re77pz38o179likaiip'  # 1998
    '05ph12gx1zix2x2w3v7o4tul5sro6ro27q8x8ob09ls9aisb'  # 1999
    '05z012qg1zsi2xcj3vhe4u4a5t1d6rxq7qin8okq9m20aj21'  # 2000
    '054p11w41yy82wic3un84ta55s766r3g7poa8nqd9l7oai7s'  # 2001
    '05ej12601z832ws63ux14tjw5sgw6rd37pxv8nzx9lh9aihe'  # 2002
    '05o312fh1zhg2x1g3v6a4tt75sqb6rmo7q7k8o9o9lr1air5'  # 2003
    '05xu12p81zr72xb73vg24u315t076rwj7qhc8ojd9m0maj0o'  # 2004
    '053e11uv1ywx2wgy3uls4t8p5s5s6r237pmw8nox9l66ai68'  # 2005
    '05cy124f1z6g2wqf3uv64ti05sf36rbg7pwf8nyl9lfyaig2'  # 2006
    '05ms12e61zg52x043v4w4trr5sot6rl77q658o8b9lpoaipq'  # 2007
    '05wc12no1zpm2x9l3vef4u1b5sye6rus7qfq8ohw9lzaaize'  # 2008
    '052211td1yvb2wf93uk24t6z5s416r0d7pl98nng9l4wai54'  # 2009
    '05bw123b1z5a2wp63utw4tgp5sdq6ra17puw8nx29leiaieq'  # 2010
    '05li12cw1zet2wyn3v3b4tq35sn56rjl7q4m8o6v9loaaiog'  # 2011
    '05v712mm1zol2x8h3vd74u015sx46rti7qeg8ogn9ly1aiy6'  # 2012
    '050x11sd1yue2wee3uj64t5z5s2y6qz87pk48nma9l3pai3w'  # 2013
    '05ao12231z422wny3usn4tff5sce6r8q7ptp8nvz9ldiaids'  # 2014
    '05kk12by1zdv2wxr3v2g4tpa5smc6rip7q3n8o5u9lnaainh'  # 2015
    '05u812lm1znj2x7f3vc54tz05sw36rsg7qdf8ofl9lwzaix5'  # 2016
    '04zv11ra1yt82wd53uhu4t4o5s1q6qy37pj28nla9l2pai2w'  # 2017
    '059o12141z342wn03urp4teh5sbh6r7u7pst8nv29lcjaicp'  # 2018
    '05je12aq1zcl2wwf3v124tnu5skw6rhc7q2g8o4t9lmcaimi'  # 2019
    '05t512kf1zm82x623var4txm5suq6rr67qc78oej9lw1aiw9'  # 2020
    '04yz11qa1ys52wby3ugn4t3f5s0h6qwt7phs8nk29l1mai1w'  # 2021
    '058p12021z1v2wlk3uq14tcp5s9p6r647pr88ntm9lb9aibm'  # 2022
    '05ig129u1zbo2wvc3uzu4tmi5sji6rfy7q128o3f9lkzail8'  # 2023
    '05s112je1zla2x523v9l4tw95st76rpl7qan8ocz9lujaius'  # 2024
    '04xk11oy1yqv2wao3uf84t1w5rys6qv37pg38nig9l03ai0g'  # 2025
    '057a11yp1z0m2wkf3up04tbo5s8k6r4u7pps8ns49l9raia4'  # 2026
    '05gx12891za32wtt3uyc4tl15si06ree7pzg8o1s9ljeaijp'  # 2027
    '05qi12hu1zjo2x3e3v7z4tur5srt6ro87q998obk9lt2aitc'  # 2028
    '04w511nk1yph2w9a3udv4t0l5rxm6qtz7pez8nh99kysahz1'  # 2029
    '055u11x81yz22wis3un94t9w5s6v6r3a7pog8nqw9l8kai8v'  # 2030
    '05fm126x1z8q2wsf3uwy4tjn5sgo6rd67pyd8o0u9lihaiiq'  # 2031
    '05pf12go1zif2x253v6p4ttf5sqg6rmw7q818oah9ls5aisg'  # 2032
    '04v711mh1yo72w7v3ucd4sz05rw06qsf7pdj8ng19kxsahy8'  # 2033
    '055411wg1yy72wht3um84t8u5s5t6r287pnd8npu9l7lai80'  # 2034
    '05ev12671z7x2wrh3uvu4tie5sfc6rbt7px18nzl9lhbaiho'  # 2035
    '05oi12fv1zhn2x193v5o4tsa5sp96rlo7q6u8o9c9lr2airf'  # 2036
    '04u911ln1ynh2w773ubo4sya5rv66qri7pck8nf19kwrahx6'  # 2037
    '054211vf1yx62wgs3ul64t7p5s4j6r0w7pm18nok9l6eai6v'  # 2038
    '05ds12541z6u2wqf3uut4the5sed6rat7pvz8nyg9lg6aigk'  # 2039
    '05ne12er1zgi2x043v4k4tr75so66rkl7q5p8o849lpsaiq5'  # 2040
    '04sz11kc1ym52w5r3ua54swp5rtl6qq07pb48ndm9kvcahvr'  # 2041
    '052m11u01yvt2wff3uju4t6d5s3a6qzq7pkw8nnf9l56ai5k'  # 2042
    '05cc123m1z5b2wov3ut94tft5scr6r987puh8nx39levaif8'  # 2043
    '05lz12d71zeu2wye3v2s4tpf5smf6riv7q438o6o9lohaiow'  # 2044
    '04rp11iz1yko2w483u8m4sv85rs76qom7p9s8ncb9ku5ahum'  # 2045
    '051j11su1yuh2wdw3ui34t4j5s1f6qxw7pj68nlt9l3pai48'  # 2046
    '05b5122h1z442wnj3urr4te85sb56r7p7pt18nvo9ldiaidy'  # 2047
    '05ks12c31zdt2wxc3v1n4to55sl26rhi7q2r8o5d9ln8aino'  # 2048
    '04qh11hs1yji2w313u7b4stq5rqk6qmx7p848nas9kspaht9'  # 2049
    '050711rj1yt72wcq3uh14t3i5s0d6qwr7phz8nkn9l2kai34'  # 2050
    '05a1121b1z2x2wmc3uqm4td35sa06r6h7prq8nud9lc9aicr'  # 2051
    '05jn12ay1zck2ww03v0a4tms5sjr6rg87q1h8o439llxaime'  # 2052
    '04pb11go1yie2w1x3u684ssq5rpo6qm57p7d8n9z9krtahsb'  # 2053
    '04z711qj1ys62wbm3uft4t265rz16qvi7pgu8njl9l1jai22'  # 2054
    '058x12071z1s2wl73upf4tbv5s8s6r5c7pqq8nti9lbfaibx'  # 2055
    '05iq129y1zbj2wuz3uz94tlr5sip6rf77q0i8o389ll6ailq'  # 2056
    '04ol11ft1yhe2w0r3u4x4srb5ro56qkl7p5v8n8l9kqmahr9'  # 2057
    '04y911pl1yr72waj3uen4t0z5rxu6quc7pfp8nig9l0gai12'  # 2058
    '058011zb1z0v2wk73uob4tan5s7i6r3z7ppd8ns59la4aiao'  # 2059
    '05hl128v1zah2wtu3uy04tkc5sh66rdm7pyx8o1o9ljoaik8'  # 2060
    '04n511eg1yg42vzl3u3t4sq75rn16qjg7p4p8n7f9kpfahq1'  # 2061
    '04wz11oa1ypu2w963uda4szm5rwd6qss7pe38ngv9kyxahzl'  # 2062
    '056k11xu1yzd2wio3umr4t945s606r2j7pnw8nqo9l8nai97'  # 2063
    '05g4127e1z8y2wsb3uwh4tix5sfu6rcd7pxp8o0f9licaiiw'  # 2064
    '04ls11d21yeo2vy13u244sof5rl86qho7p318n5t9kntahog'  # 2065
    '04ve11mo1yo92w7k3ubn4sxz5rut6qrc7pcs8nfo9kxqahyb'  # 2066
    '055611wc1yxt2wh33ul74t7k5s4g6r107pmh8npe9l7hai83'  # 2067
    '05ey12641z7k2wqs3uuv4th85se46ram7pw18nyw9lh0aihp'  # 2068
    '04kn11bw1ydd2vwn3u0p4sn25rjy6qgh7p1v8n4q9kmuahnl'  # 2069
    '04um11lx1ynd2w6j3uag4swn5rtf6qpx7pbf8nec9kwiahx9'  # 2070
    '054b11vm1yx32wg93uk64t6d5s366qzq7pl98no79l6bai70'  # 2071
    '05dy12581z6s2wq23uu44tgf5sd86r9q7pv68ny29lg7aigv'  # 2072
    '04ju11b41ycn2vvy3tzz4sm55riu6qf77p0k8n3g9klnahmf'  # 2073
    '04th11ks1ymb2w5k3u9k4svs5rsk6qp07paf8ndc9kviahw9'  # 2074
    '053911uh1yvy2wf63uj64t5h5s2c6qyv7pkb8nn69l5aai5z'  # 2075
    '05cy12471z5o2wov3usv4tf55sbz6r8h7ptw8nwq9lesaifg'  # 2076
    '04if119q1yba2vuk3tyl4skv5rhq6qe97ozq8n2m9kkpahld'  # 2077
    '04sc11jk1yl12w473u844suc5rr46qnn7p968nc79kueahv4'  # 2078
    '052011t61yuk2wdo3uhl4t3t5s0n6qx87pit8nlu9l42ai4r'  # 2079
    '05bm122r1z442wna3ur94tdl5sag6r727psl8nvl9ldtaiel'  # 2080
    '04hj118p1ya22vt43twz4sj45rfu6qcc7oxt8n0t9kj4ahjz'  # 2081
    '04r111ib1yjp2w2q3u6i4ssl5rpc6qlw7p7h8nak9ksvahto'  # 2082
    '050p11rx1ytb2wcd3ug64t2b5rz36qvo7ph98nkc9l2nai3f'  # 2083
    '05ae121l1z302wm33upy4tc25s8q6r577pqp8ntq9lc0aicu'  # 2084
    '04fv11751y8l2vrr3tvo4sht5rej6qb07owi8mzj9khuahiq'  # 2085
    '04pt11h11yif2w1h3u5a4sre5ro36qkk7p638n969krjahsf'  # 2086
    '04zh11qq1ys32wb33uew4t0z5rxr6qub7pfv8niw9l16ai1z'  # 2087
    '059012091z1o2wks3uoo4tav5s7p6r4b7ppv8nsv9lb4aibw'  # 2088
    '04ew11661y7m2vqp3tuj4sgl5rda6q9s7ovb8myd9kgoahhi'  # 2089
    '04ok11ft1yh82w0b3u444sq65rmv6qjg7p538n899kqmahrf'  # 2090
    '04yd11pi1yqt2w9v3udq4szw5rwq6qtc7pf08ni69l0kai1d'  # 2091
    '058c11zg1z0q2wjp3unj4t9p5s6g6r2z7poj8nrn9la0aiaw'  # 2092
    '04dy11551y6h2vph3tt94sfe5rc66q8r7oud8mxh9kfvahgs'  # 2093
    '04nw11f41yge2vzb3u2z4soz5rlp6qib7p3z8n769kpmahqj'  # 2094
    '04xm11ou1yq52w923ucp4syn5rvc6qry7pdm8ngt9kz8ai03'  # 2095
    '057311ya1yzm2win3umf4t8h5s586r1s7png8nqm9l91ai9x'  # 2096
    '04cy11451y5h2voh3ts74se75ras6q787oss8mvy9kefahff'  # 2097
    '04mj11ds1yf32vy03u1o4snm5rk96qgr7p2e8n5l9ko2ahp0'  # 2098
    '04w211n81yoi2w7e3ub44sx75rtz6qql7pc98nff9kxuahyq'  # 2099
    '055s11wz1yya2wh73ukw4t6x5s3m6r057plq8nou9l77ai83'  # 2100
)

if __name__ == '__main__':
    main()
