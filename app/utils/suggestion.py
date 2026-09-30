"""成绩升降对比 + 学科学习建议规则引擎

输出结构化 dict, 模板渲染中文卡片
"""
from app.models import ScoreRecord
from app.utils.ranking import subject_stats, subject_rank, rank_delta_value


# 各科满分(语数外150, 选科100), 用于雷达图与建议
SUBJECT_FULL = {
    "chinese": 150, "math": 150, "english": 150,
    "physics": 100, "chemistry": 100, "biology": 100,
    "politics": 100, "history": 100, "geography": 100,
}

SUBJECT_LABEL = {
    "chinese": "语文", "math": "数学", "english": "英语",
    "physics": "物理", "chemistry": "化学", "biology": "生物",
    "politics": "政治", "history": "历史", "geography": "地理",
}


def compare_exams(current: ScoreRecord, prev: ScoreRecord | None,
                  all_current_records: list, all_prev_records: list | None):
    """生成对比 + 建议数据

    Returns:
        dict: {
            total_delta, class_rank_delta, grade_rank_delta,
            subjects: [{subject, label, current, prev, delta, ...}],
            suggestions: [{subject, label, advice, level}],
            overall_advice: str,
        }
    """
    result = {
        "has_prev": prev is not None,
        "total_delta": None,
        "rank_delta": None,
        "class_rank_delta": None,
        "grade_rank_delta": None,
        "subjects": [],
        "suggestions": [],
        "overall_advice": "",
    }

    if prev is None:
        # 首次考试
        for subj in ScoreRecord.SUBJECTS:
            v = getattr(current, subj)
            if v is None:
                continue
            result["subjects"].append({
                "subject": subj,
                "label": SUBJECT_LABEL[subj],
                "current": v,
                "prev": None,
                "delta": None,
                "full": SUBJECT_FULL[subj],
            })
        result["overall_advice"] = "本次为首次考试, 已建立学习轨迹, 后续将自动对比升降. "
        result["suggestions"] = _subject_advice(current, all_current_records)
        return result

    # ---- 总分/排名 Δ ----
    if current.total is not None and prev.total is not None:
        result["total_delta"] = round(current.total - prev.total, 1)
    # 排名升降: 优先年级排名(学校排名), 回退班级排名
    result["rank_delta"] = rank_delta_value(prev, current)
    # 同时保留班排/年排各自的 Δ (供详情页展示)
    if current.class_rank is not None and prev.class_rank is not None:
        result["class_rank_delta"] = prev.class_rank - current.class_rank
    if current.grade_rank is not None and prev.grade_rank is not None:
        result["grade_rank_delta"] = prev.grade_rank - current.grade_rank

    # ---- 各科 Δ ----
    for subj in ScoreRecord.SUBJECTS:
        cv = getattr(current, subj)
        pv = getattr(prev, subj)
        if cv is None and pv is None:
            continue
        delta = None
        if cv is not None and pv is not None:
            delta = round(cv - pv, 1)
        result["subjects"].append({
            "subject": subj,
            "label": SUBJECT_LABEL[subj],
            "current": cv,
            "prev": pv,
            "delta": delta,
            "full": SUBJECT_FULL[subj],
        })

    # ---- 学科建议 ----
    result["suggestions"] = _subject_advice(current, all_current_records, prev, all_prev_records)

    # ---- 总评 ----
    if result["rank_delta"] is not None:
        d = result["rank_delta"]
        if d >= 3:
            result["overall_advice"] = f"年级排名进步 {d} 名, 表现优异! 总结近期有效方法, 保持节奏. "
        elif d <= -3:
            result["overall_advice"] = f"年级排名退步 {-d} 名, 建议与家长沟通, 复盘近期学习状态. "
        else:
            result["overall_advice"] = "年级排名相对稳定, 关注具体学科升降寻找突破点. "

    # 学科不均衡提示
    subjs = [s for s in result["subjects"] if s["current"] is not None]
    if len(subjs) >= 2:
        normalized = [s["current"] / s["full"] for s in subjs]
        spread = (max(normalized) - min(normalized)) * 100
        if spread > 20:
            weak = min(subjs, key=lambda s: s["current"] / s["full"])
            result["overall_advice"] += f"学科不均衡明显, 弱势科目为{weak['label']}, 建议优先投入. "
    return result


