"""成绩信息蓝图 (模块2)"""
from io import BytesIO
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, \
    flash, send_file, jsonify, abort
from sqlalchemy import or_

from app.extensions import db
from app.models import Student, Exam, ScoreRecord, ScoreGoal, StudentComment, \
    ExamQuestion, QuestionScore, KnowledgePoint, GradeBenchmark
from app.utils.excel import build_score_template, parse_score_excel
from app.utils.ranking import compute_class_rank, score_segments, subject_stats, subject_rank, rank_delta_value, display_rank
from app.utils.suggestion import compare_exams, SUBJECT_LABEL, SUBJECT_FULL, detect_alerts

scores_bp = Blueprint("scores", __name__)


@scores_bp.route("/")
def index():
    exams = Exam.query.order_by(Exam.exam_date.desc()).all()
    count_map = {e.id: ScoreRecord.query.filter_by(exam_id=e.id).count() for e in exams}
    # 成绩智能预警
    alerts = detect_alerts()
    return render_template("scores/index.html", exams=exams, count_map=count_map,
                            alerts=alerts)


@scores_bp.route("/template")
def template():
    data = build_score_template()
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name="成绩单模板.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@scores_bp.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("file")
        exam_name = request.form.get("exam_name", "").strip()
        exam_date_str = request.form.get("exam_date", "").strip()
        if not file or not file.filename:
            flash("请选择 Excel 文件", "warning")
            return redirect(url_for("scores.upload"))
        try:
            data = file.read()
            records = parse_score_excel(data)
        except Exception as e:
            flash(f"解析失败: {e}", "danger")
            return redirect(url_for("scores.upload"))

        # 解析考试日期
        try:
            ed = datetime.strptime(exam_date_str, "%Y-%m-%d").date() if exam_date_str else date.today()
        except ValueError:
            flash("考试日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("scores.upload"))
        # 默认考试名
        if not exam_name:
            exam_name = f"{ed.year}年{ed.month}月考试"
        # 创建 exam
        exam = Exam(name=exam_name, exam_date=ed, year=ed.year, month=ed.month)
        db.session.add(exam)
        db.session.flush()

        # 学号 -> student
        added, skipped = 0, 0
        all_records = []
        for rec in records:
            s = Student.query.filter_by(student_no=rec["student_no"]).first()
            if not s:
                skipped += 1
                continue
            r = ScoreRecord(
                exam_id=exam.id,
                student_id=s.id,
                total=rec["total"],
                class_rank=rec["class_rank"],
                grade_rank=rec["grade_rank"],
            )
            for subj, v in rec["subjects"].items():
                setattr(r, subj, v)
            all_records.append(r)
            db.session.add(r)
            added += 1
        # 补算班级排名
        compute_class_rank(all_records)
        db.session.commit()
        flash(f"考试「{exam_name}」导入完成: 写入 {added} 条成绩, 跳过 {skipped} 个未注册学生", "success")
        return redirect(url_for("scores.overview", eid=exam.id))
    return render_template("scores/upload.html")


@scores_bp.route("/exam/<int:eid>")
def overview(eid):
    exam = Exam.query.get_or_404(eid)
    records = ScoreRecord.query.filter_by(exam_id=eid).all()
    if not records:
        flash("本次考试暂无成绩数据", "warning")
        return redirect(url_for("scores.index"))
    # 上一场考试
    prev_exam = (Exam.query.filter(Exam.exam_date < exam.exam_date)
                  .order_by(Exam.exam_date.desc()).first())
    # 排名补算
    compute_class_rank(records)
    # 排序按 class_rank
    records.sort(key=lambda r: (r.class_rank or 9999, r.student_id))
    # 分段
    segs = score_segments(records, bin_width=10, full_score=750)
    # 各科统计
    stats = subject_stats(records)
    return render_template("scores/overview.html", exam=exam, records=records,
                            segs=segs, stats=stats, prev_exam=prev_exam)


@scores_bp.route("/exam/<int:eid>/student/<int:sid>")
def detail(eid, sid):
    exam = Exam.query.get_or_404(eid)
    s = Student.query.get_or_404(sid)
    cur = ScoreRecord.query.filter_by(exam_id=eid, student_id=sid).first_or_404()
    # 上一场考试
    prev_exam = (Exam.query.filter(Exam.exam_date < exam.exam_date)
                  .order_by(Exam.exam_date.desc()).first())
    prev = None
    all_prev_records = None
    if prev_exam:
        prev = ScoreRecord.query.filter_by(exam_id=prev_exam.id, student_id=sid).first()
        all_prev_records = ScoreRecord.query.filter_by(exam_id=prev_exam.id).all()
    all_cur_records = ScoreRecord.query.filter_by(exam_id=eid).all()
    compare = compare_exams(cur, prev, all_cur_records, all_prev_records)
    return render_template("scores/detail.html", exam=exam, s=s, cur=cur,
                            prev=prev, prev_exam=prev_exam, compare=compare)


@scores_bp.route("/exam/<int:eid>/student/<int:sid>/report")
def report(eid, sid):
    """个人成绩单打印版（家长会专用）"""
    exam = Exam.query.get_or_404(eid)
    s = Student.query.get_or_404(sid)
    cur = ScoreRecord.query.filter_by(exam_id=eid, student_id=sid).first_or_404()
    all_records = ScoreRecord.query.filter_by(exam_id=eid).all()
    compute_class_rank(all_records)
    stats = subject_stats(all_records)
    # 历次成绩
    history = (ScoreRecord.query
               .join(Exam)
               .filter(ScoreRecord.student_id == sid)
               .order_by(Exam.exam_date.asc()).all())
    # 最新评语
    from app.models import StudentComment
    latest_comment = (StudentComment.query
                      .filter_by(student_id=sid)
                      .order_by(StudentComment.term.desc()).first())
    return render_template("scores/report.html", exam=exam, s=s, cur=cur,
                            stats=stats, history=history,
                            latest_comment=latest_comment,
                            subject_label=SUBJECT_LABEL, subject_full=SUBJECT_FULL)


@scores_bp.route("/exam/<int:eid>/student/<int:sid>/diagnosis")
def diagnosis(eid, sid):
    """偏科诊断: 各科与班级均分偏差分析"""
    exam = Exam.query.get_or_404(eid)
    s = Student.query.get_or_404(sid)
    cur = ScoreRecord.query.filter_by(exam_id=eid, student_id=sid).first_or_404()
    all_records = ScoreRecord.query.filter_by(exam_id=eid).all()
    compute_class_rank(all_records)
    stats = subject_stats(all_records)
    subjects = ScoreRecord.SUBJECTS
    # 构建诊断数据
    diag = []
    for subj in subjects:
        sv = getattr(cur, subj)
        if sv is None:
            continue
        avg = stats[subj]["avg"]
        full = SUBJECT_FULL[subj]
        rate = sv / full * 100 if full else 0
        avg_rate = (avg / full * 100) if avg and full else 0
        diff = sv - avg if avg else 0
        # 偏科判定: 得分率低于均分得分率 10% 以上 = 薄弱
        if rate < avg_rate - 10:
            status = "weak"
        elif rate > avg_rate + 5:
            status = "strong"
        else:
            status = "normal"
        diag.append({
            "subject": subj,
            "label": SUBJECT_LABEL[subj],
            "score": sv,
            "full": full,
            "avg": avg,
            "rate": rate,
            "avg_rate": avg_rate,
            "diff": diff,
            "rank": subject_rank(all_records, subj).get(sid),
            "status": status,
        })
    # 按偏差升序排(偏差最大的薄弱科目在前)
    diag.sort(key=lambda x: x["diff"])
    weak = [d for d in diag if d["status"] == "weak"]
    strong = [d for d in diag if d["status"] == "strong"]
    return render_template("scores/diagnosis.html", exam=exam, s=s, cur=cur,
                            diag=diag, weak=weak, strong=strong,
                            subject_label=SUBJECT_LABEL,
                            subject_full=SUBJECT_FULL)


# ---------- JSON API ----------
@scores_bp.route("/api/exam/<int:eid>/histogram")
def api_histogram(eid):
    records = ScoreRecord.query.filter_by(exam_id=eid).all()
    compute_class_rank(records)
    segs = score_segments(records, bin_width=10, full_score=750)
    return jsonify({
        "categories": [s["range"] for s in segs],
        "counts": [s["count"] for s in segs],
        "segments": segs,
    })


@scores_bp.route("/api/exam/<int:eid>/subject-bar")
def api_subject_bar(eid):
    records = ScoreRecord.query.filter_by(exam_id=eid).all()
    stats = subject_stats(records)
    cats = [SUBJECT_LABEL[k] for k in ["chinese", "math", "english", "physics",
                                          "chemistry", "biology", "politics",
                                          "history", "geography"]]
    avgs = [stats[k]["avg"] if stats[k]["avg"] is not None else 0
             for k in ["chinese", "math", "english", "physics",
                        "chemistry", "biology", "politics",
                        "history", "geography"]]
    maxs = [stats[k]["max"] if stats[k]["max"] is not None else 0
             for k in ["chinese", "math", "english", "physics",
                        "chemistry", "biology", "politics",
                        "history", "geography"]]
    mins = [stats[k]["min"] if stats[k]["min"] is not None else 0
             for k in ["chinese", "math", "english", "physics",
                        "chemistry", "biology", "politics",
                        "history", "geography"]]
    return jsonify({
        "categories": cats,
        "avg": avgs,
        "max": maxs,
        "min": mins,
    })


@scores_bp.route("/api/exam/<int:eid>/student/<int:sid>/radar")
def api_radar(eid, sid):
    from app.utils.suggestion import SUBJECT_FULL
    records = ScoreRecord.query.filter_by(exam_id=eid).all()
    cur = ScoreRecord.query.filter_by(exam_id=eid, student_id=sid).first_or_404()
    stats = subject_stats(records)
    subjects = ["chinese", "math", "english", "physics", "chemistry",
                 "biology", "politics", "history", "geography"]
    indicators = [{"name": SUBJECT_LABEL[k], "max": SUBJECT_FULL[k]} for k in subjects]
    personal = [getattr(cur, k) or 0 for k in subjects]
    avg = [stats[k]["avg"] or 0 for k in subjects]
    return jsonify({
        "indicators": indicators,
        "personal": personal,
        "avg": avg,
        "studentId": sid,
        "studentName": cur.student.name,
    })


@scores_bp.route("/api/exam/<int:eid>/student/<int:sid>/compare")
def api_compare(eid, sid):
    cur = ScoreRecord.query.filter_by(exam_id=eid, student_id=sid).first_or_404()
    prev_exam = (Exam.query.filter(Exam.exam_date < cur.exam.exam_date)
                  .order_by(Exam.exam_date.desc()).first())
    prev = None
    if prev_exam:
        prev = ScoreRecord.query.filter_by(exam_id=prev_exam.id, student_id=sid).first()
    all_cur = ScoreRecord.query.filter_by(exam_id=eid).all()
    all_prev = ScoreRecord.query.filter_by(exam_id=prev_exam.id).all() if prev_exam else None
    compare = compare_exams(cur, prev, all_cur, all_prev)
    return jsonify(compare)


# ---------- 成绩趋势 ----------
@scores_bp.route("/trend/<int:sid>")
def trend(sid):
    s = Student.query.get_or_404(sid)
    # 历次成绩(按考试日期升序)
    records = (ScoreRecord.query
               .join(Exam)
               .filter(ScoreRecord.student_id == sid)
               .order_by(Exam.exam_date.asc()).all())
    return render_template("scores/trend.html", s=s, records=records)


@scores_bp.route("/api/trend/<int:sid>")
def api_trend(sid):
    s = Student.query.get_or_404(sid)
    records = (ScoreRecord.query
               .join(Exam)
               .filter(ScoreRecord.student_id == sid)
               .order_by(Exam.exam_date.asc()).all())
    if not records:
        return jsonify({"exams": [], "series": [], "studentName": s.name})
    subjects = ["chinese", "math", "english", "physics", "chemistry",
                "biology", "politics", "history", "geography"]
    exams = [{"name": r.exam.name, "date": r.exam.exam_date.isoformat(),
              "id": r.exam_id} for r in records]
    series = []
    # 总分
    series.append({"name": "总分", "data": [r.total for r in records]})
    # 年级排名(优先, 回退班级排名)
    series.append({"name": "年级排名", "data": [r.grade_rank if r.grade_rank is not None else r.class_rank for r in records]})
    # 各科
    for subj in subjects:
        series.append({"name": SUBJECT_LABEL[subj],
                       "data": [getattr(r, subj) for r in records]})
    return jsonify({"exams": exams, "series": series,
                    "studentName": s.name, "studentId": sid})


# ---------- 班级进步榜 ----------
@scores_bp.route("/ranking")
def ranking():
    exams = Exam.query.order_by(Exam.exam_date.desc()).limit(5).all()
    return render_template("scores/ranking.html", exams=exams)


@scores_bp.route("/api/ranking")
def api_ranking():
    """进步榜+退步榜(以最近两次考试对比)"""
    exam_id = request.args.get("eid", type=int)
    if exam_id:
        cur_exam = Exam.query.get_or_404(exam_id)
    else:
        cur_exam = Exam.query.order_by(Exam.exam_date.desc()).first()
    if not cur_exam:
        return jsonify({"progress": [], "regress": [], "examName": ""})
    prev_exam = (Exam.query.filter(Exam.exam_date < cur_exam.exam_date)
                  .order_by(Exam.exam_date.desc()).first())
    if not prev_exam:
        return jsonify({"progress": [], "regress": [],
                        "examName": cur_exam.name, "prevName": None})
    # 全班对比
    cur_records = {r.student_id: r for r in
                   ScoreRecord.query.filter_by(exam_id=cur_exam.id).all()}
    prev_records = {r.student_id: r for r in
                    ScoreRecord.query.filter_by(exam_id=prev_exam.id).all()}
    students = Student.query.all()
    sid_to_student = {s.id: s for s in students}
    deltas = []
    for sid, cur_r in cur_records.items():
        prev_r = prev_records.get(sid)
        if not prev_r or prev_r.total is None or cur_r.total is None:
            continue
        delta = cur_r.total - prev_r.total
        # 排名升降: 优先年级排名(学校排名), 回退班级排名
        rank_delta = rank_delta_value(prev_r, cur_r)
        if rank_delta is None:
            rank_delta = 0
        # 展示排名: 优先年级排名, 回退班级排名
        prev_rank = display_rank(prev_r)
        cur_rank = display_rank(cur_r)
        deltas.append({
            "studentId": sid,
            "studentName": sid_to_student[sid].name,
            "studentNo": sid_to_student[sid].student_no,
            "prevTotal": prev_r.total,
            "curTotal": cur_r.total,
            "delta": delta,
            "prevRank": prev_rank,
            "curRank": cur_rank,
            "prevClassRank": prev_r.class_rank,
            "curClassRank": cur_r.class_rank,
            "prevGradeRank": prev_r.grade_rank,
            "curGradeRank": cur_r.grade_rank,
            "rankDelta": rank_delta,
        })
    # 进步榜: rankDelta 降序(进步名次最多)
    progress = sorted(deltas, key=lambda x: x["rankDelta"], reverse=True)[:10]
    # 退步榜: rankDelta 升序
    regress = sorted(deltas, key=lambda x: x["rankDelta"])[:10]
    return jsonify({
        "progress": progress,
        "regress": regress,
        "all": deltas,  # 班级全员升降数据
        "examName": cur_exam.name,
        "prevName": prev_exam.name,
        "total": len(deltas),
    })


# ---------- 目标成绩管理 ----------
def _current_term():
    today = date.today()
    if today.month >= 8:
        return f"{today.year}秋季"
    elif today.month >= 2:
        return f"{today.year}春季"
    else:
        return f"{today.year - 1}秋季"


@scores_bp.route("/goal")
def goal_list():
    """目标成绩管理主页"""
    term = request.args.get("term", _current_term())
    students = Student.query.order_by(Student.student_no).all()
    goals = {g.student_id: g for g in ScoreGoal.query.filter_by(term=term).all()}
    # 该学期每次考试
    exams = (Exam.query
             .filter(Exam.exam_date >= date(int(term[:4]), 8, 1) if term.endswith("秋季")
                     else Exam.exam_date >= date(int(term[:4]), 2, 1))
             .order_by(Exam.exam_date.asc()).all()) if term else []
    return render_template("scores/goal_list.html", students=students,
                            goals=goals, term=term,
                            current_term=_current_term(),
                            exams=exams,
                            subject_label=SUBJECT_LABEL)


@scores_bp.route("/goal/<int:sid>", methods=["GET", "POST"])
def goal_edit(sid):
    """编辑学生目标成绩"""
    s = Student.query.get_or_404(sid)
    term = request.args.get("term", _current_term())
    if request.method == "POST":
        new_term = request.form.get("term", term).strip() or term
        g = ScoreGoal.query.filter_by(student_id=sid, term=new_term).first()
        if not g:
            g = ScoreGoal(student_id=sid, term=new_term)
            db.session.add(g)
        for subj in ScoreGoal.SUBJECTS:
            v = request.form.get(subj, "").strip()
            try:
                setattr(g, subj, float(v) if v else None)
            except ValueError:
                pass
        total_v = request.form.get("total", "").strip()
        try:
            g.total = float(total_v) if total_v else None
        except ValueError:
            g.total = None
        rank_v = request.form.get("class_rank_target", "").strip()
        try:
            g.class_rank_target = int(rank_v) if rank_v else None
        except ValueError:
            g.class_rank_target = None
        g.note = request.form.get("note", "").strip() or None
        db.session.commit()
        flash(f"{s.name} 的 {new_term} 目标已保存", "success")
        return redirect(url_for("scores.goal_edit", sid=sid, term=new_term))
    g = ScoreGoal.query.filter_by(student_id=sid, term=term).first()
    # 最新一次成绩作为参考
    latest = (ScoreRecord.query
              .join(Exam)
              .filter(ScoreRecord.student_id == sid)
              .order_by(Exam.exam_date.desc()).first())
    # 预计算科目数据(避免模板调用getattr)
    subject_data = []
    for subj in ScoreGoal.SUBJECTS:
        subject_data.append({
            "key": subj,
            "label": SUBJECT_LABEL[subj],
            "full": SUBJECT_FULL[subj],
            "target": getattr(g, subj) if g else None,
            "actual": getattr(latest, subj) if latest else None,
        })
    return render_template("scores/goal_edit.html", s=s, g=g, term=term,
                            current_term=_current_term(),
                            latest=latest,
                            subject_data=subject_data,
                            subjects=ScoreGoal.SUBJECTS,
                            subject_label=SUBJECT_LABEL,
                            subject_full=SUBJECT_FULL)


@scores_bp.route("/goal/<int:sid>/compare")
def goal_compare(sid):
    """目标 vs 实际对比"""
    s = Student.query.get_or_404(sid)
    term = request.args.get("term", _current_term())
    g = ScoreGoal.query.filter_by(student_id=sid, term=term).first()
    # 该学期历次成绩
    records = (ScoreRecord.query
               .join(Exam)
               .filter(ScoreRecord.student_id == sid)
               .order_by(Exam.exam_date.asc()).all())
    # 过滤该学期的
    term_records = []
    for r in records:
        if r.exam.exam_date:
            y = r.exam.exam_date.year
            m = r.exam.exam_date.month
            if term.endswith("秋季") and (m >= 8 or (y == int(term[:4]) + 1 and m <= 1)):
                term_records.append(r)
            elif term.endswith("春季") and (m >= 2 and m <= 7):
                term_records.append(r)
    latest = term_records[-1] if term_records else None
    # 预计算科目对比数据
    subject_data = []
    for subj in ScoreRecord.SUBJECTS:
        subject_data.append({
            "key": subj,
            "label": SUBJECT_LABEL[subj],
            "full": SUBJECT_FULL[subj],
            "target": getattr(g, subj) if g else None,
            "actual": getattr(latest, subj) if latest else None,
        })
    return render_template("scores/goal_compare.html", s=s, g=g, term=term,
                            latest=latest, term_records=term_records,
                            subject_data=subject_data,
                            subjects=ScoreRecord.SUBJECTS,
                            subject_label=SUBJECT_LABEL,
                            subject_full=SUBJECT_FULL)


# ---------- 历次考试班级趋势 ----------
@scores_bp.route("/class-trend")
def class_trend():
    """班级历次考试趋势"""
    exams = Exam.query.order_by(Exam.exam_date.asc()).all()
    return render_template("scores/class_trend.html", exams=exams)


@scores_bp.route("/api/class-trend")
def api_class_trend():
    """班级历次考试均分/最高分/各科均分趋势"""
    exams = Exam.query.order_by(Exam.exam_date.asc()).all()
    if not exams:
        return jsonify({"exams": [], "series": []})
    subjects = ScoreRecord.SUBJECTS
    exam_labels = [e.name for e in exams]
    # 计算每次考试的统计
    total_avg = []
    total_max = []
    total_min = []
    subject_avg_series = {subj: [] for subj in subjects}
    for e in exams:
        records = ScoreRecord.query.filter_by(exam_id=e.id).all()
        totals = [r.total for r in records if r.total is not None]
        total_avg.append(round(sum(totals) / len(totals), 1) if totals else None)
        total_max.append(max(totals) if totals else None)
        total_min.append(min(totals) if totals else None)
        stats = subject_stats(records)
        for subj in subjects:
            v = stats[subj]["avg"] if stats[subj]["avg"] is not None else None
            subject_avg_series[subj].append(v)
    series = [
        {"name": "总分均分", "data": total_avg, "type": "line"},
        {"name": "总分最高", "data": total_max, "type": "line"},
        {"name": "总分最低", "data": total_min, "type": "line"},
    ]
    for subj in subjects:
        series.append({"name": SUBJECT_LABEL[subj],
                       "data": subject_avg_series[subj], "type": "line"})
    return jsonify({
        "exams": exam_labels,
        "examDates": [e.exam_date.isoformat() for e in exams],
        "series": series,
    })


# ---------- 学科均衡度分析 ----------
@scores_bp.route("/balance/<int:eid>")
def balance(eid):
    """学科均衡度分析: 全班各科标准差/极差 + 个人均衡度排行"""
    exam = Exam.query.get_or_404(eid)
    records = ScoreRecord.query.filter_by(exam_id=eid).all()
    compute_class_rank(records)
    stats = subject_stats(records)
    subjects = ScoreRecord.SUBJECTS
    # 计算每个学生的均衡度（变异系数CV = std/mean）
    student_balance = []
    for r in records:
        s_scores = r.subject_scores()
        if len(s_scores) < 2:
            continue
        vals = list(s_scores.values())
        mean_v = sum(vals) / len(vals)
        # 计算标准差
        variance = sum((v - mean_v) ** 2 for v in vals) / len(vals)
        std_v = variance ** 0.5
        cv = std_v / mean_v * 100 if mean_v > 0 else 0  # 变异系数%
        # 极差
        rng = max(vals) - min(vals)
        student_balance.append({
            "student": r.student,
            "score_record": r,
            "cv": round(cv, 1),
            "std": round(std_v, 1),
            "range": round(rng, 1),
            "min_subj": min(s_scores, key=s_scores.get),
            "max_subj": max(s_scores, key=s_scores.get),
            "min_score": min(vals),
            "max_score": max(vals),
        })
    # 按CV升序（CV越小越均衡）
    student_balance.sort(key=lambda x: x["cv"])
    # 各科均衡度（统计各科std）
    subject_balance = []
    for subj in subjects:
        st = stats[subj]
        if st["avg"] is None:
            continue
        vals = [getattr(r, subj) for r in records if getattr(r, subj) is not None]
        if not vals:
            continue
        mean_v = sum(vals) / len(vals)
        variance = sum((v - mean_v) ** 2 for v in vals) / len(vals)
        std_v = variance ** 0.5
        cv = std_v / mean_v * 100 if mean_v > 0 else 0
        subject_balance.append({
            "subject": subj,
            "label": SUBJECT_LABEL[subj],
            "avg": round(mean_v, 1),
            "std": round(std_v, 1),
            "cv": round(cv, 1),
            "max": st["max"],
            "min": st["min"],
            "range": round(st["max"] - st["min"], 1) if st["max"] and st["min"] else None,
            "full": SUBJECT_FULL[subj],
        })
    return render_template("scores/balance.html", exam=exam,
                            student_balance=student_balance,
                            subject_balance=subject_balance,
                            subject_label=SUBJECT_LABEL,
                            subject_full=SUBJECT_FULL)


@scores_bp.route("/api/balance/<int:eid>")
def api_balance(eid):
    """学科均衡度JSON API: 各科箱线图数据"""
    records = ScoreRecord.query.filter_by(exam_id=eid).all()
    subjects = ScoreRecord.SUBJECTS
    box_data = []
    for subj in subjects:
        vals = sorted([getattr(r, subj) for r in records if getattr(r, subj) is not None])
        if not vals:
            continue
        n = len(vals)
        # 四分位数
        def quantile(data, q):
            if not data:
                return None
            idx = q * (len(data) - 1)
            lo = int(idx)
            hi = min(lo + 1, len(data) - 1)
            frac = idx - lo
            return data[lo] + (data[hi] - data[lo]) * frac
        box_data.append({
            "name": SUBJECT_LABEL[subj],
            "subject": subj,
            "min": round(vals[0], 1),
            "q1": round(quantile(vals, 0.25), 1),
            "median": round(quantile(vals, 0.5), 1),
            "q3": round(quantile(vals, 0.75), 1),
            "max": round(vals[-1], 1),
            "full": SUBJECT_FULL[subj],
        })
    return jsonify({"boxes": box_data})


# ==================== 试卷逐题分析 ====================
@scores_bp.route("/exam/<int:eid>/questions", methods=["GET", "POST"])
def question_list(eid):
    """试卷题目管理: 录入题目, 显示题目列表"""
    exam = Exam.query.get_or_404(eid)
    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        question_no = request.form.get("question_no", "").strip()
        full_score_str = request.form.get("full_score", "").strip()
        knowledge_points = request.form.get("knowledge_points", "").strip()
        question_type = request.form.get("question_type", "").strip()
        if not subject or not question_no:
            flash("科目和题号必填", "danger")
            return redirect(url_for("scores.question_list", eid=eid))
        try:
            full_score = float(full_score_str) if full_score_str else 0
        except ValueError:
            flash("满分需为数字", "danger")
            return redirect(url_for("scores.question_list", eid=eid))
        # 检查重复
        existing = ExamQuestion.query.filter_by(exam_id=eid, subject=subject, question_no=question_no).first()
        if existing:
            flash(f"题目 {subject}-{question_no} 已存在", "warning")
            return redirect(url_for("scores.question_list", eid=eid))
        q = ExamQuestion(exam_id=eid, subject=subject, question_no=question_no,
                          full_score=full_score, knowledge_points=knowledge_points or None,
                          question_type=question_type or None)
        db.session.add(q)
        db.session.commit()
        flash(f"已添加题目 {SUBJECT_LABEL.get(subject, subject)} {question_no}", "success")
        return redirect(url_for("scores.question_list", eid=eid))
    # 按科目分组
    questions = (ExamQuestion.query.filter_by(exam_id=eid)
                  .order_by(ExamQuestion.subject, ExamQuestion.question_no).all())
    subjects = ScoreRecord.SUBJECTS
    # 题数统计
    question_count = {subj: sum(1 for q in questions if q.subject == subj) for subj in subjects}
    # 已录学生得分数
    scored_students = {q.id: QuestionScore.query.filter_by(question_id=q.id).count() for q in questions}
    return render_template("scores/question_list.html", exam=exam, questions=questions,
                            subjects=subjects, subject_label=SUBJECT_LABEL,
                            question_count=question_count, scored_students=scored_students)


@scores_bp.route("/exam/<int:eid>/question/<int:qid>/scores", methods=["GET", "POST"])
def question_scores(eid, qid):
    """录入每生每题得分"""
    exam = Exam.query.get_or_404(eid)
    q = ExamQuestion.query.get_or_404(qid)
    if q.exam_id != eid:
        abort(404)
    if request.method == "POST":
        # 表单字段：score_<student_id> = 得分
        added, updated, skipped = 0, 0, 0
        for key, value in request.form.items():
            if not key.startswith("score_"):
                continue
            try:
                sid = int(key[6:])
            except ValueError:
                continue
            value = value.strip()
            if not value:
                # 空值: 删除已存在记录
                qs = QuestionScore.query.filter_by(question_id=qid, student_id=sid).first()
                if qs:
                    db.session.delete(qs)
                continue
            try:
                score_v = float(value)
            except ValueError:
                skipped += 1
                continue
            if score_v < 0 or score_v > q.full_score:
                skipped += 1
                continue
            qs = QuestionScore.query.filter_by(question_id=qid, student_id=sid).first()
            if qs:
                qs.score = score_v
                updated += 1
            else:
                db.session.add(QuestionScore(question_id=qid, student_id=sid, score=score_v))
                added += 1
        db.session.commit()
        flash(f"已保存: 新增 {added} 条, 更新 {updated} 条, 跳过 {skipped} 条无效", "success")
        return redirect(url_for("scores.question_scores", eid=eid, qid=qid))
    students = Student.query.order_by(Student.student_no).all()
    # 已录得分映射
    score_map = {qs.student_id: qs.score for qs in QuestionScore.query.filter_by(question_id=qid).all()}
    return render_template("scores/question_scores.html", exam=exam, q=q,
                            students=students, score_map=score_map,
                            subject_label=SUBJECT_LABEL)


@scores_bp.route("/exam/<int:eid>/question-report")
def question_report(eid):
    """试卷质量报告: 得分率/区分度/易错题"""
    exam = Exam.query.get_or_404(eid)
    questions = (ExamQuestion.query.filter_by(exam_id=eid)
                  .order_by(ExamQuestion.subject, ExamQuestion.question_no).all())
    if not questions:
        flash("请先录入试卷题目", "warning")
        return redirect(url_for("scores.question_list", eid=eid))
    # 计算每题统计
    report = []
    for q in questions:
        scores = QuestionScore.query.filter_by(question_id=q.id).all()
        n = len(scores)
        if n == 0:
            report.append({
                "question": q, "n": 0, "avg": None, "rate": None,
                "std": None, "discrim": None, "easy_error": None,
            })
            continue
        vals = [s.score for s in scores]
        avg_v = sum(vals) / n
        rate = avg_v / q.full_score if q.full_score > 0 else 0
        variance = sum((v - avg_v) ** 2 for v in vals) / n
        std_v = variance ** 0.5
        # 区分度: 用高低分组差异法
        sorted_vals = sorted(vals)
        third = max(1, n // 3)
        high = sorted_vals[-third:]
        low = sorted_vals[:third]
        high_avg = sum(high) / len(high) if high else 0
        low_avg = sum(low) / len(low) if low else 0
        discrim = (high_avg - low_avg) / q.full_score if q.full_score > 0 else 0
        # 易错题: 得分率 < 0.6 视为易错
        easy_error = rate < 0.6
        report.append({
            "question": q, "n": n,
            "avg": round(avg_v, 1), "rate": round(rate * 100, 1),
            "std": round(std_v, 1), "discrim": round(discrim, 2),
            "easy_error": easy_error,
        })
    # 按易错排序
    easy_errors = [r for r in report if r["easy_error"]]
    # 总览
    total_questions = len(questions)
    total_scored = sum(1 for r in report if r["n"] > 0)
    return render_template("scores/question_report.html", exam=exam, report=report,
                            easy_errors=easy_errors, subject_label=SUBJECT_LABEL,
                            total_questions=total_questions, total_scored=total_scored)


# ==================== 知识点掌握度分析 ====================
@scores_bp.route("/exam/<int:eid>/knowledge")
def knowledge_analysis(eid):
    """基于题目标注的知识点分析掌握度"""
    exam = Exam.query.get_or_404(eid)
    questions = (ExamQuestion.query.filter_by(exam_id=eid)
                  .filter(ExamQuestion.knowledge_points.isnot(None)).all())
    if not questions:
        flash("请先录入题目并标注知识点", "warning")
        return redirect(url_for("scores.question_list", eid=eid))
    # 知识点 -> [得分率列表]
    knowledge_map = {}  # {subject: {kp: {"rates":[], "avg_rate":, "full":, "questions":[]}}}
    for q in questions:
        if not q.knowledge_points:
            continue
        kps = [k.strip() for k in q.knowledge_points.split(";") if k.strip()]
        scores = QuestionScore.query.filter_by(question_id=q.id).all()
        for kp in kps:
            subj_data = knowledge_map.setdefault(q.subject, {})
            entry = subj_data.setdefault(kp, {"rates": [], "questions": []})
            entry["questions"].append(q.question_no)
            for qs in scores:
                rate = qs.score / q.full_score if q.full_score > 0 else 0
                entry["rates"].append(rate)
    # 汇总
    knowledge_summary = []  # [{subject, label, kp, avg_rate, count}]
    for subj, kps in knowledge_map.items():
        for kp, data in kps.items():
            if not data["rates"]:
                continue
            avg_rate = sum(data["rates"]) / len(data["rates"])
            knowledge_summary.append({
                "subject": subj,
                "label": SUBJECT_LABEL.get(subj, subj),
                "kp": kp,
                "avg_rate": round(avg_rate * 100, 1),
                "count": len(data["rates"]),
                "questions": ", ".join(data["questions"]),
            })
    # 按科目排序
    knowledge_summary.sort(key=lambda x: (x["subject"], -x["avg_rate"]))
    # 学生维度: 每生在各知识点的掌握度
    students = Student.query.order_by(Student.student_no).all()
    student_kp = []  # [{student, weak_kps: [{subj,label,kp,rate}]}]
    for s in students:
        weak = []
        for subj, kps in knowledge_map.items():
            for kp, data in kps.items():
                # 收集该生在各题的得分率
                rates = []
                for qid in [q.id for q in questions if q.subject == subj and kp in [k.strip() for k in (q.knowledge_points or "").split(";") if k.strip()]]:
                    qs = QuestionScore.query.filter_by(question_id=qid, student_id=s.id).first()
                    if qs:
                        q = next((q for q in questions if q.id == qid), None)
                        if q:
                            rates.append(qs.score / q.full_score if q.full_score > 0 else 0)
                if rates:
                    avg_rate = sum(rates) / len(rates)
                    if avg_rate < 0.7:  # 弱项阈值70%
                        weak.append({
                            "subj": subj, "label": SUBJECT_LABEL.get(subj, subj),
                            "kp": kp, "rate": round(avg_rate * 100, 1),
                        })
        if weak:
            student_kp.append({"student": s, "weak_kps": weak})
    # 各科目知识点图表数据
    chart_data = {}
    for subj, kps in knowledge_map.items():
        labels = list(kps.keys())
        rates = [round(sum(kps[kp]["rates"]) / len(kps[kp]["rates"]) * 100, 1) if kps[kp]["rates"] else 0 for kp in labels]
        chart_data[subj] = {"labels": labels, "rates": rates, "label": SUBJECT_LABEL.get(subj, subj)}
    return render_template("scores/knowledge.html", exam=exam,
                            knowledge_summary=knowledge_summary,
                            student_kp=student_kp,
                            chart_data=chart_data)


# ==================== 学科贡献度分析 ====================
@scores_bp.route("/exam/<int:eid>/contribution")
def contribution_analysis(eid):
    """各科对总分贡献度(标准化), 识别拉分科目与提分空间"""
    exam = Exam.query.get_or_404(eid)
    records = ScoreRecord.query.filter_by(exam_id=eid).all()
    if not records:
        flash("本次考试暂无成绩", "warning")
        return redirect(url_for("scores.index"))
    subjects = ScoreRecord.SUBJECTS
    # 各科统计
    stats = subject_stats(records)
    # 标准化得分率 = 平均得分/满分
    contribution = []
    for subj in subjects:
        st = stats[subj]
        if st["avg"] is None:
            continue
        rate = st["avg"] / SUBJECT_FULL[subj] if SUBJECT_FULL[subj] > 0 else 0
        # 标准差作为区分度参考
        vals = [getattr(r, subj) for r in records if getattr(r, subj) is not None]
        variance = sum((v - st["avg"]) ** 2 for v in vals) / len(vals) if vals else 0
        std_v = variance ** 0.5
        # 提分空间 = (满分 * 0.85 - 平均分) / 满分 * 100 (距85%目标)
        target = SUBJECT_FULL[subj] * 0.85
        improve_space = max(0, (target - st["avg"]) / SUBJECT_FULL[subj] * 100)
        contribution.append({
            "subject": subj,
            "label": SUBJECT_LABEL[subj],
            "avg": round(st["avg"], 1),
            "full": SUBJECT_FULL[subj],
            "rate": round(rate * 100, 1),
            "std": round(std_v, 1),
            "max": st["max"],
            "min": st["min"],
            "improve_space": round(improve_space, 1),
            "weight": round(SUBJECT_FULL[subj] / 950 * 100, 1),  # 权重(总分950)
        })
    # 按贡献率(得分率)升序：得分率低的=拉分科目
    contribution.sort(key=lambda x: x["rate"])
    weak_subjects = [c for c in contribution if c["rate"] < 70]  # 弱项
    strong_subjects = [c for c in contribution if c["rate"] >= 80]  # 强项
    # 班级总分情况
    totals = [r.total for r in records if r.total is not None]
    class_avg = sum(totals) / len(totals) if totals else 0
    class_max = max(totals) if totals else 0
    class_min = min(totals) if totals else 0
    # 学生维度：识别拉分学生（单科得分率显著低于班级）
    student_contribution = []
    for r in records:
        if r.total is None:
            continue
        weak = []
        for subj in subjects:
            v = getattr(r, subj, None)
            if v is None:
                continue
            rate = v / SUBJECT_FULL[subj] if SUBJECT_FULL[subj] > 0 else 0
            if rate < 0.6:  # 显著低于班级
                weak.append({
                    "subj": subj, "label": SUBJECT_LABEL[subj],
                    "score": round(v, 1), "rate": round(rate * 100, 1),
                    "class_avg": round(stats[subj]["avg"], 1),
                })
        if weak:
            student_contribution.append({
                "student": r.student, "total": round(r.total, 1),
                "class_rank": r.class_rank, "weak": weak,
            })
    # 按总分降序
    student_contribution.sort(key=lambda x: -x["total"])
    return render_template("scores/contribution.html", exam=exam,
                            contribution=contribution,
                            weak_subjects=weak_subjects,
                            strong_subjects=strong_subjects,
                            class_avg=round(class_avg, 1),
                            class_max=round(class_max, 1),
                            class_min=round(class_min, 1),
                            student_count=len(totals),
                            student_contribution=student_contribution)


# ==================== 年级对标分析 ====================
@scores_bp.route("/exam/<int:eid>/benchmark", methods=["GET", "POST"])
def benchmark_analysis(eid):
    """年级对标: 导入年级均分, 班级 vs 年级"""
    exam = Exam.query.get_or_404(eid)
    if request.method == "POST":
        # 批量录入/更新
        for key, value in request.form.items():
            if not key.startswith("bm_"):
                continue
            # bm_<subject> = grade_avg
            subj = key[3:]
            value = value.strip()
            if not value:
                continue
            try:
                grade_avg = float(value)
            except ValueError:
                continue
            bm = GradeBenchmark.query.filter_by(exam_id=eid, subject=subj).first()
            if bm:
                bm.grade_avg = grade_avg
            else:
                db.session.add(GradeBenchmark(exam_id=eid, subject=subj, grade_avg=grade_avg))
        # 年级人数/最高分
        cnt = request.form.get("grade_stu_count", "").strip()
        if cnt:
            try:
                cnt_v = int(cnt)
                for subj in ["total"] + ScoreRecord.SUBJECTS:
                    bm = GradeBenchmark.query.filter_by(exam_id=eid, subject=subj).first()
                    if bm:
                        bm.grade_stu_count = cnt_v
            except ValueError:
                pass
        db.session.commit()
        flash("年级对标数据已保存", "success")
        return redirect(url_for("scores.benchmark_analysis", eid=eid))
    records = ScoreRecord.query.filter_by(exam_id=eid).all()
    subjects = ScoreRecord.SUBJECTS
    stats = subject_stats(records)
    # 年级数据
    bm_map = {bm.subject: bm for bm in GradeBenchmark.query.filter_by(exam_id=eid).all()}
    # 对标表
    comparison = []
    for subj in subjects + ["total"]:
        if subj == "total":
            class_avg = sum(r.total for r in records if r.total is not None) / len(records) if records else 0
            full = 950
        else:
            class_avg = stats[subj]["avg"] or 0
            full = SUBJECT_FULL[subj]
        bm = bm_map.get(subj)
        grade_avg = bm.grade_avg if bm and bm.grade_avg else None
        grade_max = bm.grade_max if bm and bm.grade_max else None
        grade_count = bm.grade_stu_count if bm and bm.grade_stu_count else None
        diff = round(class_avg - grade_avg, 1) if grade_avg is not None else None
        comparison.append({
            "subject": subj,
            "label": "总分" if subj == "total" else SUBJECT_LABEL[subj],
            "class_avg": round(class_avg, 1),
            "grade_avg": round(grade_avg, 1) if grade_avg is not None else None,
            "grade_max": round(grade_max, 1) if grade_max is not None else None,
            "grade_count": grade_count,
            "diff": diff,
            "rate": round((diff / grade_avg * 100) if (grade_avg and grade_avg > 0) else 0, 1),
            "full": full,
        })
    # 班级排名分布(基于年级人数)
    grade_total_count = bm_map.get("total").grade_stu_count if bm_map.get("total") else None
    return render_template("scores/benchmark.html", exam=exam,
                            comparison=comparison, bm_map=bm_map,
                            subjects=subjects, subject_label=SUBJECT_LABEL,
                            subject_full=SUBJECT_FULL,
                            grade_total_count=grade_total_count)
