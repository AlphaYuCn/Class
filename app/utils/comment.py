"""学生评语自动生成
基于学生成绩(进步/退步) + 日常记录(违纪/表扬次数) + 性格特点
套用模板拼装生成结构化中文评语初稿, 供班主任修改。
"""
from collections import Counter
from app.models import ScoreRecord, DailyRecord, Exam
from app.utils.ranking import display_rank, rank_delta_value


def generate_comment(student, term: str) -> str:
    """生成评语初稿
    student: Student 实例
    term: 学期标识(如 "2025秋季")
    返回: 评语正文 str
    """
    name = student.name or "该生"
    parts = []

    # ---------- 1. 开篇: 性别+性格概览 ----------
    gender = "该男生" if student.gender == "M" else "该女生" if student.gender == "F" else "该生"
    parts.append(f"{gender}{name}, ")

    # ---------- 2. 成绩表现 ----------
    records = (ScoreRecord.query
                .join(Exam)
                .filter(ScoreRecord.student_id == student.id)
                .order_by(Exam.exam_date.asc()).all())
    if records:
        latest = records[-1]
        # 分档用班级排名(分母为班级人数); 进步/退步优先年级排名
        rank = latest.class_rank or 0
        display = display_rank(latest) or rank
        total_students = ScoreRecord.query.filter_by(exam_id=latest.exam_id).count()
        # 进步/退步判断(优先年级排名, 回退班级排名)
        progress_word = "成绩稳定"
        if len(records) >= 2:
            prev = records[-2]
            delta = rank_delta_value(prev, latest)  # 正数=进步
            if delta is not None and delta > 5:
                progress_word = f"本学期进步显著(排名上升{delta}名)"
            elif delta is not None and delta < -5:
                progress_word = f"本学期成绩有所下滑(排名下降{-delta}名), 需关注"
            else:
                progress_word = "成绩保持稳定"
        # 排名分档(按班级百分比)
        if total_students > 0:
            pct = (rank / total_students) * 100
            if pct <= 25:
                level_word = f"名列前茅(排名第{display}名/{total_students}人)"
            elif pct <= 50:
                level_word = f"中上水平(排名第{display}名/{total_students}人)"
            elif pct <= 75:
                level_word = f"中等水平(排名第{display}名/{total_students}人)"
            else:
                level_word = f"暂时落后(排名第{display}名/{total_students}人), 有较大提升空间"
            parts.append(f"{progress_word}, {level_word}。")

        # 偏科诊断
        subjects = ["chinese", "math", "english", "physics", "chemistry",
                    "biology", "politics", "history", "geography"]
        subject_scores = [(s, getattr(latest, s)) for s in subjects
                          if getattr(latest, s) is not None]
        if subject_scores:
            subject_scores.sort(key=lambda x: x[1])
            weak_subj = subject_scores[0]
            strong_subj = subject_scores[-1]
            subj_label = {
                "chinese": "语文", "math": "数学", "english": "英语",
                "physics": "物理", "chemistry": "化学", "biology": "生物",
                "politics": "政治", "history": "历史", "geography": "地理",
            }
            parts.append(f"优势科目为{subj_label[strong_subj[0]]}, "
                         f"薄弱科目为{subj_label[weak_subj[0]]}, 建议针对性提升。")
    else:
        parts.append("本学期暂无成绩记录。")

    # ---------- 3. 日常表现 ----------
    daily = (DailyRecord.query
             .filter_by(student_id=student.id).all())
    type_count = Counter(r.record_type for r in daily)
    praise_count = type_count.get("praise", 0) + type_count.get("reward", 0)
    punish_count = (type_count.get("late", 0) + type_count.get("discipline", 0)
                    + type_count.get("distraction", 0) + type_count.get("leave", 0))
    if praise_count and not punish_count:
        parts.append(f"日常表现良好, 共获表扬/奖励{praise_count}次, 遵守纪律, 是同学的榜样。")
    elif punish_count and not praise_count:
        parts.append(f"日常记录违纪{punish_count}次, 需加强纪律意识和自我管理。")
    elif praise_count and punish_count:
        parts.append(f"日常表现有起伏: 获表扬{praise_count}次, 也有违纪{punish_count}次, "
                     "建议发扬优点, 改进不足。")
    else:
        parts.append("日常表现平稳, 无明显违纪记录。")

    # ---------- 4. 结尾鼓励 ----------
    parts.append("望今后继续努力, 扬长避短, 取得更大进步。")

    return "".join(parts)


if __name__ == "__main__":
    # 测试
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.models import Student
        s = Student.query.first()
        if s:
            print(f"--- {s.name} 评语初稿 ---")
            print(generate_comment(s, "2025秋季"))