def _subject_advice(current: ScoreRecord, all_current_records: list,
                    prev: ScoreRecord | None = None, all_prev_records: list | None = None):
    """对各科独立生成建议"""
    advice_list = []
    # 班均
    stats = subject_stats(all_current_records)
    prev_stats = subject_stats(all_prev_records) if all_prev_records else {}

    for subj in ScoreRecord.SUBJECTS:
        v = getattr(current, subj)
        if v is None:
            advice_list.append({
                "subject": subj,
                "label": SUBJECT_LABEL[subj],
                "advice": "本次缺考, 建议尽快补测以建立完整学习轨迹. ",
                "level": "warn",
            })
            continue
        full = SUBJECT_FULL[subj]
        cur_stats = stats.get(subj, {})
        avg = cur_stats.get("avg")
        # 该科班级排名
        ranks = subject_rank(all_current_records, subj)
        my_rank = ranks.get(current.student_id)
        advice = []
        level = "info"

        # 1. 优势科保持
        if my_rank is not None and my_rank <= 3:
            advice.append(f"班级排名第 {my_rank}, 优势科目, 继续保持, 可适度挑战难题拓展. ")
            level = "good"

        # 2. 低于班均
        if avg is not None and v < avg:
            advice.append(f"低于班均 {round(avg - v, 1)} 分, 建议同伴互助或组内补习巩固基础. ")
            level = "warn" if level != "good" else level

        # 3. 满分占比 < 50% 视为基础薄弱
        if v < full * 0.5:
            advice.append(f"得分率仅 {round(v/full*100, 0)}%, 基础薄弱, 建议每日基础练习 30 分钟并主动答疑. ")
            level = "danger"

        # 4. 与上次对比
        if prev is not None:
            pv = getattr(prev, subj)
            if pv is not None:
                delta = v - pv
                if delta < -10:
                    advice.append(f"较上次下滑 {-round(delta,1)} 分, 需复盘近期学习方法. ")
                    level = "danger"
                elif delta > 10:
                    advice.append(f"较上次进步 {round(delta,1)} 分, 总结有效方法保持. ")
                    level = "good"
            else:
                advice.append("上次缺考, 无法对比. ")

        advice_list.append({
            "subject": subj,
            "label": SUBJECT_LABEL[subj],
            "advice": "".join(advice) or "保持稳定, 继续巩固. ",
            "level": level,
            "current": v,
            "avg": avg,
            "rank": my_rank,
            "full": full,
        })
    return advice_list


def detect_alerts():
    """成绩智能预警: 连续退步 + 单科大幅下滑

    返回:
        {
            "consecutive_drop": [{student_id, name, ranks, exam_names, total_delta}],
            "subject_slump": [{student_id, name, subject, label, prev_score, cur_score, delta}],
            "exams": [Exam],  # 参与分析的考试
        }
    """
    from app.models import Exam, Student
    from app.utils.ranking import compute_class_rank, display_rank

    # 最近 3 次考试(按时间正序)
    exams = Exam.query.order_by(Exam.exam_date.desc()).limit(3).all()
    exams = list(reversed(exams))
    if len(exams) < 2:
        return {"consecutive_drop": [], "subject_slump": [], "exams": exams}

    # 每次考试的记录 {exam_id: {student_id: ScoreRecord}}
    exam_records = {}
    for e in exams:
        recs = ScoreRecord.query.filter_by(exam_id=e.id).all()
        compute_class_rank(recs)
        exam_records[e.id] = {r.student_id: r for r in recs}

    students = Student.query.all()

    # 1. 连续退步: 最近 3 次排名连续下降(数字增大)
    consecutive_drop = []
    if len(exams) >= 3:
        e1, e2, e3 = exams
        for s in students:
            r1 = exam_records[e1.id].get(s.id)
            r2 = exam_records[e2.id].get(s.id)
            r3 = exam_records[e3.id].get(s.id)
            if not (r1 and r2 and r3):
                continue
            rk1 = display_rank(r1)
            rk2 = display_rank(r2)
            rk3 = display_rank(r3)
            if rk1 is not None and rk2 is not None and rk3 is not None:
                # 排名连续下降(数字增大=退步)
                if rk1 < rk2 < rk3:
                    total_delta = None
                    if r1.total is not None and r3.total is not None:
                        total_delta = round(r3.total - r1.total, 1)
                    consecutive_drop.append({
                        "student_id": s.id,
                        "name": s.name,
                        "ranks": [rk1, rk2, rk3],
                        "exam_names": [e1.name, e2.name, e3.name],
                        "total_delta": total_delta,
                    })

    # 2. 单科大幅下滑: 最近 2 次, 某科下滑超过 15 分
    subject_slump = []
    if len(exams) >= 2:
        prev_e, cur_e = exams[-2], exams[-1]
        prev_map = exam_records[prev_e.id]
        cur_map = exam_records[cur_e.id]
        for s in students:
            pr = prev_map.get(s.id)
            cr = cur_map.get(s.id)
            if not (pr and cr):
                continue
            for subj in ScoreRecord.SUBJECTS:
                pv = getattr(pr, subj)
                cv = getattr(cr, subj)
                if pv is not None and cv is not None:
                    delta = round(cv - pv, 1)
                    if delta <= -15:
                        subject_slump.append({
                            "student_id": s.id,
                            "name": s.name,
                            "subject": subj,
                            "label": SUBJECT_LABEL.get(subj, subj),
                            "prev_score": pv,
                            "cur_score": cv,
                            "delta": delta,
                        })

    return {
        "consecutive_drop": consecutive_drop,
        "subject_slump": subject_slump,
        "exams": exams,
    }
