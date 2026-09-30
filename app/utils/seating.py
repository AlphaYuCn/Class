"""智能排座: 打分函数 + 蛇形初始化 + 模拟退火

邻接(4 邻域)打分:
- 成绩相近 g(a,b) = 1 - min(1, |ta - tb| / 100)
- 学科互补 comp = 1/9 * Σ [strength_a[k]·(1-strength_b[k]) + strength_b[k]·(1-strength_a[k])] / 2
- 同性别 sg = 1 if same else 0
- 星座互补 zodiac = compat_score(elem_a, elem_b)

总评分 = w1·g + w2·comp + w3·sg + w4·zodiac
默认权重: w1=1.0, w2=1.2, w3=0.6, w4=0.4
强制同性别模式: w3=2.0, 异性别 pair 直接扣 2.0
"""
import math
import random
from dataclasses import dataclass, field

from app.utils.zodiac import compat_score
from app.models import ScoreRecord


@dataclass
class StudentFeatures:
    sid: int
    total_avg: float  # 历次总分均值
    strength: dict     # {subject: [0,1]}
    gender: str
    element: str  # 火/风/土/水
    name: str = ""


@dataclass
class ScoreBreakdown:
    grade: float = 0.0       # 成绩相近累计
    complement: float = 0.0   # 学科互补累计
    same_gender: float = 0.0  # 同性别累计
    zodiac: float = 0.0       # 星座累计
    total: float = 0.0


def build_features(students, score_records_by_sid: dict) -> dict:
    """根据学生 + 历次成绩构建特征字典 {sid: StudentFeatures}"""
    # 收集每学生各科成绩列表与总分列表
    feat = {}
    for s in students:
        recs = score_records_by_sid.get(s.id, [])
        totals = [r.total for r in recs if r.total is not None]
        # 各科成绩列表
        subj_scores = {}
        for subj in ScoreRecord.SUBJECTS:
            vals = [getattr(r, subj) for r in recs if getattr(r, subj) is not None]
            subj_scores[subj] = vals
        # 班级各科 min/max (用于 strength)
        all_min = {}
        all_max = {}
        for subj in ScoreRecord.SUBJECTS:
            all_vals = []
            for sid_recs in score_records_by_sid.values():
                all_vals.extend([getattr(r, subj) for r in sid_recs if getattr(r, subj) is not None])
            all_min[subj] = min(all_vals) if all_vals else 0
            all_max[subj] = max(all_vals) if all_vals else 1
        # strength ∈ [0,1], 无数据 0.5
        strength = {}
        for subj in ScoreRecord.SUBJECTS:
            vals = subj_scores[subj]
            if vals and all_max[subj] > all_min[subj]:
                avg_v = sum(vals) / len(vals)
                strength[subj] = (avg_v - all_min[subj]) / (all_max[subj] - all_min[subj])
            else:
                strength[subj] = 0.5
        feat[s.id] = StudentFeatures(
            sid=s.id,
            total_avg=sum(totals) / len(totals) if totals else 0.0,
            strength=strength,
            gender=s.gender or "M",
            element=s.zodiac_element or "",
            name=s.name,
        )
    return feat


def pair_score(a: StudentFeatures, b: StudentFeatures,
                w1=1.0, w2=1.2, w3=0.6, w4=0.4,
                force_same_gender=False) -> tuple:
    """计算一对学生的邻接分 (grade, comp, same_gender, zodiac)"""
    # 成绩相近
    diff = abs(a.total_avg - b.total_avg)
    g = 1 - min(1.0, diff / 100.0)
    # 学科互补
    comp_sum = 0.0
    for k in a.strength:
        sa = a.strength[k]
        sb = b.strength[k]
        comp_sum += (sa * (1 - sb) + sb * (1 - sa)) / 2
    comp = comp_sum / len(a.strength) if a.strength else 0.0
    # 同性别
    sg = 1.0 if a.gender == b.gender else 0.0
    # 星座
    zo = compat_score(a.element, b.element)

    grade = w1 * g
    complement = w2 * comp
    same_gender = w3 * sg
    zodiac = w4 * zo
    if force_same_gender and a.gender != b.gender:
        # 强制同性别: 异性邻接扣分
        same_gender -= 2.0
    return grade, complement, same_gender, zodiac


def _neighbors(pos, rows, cols):
    r, c = pos
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            yield (nr, nc)


