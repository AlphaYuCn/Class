"""排名 + 分段统计"""
from collections import defaultdict
from app.models import ScoreRecord


def compute_class_rank(records):
    """按 total 降序补 class_rank(method='min', 同分同名次)
    records: list[ScoreRecord]
    """
    # 过滤 None total 的排在最后
    valid = [r for r in records if r.total is not None]
    no_total = [r for r in records if r.total is None]
    valid.sort(key=lambda r: r.total, reverse=True)
    prev_score = None
    rank = 0
    same_count = 0
    for i, r in enumerate(valid, 1):
        if r.total == prev_score:
            same_count += 1
        else:
            same_count = 0
            rank = i
        r.class_rank = rank
        prev_score = r.total
    # 缺总分的排末尾
    base_rank = len(valid) + 1
    for r in no_total:
        r.class_rank = base_rank
    return records


def score_segments(records, bin_width=10, full_score=750):
    """把学生按 total 分到分段
    返回 [{"range":"570-579", "count":N, "start":570, "end":579}, ...]

    改进: 起始段人数为 0 则不显示(从第一个 count>0 的段开始返回)
    """
    valid = [r.total for r in records if r.total is not None]
    if not valid:
        return []
    bins = list(range(0, int(full_score) + bin_width, bin_width))
    seg_count = defaultdict(int)
    for t in valid:
        idx = min(int(t // bin_width), len(bins) - 2)
        seg_count[idx] += 1
    result = []
    for i in range(len(bins) - 1):
        result.append({
            "range": f"{bins[i]}-{bins[i+1]-1}",
            "count": seg_count.get(i, 0),
            "start": bins[i],
            "end": bins[i+1] - 1,
        })
    # 起始/末尾段人数为 0 则不显示: 裁剪到首个 count>0 ~ 末个 count>0
    first_nonzero = next((i for i, s in enumerate(result) if s["count"] > 0), None)
    if first_nonzero is None:
        return []
    last_nonzero = max(i for i, s in enumerate(result) if s["count"] > 0)
    return result[first_nonzero:last_nonzero + 1]


def subject_stats(records):
    """各科: 平均分/最高/最低/众数/中位数/参考人数
    返回 {subject: {avg, max, min, median, count}}
    """
    stats = {}
    for subj in ScoreRecord.SUBJECTS:
        scores = [getattr(r, subj) for r in records if getattr(r, subj) is not None]
        if not scores:
            stats[subj] = {"avg": None, "max": None, "min": None, "median": None, "count": 0}
            continue
        stats[subj] = {
            "avg": round(sum(scores) / len(scores), 2),
            "max": max(scores),
            "min": min(scores),
            "median": sorted(scores)[len(scores) // 2],
            "count": len(scores),
        }
    return stats


def display_rank(record):
    """返回优先使用年级排名(学校排名), 若无则回退班级排名"""
    if record.grade_rank is not None:
        return record.grade_rank
    return record.class_rank


def rank_delta_value(prev_record, cur_record):
    """计算排名升降差值(正数=进步, 负数=退步)
    优先使用年级排名; 若任一方缺年级排名则回退班级排名; 都无则 None
    """
    if (prev_record.grade_rank is not None and
            cur_record.grade_rank is not None):
        return prev_record.grade_rank - cur_record.grade_rank
    if (prev_record.class_rank is not None and
            cur_record.class_rank is not None):
        return prev_record.class_rank - cur_record.class_rank
    return None


def subject_rank(records, subject):
    """某科班级排名(method=min)"""
    valid = [r for r in records if getattr(r, subject) is not None]
    valid.sort(key=lambda r: getattr(r, subject), reverse=True)
    rank_map = {}
    prev = None
    rank = 0
    same = 0
    for i, r in enumerate(valid, 1):
        v = getattr(r, subject)
        if v == prev:
            same += 1
        else:
            same = 0
            rank = i
        rank_map[r.student_id] = rank
        prev = v
    return rank_map