def snake_initialize(sids: list, rows: int, cols: int):
    """蛇形(S 形)初始化: 按学号(传入顺序)蛇形填入网格

    改进: 学生数不足时, 空座集中到后排(后往前填满)
    """
    grid = [[None] * cols for _ in range(rows)]
    capacity = rows * cols
    sids = list(sids)
    n = len(sids)
    # 不够则补 None (空座)
    while len(sids) < capacity:
        sids.append(None)
    sids = sids[:capacity]
    # 学生数 < 容量时: 让空座集中到后排
    # 策略: 先把学生填到前 n 个位置(按蛇形), 后面留空
    if n < capacity:
        # 先把 None 全部挪到末尾
        sids.sort(key=lambda x: 1 if x is None else 0)
    idx = 0
    for r in range(rows):
        cells = range(cols) if r % 2 == 0 else range(cols - 1, -1, -1)
        for c in cells:
            grid[r][c] = sids[idx]
            idx += 1
    return grid


def _desk_partner_score(a, b, w3=0.6):
    """同桌双人组(1-2, 3-4, 5-6, 7-8 列)同性别奖励"""
    if a is None or b is None:
        return 0.0
    return w3 if a.gender == b.gender else 0.0


def _front_fill_penalty(grid, rows, cols, w_empty=2.0):
    """前排空座惩罚: 前排每出现一个空座扣 w_empty 分"""
    penalty = 0.0
    for r in range(rows):
        # 越靠前排惩罚越大(线性递减)
        weight = (rows - r) / rows
        for c in range(cols):
            if grid[r][c] is None:
                penalty += w_empty * weight
    return -penalty  # 惩罚为负值


def desk_partner_total(grid, feat, rows, cols, w3=0.6):
    """计算所有同桌双人组同性别奖励总和"""
    total = 0.0
    for r in range(rows):
        # 同桌对: (0,1) (2,3) (4,5) (6,7)
        for c in range(0, cols - 1, 2):
            a_id = grid[r][c]
            b_id = grid[r][c + 1]
            if a_id is None or b_id is None:
                continue
            a = feat.get(a_id) if a_id is not None else None
            b = feat.get(b_id) if b_id is not None else None
            if a and b:
                total += _desk_partner_score(a, b, w3)
    return total


def grid_total_score(grid, feat, rows, cols, **kw) -> ScoreBreakdown:
    """计算网格总评分(每对相邻只计一次, 避免重复)

    新增: 同桌双人组同性别奖励 + 前排空座惩罚
    """
    bd = ScoreBreakdown()
    seen = set()
    for r in range(rows):
        for c in range(cols):
            sa = grid[r][c]
            if sa is None:
                continue
            for (nr, nc) in _neighbors((r, c), rows, cols):
                key = (sa, grid[nr][nc])
                if grid[nr][nc] is None:
                    continue
                # 去重: (a,b) 与 (b,a) 视为同一对
                sorted_key = tuple(sorted(key))
                if sorted_key in seen:
                    continue
                seen.add(sorted_key)
                g, comp, sg, zo = pair_score(feat[sa], feat[grid[nr][nc]], **kw)
                bd.grade += g
                bd.complement += comp
                bd.same_gender += sg
                bd.zodiac += zo
    # 同桌双人组奖励
    w3 = kw.get("w3", 0.6)
    bd.same_gender += desk_partner_total(grid, feat, rows, cols, w3)
    # 前排空座惩罚
    bd.total = bd.grade + bd.complement + bd.same_gender + bd.zodiac
    bd.total += _front_fill_penalty(grid, rows, cols)
    return bd


def _local_score(grid, pos, feat, rows, cols, **kw):
    """计算 pos 处学生与其四邻的 pair 总分(不去重, 调用方负责去重 pos1-pos2 互邻情况)

    包含: 同桌对奖励; 前排空座惩罚由 arrange 在 Δ 中作为全局项单独计算
    """
    r, c = pos
    sa = grid[r][c]
    if sa is None:
        return 0.0
    total = 0.0
    for (nr, nc) in _neighbors((r, c), rows, cols):
        sb = grid[nr][nc]
        if sb is None:
            continue
        g, comp, sg, zo = pair_score(feat[sa], feat[sb], **kw)
        total += g + comp + sg + zo
    # 同桌对奖励: (c, c+1) 或 (c-1, c)
    w3 = kw.get("w3", 0.6)
    a = feat.get(sa)
    if a:
        for partner_c in [c + 1, c - 1]:
            # 只取偶数起始的对: (0,1) (2,3) ...
            pair_start = min(c, partner_c)
            if pair_start % 2 != 0:
                continue
            if 0 <= partner_c < cols:
                b_id = grid[r][partner_c]
                if b_id is not None:
                    b = feat.get(b_id)
                    if b:
                        total += _desk_partner_score(a, b, w3)
    return total


def arrange(students, score_records_by_sid: dict, rows: int, cols: int,
            w1=1.0, w2=1.2, w3=0.6, w4=0.4, force_same_gender=False,
            iterations=2000, seed=None):
    """智能排座主入口

    Args:
        students: list[Student]
        score_records_by_sid: {sid: list[ScoreRecord]}
        rows, cols: 网格尺寸
        w1-w4: 权重
        force_same_gender: 强制同性别邻座
        iterations: 模拟退火迭代次数
        seed: 随机种子

    Returns:
        {
            "grid": [[sid or None, ...], ...],
            "score": ScoreBreakdown,
            "feat": {sid: StudentFeatures},
            "rows": rows, "cols": cols,
        }

    优化目标:
        1) 相邻学生成绩相近/学科互补/同性别/星座相配(原)
        2) 同桌双人组(列1-2/3-4/5-6/7-8)同性别奖励(新)
        3) 前排优先填满, 空座集中到后排(新)
    """
    if not students:
        raise ValueError("没有学生可排座")
    if len(students) > rows * cols:
        raise ValueError(f"学生数 {len(students)} 超过座位数 {rows*cols}")

    rng = random.Random(seed) if seed is not None else random
    feat = build_features(students, score_records_by_sid)
    sids = [s.id for s in students]

    kw = dict(w1=w1, w2=w2, w3=w3, w4=w4, force_same_gender=force_same_gender)

    # 蛇形初始化(按总分降序填入, 强者分散; 空座集中到后排)
    sorted_sids = sorted(sids, key=lambda sid: feat[sid].total_avg, reverse=True)
    grid = snake_initialize(sorted_sids, rows, cols)

    best_grid = [row[:] for row in grid]
    best_score = grid_total_score(grid, feat, rows, cols, **kw)
    cur_score = best_score.total

    # 模拟退火
    T_start = 0.5
    T_end = 0.01
    if iterations <= 0:
        iterations = 2000
    positions = [(r, c) for r in range(rows) for c in range(cols)]

    for i in range(iterations):
        T = T_start - (T_start - T_end) * (i / max(1, iterations))
        if T <= 0:
            T = 0.001
        # 随机选两个位置交换
        pos1, pos2 = rng.sample(positions, 2)
        s1 = grid[pos1[0]][pos1[1]]
        s2 = grid[pos2[0]][pos2[1]]
        if s1 is None and s2 is None:
            continue
        # 计算 Δ: 只看受影响的邻接对 + 同桌对 + 前排空座惩罚(全局项)
        before = _local_score(grid, pos1, feat, rows, cols, **kw) + \
                 _local_score(grid, pos2, feat, rows, cols, **kw) + \
                 _front_fill_penalty(grid, rows, cols)
        # 去除 pos1-pos2 互为邻接时的重复
        if _is_adjacent(pos1, pos2, rows, cols) and s1 is not None and s2 is not None:
            g, comp, sg, zo = pair_score(feat[s1], feat[s2], **kw)
            before -= (g + comp + sg + zo)

        # 交换
        grid[pos1[0]][pos1[1]], grid[pos2[0]][pos2[1]] = s2, s1
        after = _local_score(grid, pos1, feat, rows, cols, **kw) + \
                _local_score(grid, pos2, feat, rows, cols, **kw) + \
                _front_fill_penalty(grid, rows, cols)
        if _is_adjacent(pos1, pos2, rows, cols) and s1 is not None and s2 is not None:
            g, comp, sg, zo = pair_score(feat[s1], feat[s2], **kw)
            after += (g + comp + sg + zo)

        delta = after - before
        if delta > 0 or (T > 0 and rng.random() < math.exp(delta / T)):
            # 接受
            cur_score += delta
            if cur_score > best_score.total:
                best_grid = [row[:] for row in grid]
                best_score = grid_total_score(grid, feat, rows, cols, **kw)
        else:
            # 撤销
            grid[pos1[0]][pos1[1]], grid[pos2[0]][pos2[1]] = s1, s2

    # 用最优解
    best_score = grid_total_score(best_grid, feat, rows, cols, **kw)
    return {
        "grid": best_grid,
        "score": best_score,
        "feat": feat,
        "rows": rows,
        "cols": cols,
    }


def _is_adjacent(p1, p2, rows, cols):
    for (nr, nc) in _neighbors(p1, rows, cols):
        if (nr, nc) == p2:
            return True
    return False
