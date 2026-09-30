"""日常管理蓝图 (模块3)"""
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from sqlalchemy import func

from app.extensions import db
from app.models import Student, DailyRecord, StudentComment, ParentContact, ScoreRecord, Exam, \
    ClassActivity, Honor, PsychologyObservation, HomeVisit
from app.utils.comment import generate_comment
from app.utils.suggestion import SUBJECT_LABEL, SUBJECT_FULL
from collections import Counter

daily_bp = Blueprint("daily", __name__)


@daily_bp.route("/")
def index():
    q = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    per_page = 20
    query = Student.query
    if q:
        query = query.filter(Student.name.contains(q) | Student.student_no.contains(q))
    pagination = query.order_by(Student.student_no).paginate(page=page, per_page=per_page, error_out=False)
    # 每人本月违纪/表扬计数
    month_start = date.today().replace(day=1)
    counts = {}
    rows = (db.session.query(DailyRecord.student_id, DailyRecord.record_type,
                              func.count(DailyRecord.id))
            .filter(DailyRecord.occurred_at >= month_start)
            .group_by(DailyRecord.student_id, DailyRecord.record_type).all())
    for sid, rtype, cnt in rows:
        counts.setdefault(sid, Counter())[rtype] = cnt
    return render_template("daily/index.html", pagination=pagination, q=q,
                            counts=counts, praise_types=DailyRecord.PRAISE_TYPES)


@daily_bp.route("/student/<int:sid>", methods=["GET", "POST"])
def student_page(sid):
    s = Student.query.get_or_404(sid)
    if request.method == "POST":
        rtype = request.form.get("record_type")
        occurred = request.form.get("occurred_at")
        desc = request.form.get("description", "").strip()
        severity_str = request.form.get("severity", "0")
        if rtype not in DailyRecord.TYPE_CHOICES:
            flash("记录类型不合法", "danger")
            return redirect(url_for("daily.student_page", sid=sid))
        try:
            od = datetime.strptime(occurred, "%Y-%m-%d").date() if occurred else date.today()
        except ValueError:
            flash("日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("daily.student_page", sid=sid))
        try:
            sev = int(severity_str)
        except ValueError:
            sev = 0
        r = DailyRecord(
            student_id=sid,
            record_type=rtype,
            occurred_at=od,
            description=desc,
            severity=sev if rtype in ("late", "distraction", "discipline") else 0,
        )
        db.session.add(r)
        db.session.commit()
        flash("已记录", "success")
        return redirect(url_for("daily.student_page", sid=sid))
    records = (DailyRecord.query
                .filter_by(student_id=sid)
                .order_by(DailyRecord.occurred_at.desc(),
                          DailyRecord.id.desc()).all())
    return render_template("daily/student.html", s=s, records=records,
                            type_choices=DailyRecord.TYPE_CHOICES,
                            today=date.today().isoformat())


@daily_bp.route("/record/<int:rid>/delete", methods=["POST"])
def delete_record(rid):
    r = DailyRecord.query.get_or_404(rid)
    sid = r.student_id
    db.session.delete(r)
    db.session.commit()
    flash("已删除", "success")
    return redirect(url_for("daily.student_page", sid=sid))


# ---------- 班级日常统计 ----------
@daily_bp.route("/stats")
def stats():
    from collections import Counter
    from calendar import monthrange
    # 当月各类型计数
    month_start = date.today().replace(day=1)
    _, last_day = monthrange(date.today().year, date.today().month)
    month_end = date.today().replace(day=last_day)
    # 工作日数(周一~周五)
    workdays = sum(1 for d in range(1, last_day + 1)
                  if date(date.today().year, date.today().month, d).weekday() < 5)
    rows = (db.session.query(DailyRecord.record_type,
                              func.count(DailyRecord.id))
            .filter(DailyRecord.occurred_at >= month_start)
            .group_by(DailyRecord.record_type).all())
    type_counts = {r[0]: r[1] for r in rows}
    # 各学生本月违纪/表扬计数
    subq = (db.session.query(DailyRecord.student_id,
                              DailyRecord.record_type,
                              func.count(DailyRecord.id).label("cnt"))
            .filter(DailyRecord.occurred_at >= month_start)
            .group_by(DailyRecord.student_id, DailyRecord.record_type).all())
    student_counts = {}
    for sid, rtype, cnt in subq:
        student_counts.setdefault(sid, Counter())[rtype] = cnt
    students = Student.query.order_by(Student.student_no).all()
    # 违纪榜 + 出勤率 + 预警
    punish_top = []
    attendance_list = []  # [(student, absence_count, attendance_rate)]
    warning_list = []  # 重复违纪(本月≥3次)
    for s in students:
        c = student_counts.get(s.id, Counter())
        total_punish = sum(c.get(t, 0) for t in ["late", "discipline", "distraction", "leave", "other"])
        total_praise = sum(c.get(t, 0) for t in ["praise", "reward"])
        if total_punish > 0:
            punish_top.append({"student": s, "count": total_punish})
        # 出勤率: 简化公式 = (工作日 - 缺席次数*0.5) / 工作日, 缺席=late+leave
        # late 算半天, leave 算1天
        absence_days = c.get("late", 0) * 0.5 + c.get("leave", 0)
        rate = max(0, (workdays - absence_days) / workdays * 100) if workdays > 0 else 100
        attendance_list.append({"student": s, "absence": absence_days,
                                 "rate": rate,
                                 "late": c.get("late", 0),
                                 "leave": c.get("leave", 0),
                                 "discipline": c.get("discipline", 0) + c.get("distraction", 0)})
        if total_punish >= 3:
            warning_list.append({"student": s, "count": total_punish,
                                  "details": dict(c)})
    praise_top = []
    for s in students:
        c = student_counts.get(s.id, Counter())
        total = sum(c.get(t, 0) for t in ["praise", "reward"])
        if total > 0:
            praise_top.append({"student": s, "count": total})
    praise_top.sort(key=lambda x: x["count"], reverse=True)
    punish_top.sort(key=lambda x: x["count"], reverse=True)
    warning_list.sort(key=lambda x: x["count"], reverse=True)
    # 出勤率按低→高排(关注后进)
    attendance_list.sort(key=lambda x: x["rate"])
    return render_template("daily/stats.html",
                            type_counts=type_counts,
                            type_choices=DailyRecord.TYPE_CHOICES,
                            punish_top=punish_top[:10],
                            praise_top=praise_top[:10],
                            month_start=month_start,
                            month_end=month_end,
                            workdays=workdays,
                            attendance_list=attendance_list,
                            warning_list=warning_list)


@daily_bp.route("/api/stats")
def api_stats():
    """当月各类型计数 + Top10 (供 ECharts 用)"""
    from collections import Counter
    month_start = date.today().replace(day=1)
    rows = (db.session.query(DailyRecord.record_type,
                              func.count(DailyRecord.id))
            .filter(DailyRecord.occurred_at >= month_start)
            .group_by(DailyRecord.record_type).all())
    type_counts = {r[0]: r[1] for r in rows}
    # 全部类型(即使 0 也显示)
    pie_data = []
    for code, label in DailyRecord.TYPE_CHOICES.items():
        pie_data.append({"name": label, "value": type_counts.get(code, 0)})
    # 各学生违纪/表扬计数
    subq = (db.session.query(DailyRecord.student_id,
                              DailyRecord.record_type,
                              func.count(DailyRecord.id).label("cnt"))
            .filter(DailyRecord.occurred_at >= month_start)
            .group_by(DailyRecord.student_id, DailyRecord.record_type).all())
    student_counts = {}
    for sid, rtype, cnt in subq:
        student_counts.setdefault(sid, Counter())[rtype] = cnt
    students = Student.query.all()
    punish_top = []
    praise_top = []
    for s in students:
        c = student_counts.get(s.id, Counter())
        pp = sum(c.get(t, 0) for t in ["late", "discipline", "distraction", "leave", "other"])
        pr = sum(c.get(t, 0) for t in ["praise", "reward"])
        if pp > 0:
            punish_top.append({"name": s.name, "studentId": s.id, "count": pp})
        if pr > 0:
            praise_top.append({"name": s.name, "studentId": s.id, "count": pr})
    punish_top.sort(key=lambda x: x["count"], reverse=True)
    praise_top.sort(key=lambda x: x["count"], reverse=True)
    return jsonify({
        "pie": pie_data,
        "punishTop": punish_top[:10],
        "praiseTop": praise_top[:10],
        "month": month_start.isoformat(),
    })


# ---------- 学生评语 ----------
@daily_bp.route("/comment/<int:sid>", methods=["GET", "POST"])
def comment(sid):
    s = Student.query.get_or_404(sid)
    # 默认学期: 当前年+季节
    today = date.today()
    if today.month >= 8:
        default_term = f"{today.year}秋季"
    elif today.month >= 2:
        default_term = f"{today.year}春季"
    else:
        default_term = f"{today.year - 1}秋季"
    term = request.args.get("term", default_term)

    if request.method == "POST":
        action = request.form.get("action", "save")
        new_term = request.form.get("term", term).strip() or default_term
        content = request.form.get("content", "").strip()
        # 查询或新建
        c = StudentComment.query.filter_by(student_id=sid, term=new_term).first()
        if not c:
            c = StudentComment(student_id=sid, term=new_term, content=content,
                               is_draft=(action != "finalize"))
            db.session.add(c)
        else:
            c.content = content
            c.is_draft = (action != "finalize")
        db.session.commit()
        if action == "finalize":
            flash(f"评语已定稿（{new_term}）", "success")
        else:
            flash(f"草稿已保存（{new_term}）", "success")
        return redirect(url_for("daily.comment", sid=sid, term=new_term))

    # GET
    c = StudentComment.query.filter_by(student_id=sid, term=term).first()
    content = c.content if c else ""
    is_draft = c.is_draft if c else True
    # 列出该学生所有评语学期
    history = (StudentComment.query
               .filter_by(student_id=sid)
               .order_by(StudentComment.term.desc()).all())
    return render_template("daily/comment.html", s=s, term=term,
                            content=content, is_draft=is_draft,
                            history=history, default_term=default_term)


@daily_bp.route("/comment/<int:sid>/generate", methods=["POST"])
def comment_generate(sid):
    s = Student.query.get_or_404(sid)
    term = request.form.get("term", "").strip()
    if not term:
        today = date.today()
        if today.month >= 8:
            term = f"{today.year}秋季"
        elif today.month >= 2:
            term = f"{today.year}春季"
        else:
            term = f"{today.year - 1}秋季"
    draft = generate_comment(s, term)
    c = StudentComment.query.filter_by(student_id=sid, term=term).first()
    if not c:
        c = StudentComment(student_id=sid, term=term, content=draft, is_draft=True)
        db.session.add(c)
    else:
        c.content = draft
        c.is_draft = True
    db.session.commit()
    flash(f"已生成 {term} 评语初稿, 请班主任审阅修改", "success")
    return redirect(url_for("daily.comment", sid=sid, term=term))


# ---------- 家校联系日志 ----------
@daily_bp.route("/contact", methods=["GET", "POST"])
def contact_list():
    """所有学生的家校联系记录总览"""
    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        contact_date = request.form.get("contact_date", date.today().isoformat())
        contact_type = request.form.get("contact_type", "phone")
        contact_person = request.form.get("contact_person", "").strip()
        content = request.form.get("content", "").strip()
        if not student_id:
            flash("请选择学生", "danger")
            return redirect(url_for("daily.contact_list"))
        s = Student.query.get_or_404(student_id)
        try:
            cd = datetime.strptime(contact_date, "%Y-%m-%d").date() if contact_date else date.today()
        except ValueError:
            flash("日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("daily.contact_list"))
        pc = ParentContact(
            student_id=student_id,
            contact_date=cd,
            contact_type=contact_type,
            contact_person=contact_person or None,
            content=content or None,
        )
        db.session.add(pc)
        db.session.commit()
        flash(f"已记录与 {s.name} 家长的沟通", "success")
        return redirect(url_for("daily.contact_list"))
    # GET: 列出所有联系记录
    contacts = (ParentContact.query
                .order_by(ParentContact.contact_date.desc(),
                          ParentContact.id.desc()).all())
    students = Student.query.order_by(Student.student_no).all()
    return render_template("daily/contact_list.html", contacts=contacts,
                            students=students,
                            type_choices=ParentContact.TYPE_CHOICES,
                            today=date.today().isoformat())


@daily_bp.route("/contact/<int:sid>")
def contact_student(sid):
    """单个学生的家校联系记录"""
    s = Student.query.get_or_404(sid)
    contacts = (ParentContact.query
                .filter_by(student_id=sid)
                .order_by(ParentContact.contact_date.desc(),
                          ParentContact.id.desc()).all())
    return render_template("daily/contact_student.html", s=s, contacts=contacts,
                            type_choices=ParentContact.TYPE_CHOICES,
                            today_val=date.today().isoformat())


@daily_bp.route("/contact/<int:cid>/delete", methods=["POST"])
def contact_delete(cid):
    pc = ParentContact.query.get_or_404(cid)
    sid = pc.student_id
    db.session.delete(pc)
    db.session.commit()
    flash("已删除该联系记录", "success")
    return redirect(url_for("daily.contact_student", sid=sid))


# ---------- 请假管理（独立流程） ----------
@daily_bp.route("/leave")
def leave_list():
    """请假登记列表"""
    status = request.args.get("status", "all")  # all/active/canceled
    q = (DailyRecord.query
         .filter(DailyRecord.record_type == DailyRecord.TYPE_LEAVE))
    if status == "active":
        q = q.filter(DailyRecord.cancel_date.is_(None))
    elif status == "canceled":
        q = q.filter(DailyRecord.cancel_date.isnot(None))
    leaves = q.order_by(DailyRecord.occurred_at.desc(),
                        DailyRecord.id.desc()).all()
    students = Student.query.order_by(Student.student_no).all()
    return render_template("daily/leave_list.html", leaves=leaves,
                            students=students, status=status,
                            today=date.today().isoformat())


@daily_bp.route("/leave/new", methods=["GET", "POST"])
def leave_new():
    """请假登记表单（含天数计算/家长知晓）"""
    students = Student.query.order_by(Student.student_no).all()
    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        start_date_str = request.form.get("start_date", "")
        end_date_str = request.form.get("end_date", "")
        leave_reason = request.form.get("leave_reason", "").strip()
        parent_notified = request.form.get("parent_notified") == "on"
        note = request.form.get("description", "").strip()
        if not student_id:
            flash("请选择学生", "danger")
            return redirect(url_for("daily.leave_new"))
        s = Student.query.get_or_404(student_id)
        try:
            sd = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else date.today()
            ed = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else sd
        except ValueError:
            flash("日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("daily.leave_new"))
        if ed < sd:
            flash("结束日期不能早于开始日期", "danger")
            return redirect(url_for("daily.leave_new"))
        # 天数计算(包含起止两端)
        days = (ed - sd).days + 1
        r = DailyRecord(
            student_id=student_id,
            record_type=DailyRecord.TYPE_LEAVE,
            occurred_at=sd,
            description=note,
            start_date=sd,
            end_date=ed,
            leave_days=float(days),
            leave_reason=leave_reason or None,
            parent_notified=parent_notified,
        )
        db.session.add(r)
        db.session.commit()
        flash(f"已登记 {s.name} 的请假（{days} 天）", "success")
        return redirect(url_for("daily.leave_list"))
    return render_template("daily/leave_form.html", students=students,
                            today=date.today().isoformat(),
                            action="new")


@daily_bp.route("/leave/<int:lid>/cancel", methods=["GET", "POST"])
def leave_cancel(lid):
    """销假确认"""
    r = DailyRecord.query.get_or_404(lid)
    if r.record_type != DailyRecord.TYPE_LEAVE:
        abort(404)
    if r.cancel_date is not None:
        flash("该请假已销假，无需重复操作", "info")
        return redirect(url_for("daily.leave_list"))
    if request.method == "POST":
        cancel_date_str = request.form.get("cancel_date", "")
        try:
            cd = datetime.strptime(cancel_date_str, "%Y-%m-%d").date() if cancel_date_str else date.today()
        except ValueError:
            flash("日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("daily.leave_cancel", lid=lid))
        if cd < r.start_date:
            flash("销假日期不能早于请假开始日期", "danger")
            return redirect(url_for("daily.leave_cancel", lid=lid))
        # 重新计算实际请假天数
        if r.end_date and cd < r.end_date:
            r.leave_days = float((cd - r.start_date).days + 1)
        r.cancel_date = cd
        db.session.commit()
        flash(f"{r.student.name} 销假完成（实际请假 {r.leave_days} 天）", "success")
        return redirect(url_for("daily.leave_list"))
    return render_template("daily/leave_form.html", r=r,
                            today=date.today().isoformat(),
                            action="cancel")


@daily_bp.route("/leave/<int:lid>/delete", methods=["POST"])
def leave_delete(lid):
    r = DailyRecord.query.get_or_404(lid)
    if r.record_type != DailyRecord.TYPE_LEAVE:
        abort(404)
    db.session.delete(r)
    db.session.commit()
    flash("已删除该请假记录", "success")
    return redirect(url_for("daily.leave_list"))


# ---------- 学生成长轨迹 ----------
@daily_bp.route("/growth/<int:sid>")
def growth(sid):
    """学生成长轨迹：综合个人档案"""
    s = Student.query.get_or_404(sid)
    # 历次成绩(按考试日期升序)
    scores = (ScoreRecord.query
              .join(Exam)
              .filter(ScoreRecord.student_id == sid)
              .order_by(Exam.exam_date.asc()).all())
    # 日常记录(奖惩/请假/违纪)
    records = (DailyRecord.query
               .filter_by(student_id=sid)
               .order_by(DailyRecord.occurred_at.asc(),
                         DailyRecord.id.asc()).all())
    # 评语
    comments = (StudentComment.query
                .filter_by(student_id=sid)
                .order_by(StudentComment.term.desc()).all())
    # 家校联系
    contacts = (ParentContact.query
                .filter_by(student_id=sid)
                .order_by(ParentContact.contact_date.asc(),
                          ParentContact.id.asc()).all())
    # 合并时间线
    timeline = []
    for r in records:
        timeline.append({
            "date": r.occurred_at,
            "type": "record",
            "label": r.type_label(),
            "title": r.type_label() + (f"（{r.leave_days}天）" if r.is_leave() and r.leave_days else ""),
            "content": r.description or r.leave_reason or "",
            "is_praise": r.is_praise(),
            "obj": r,
        })
    for c in contacts:
        timeline.append({
            "date": c.contact_date,
            "type": "contact",
            "label": "家校联系·" + c.type_label(),
            "title": "家校沟通" + (f"（{c.contact_person}）" if c.contact_person else ""),
            "content": c.content or "",
            "is_praise": False,
            "obj": c,
        })
    for sc in scores:
        timeline.append({
            "date": sc.exam.exam_date,
            "type": "score",
            "label": "考试·" + sc.exam.name,
            "title": f"{sc.exam.name} · 总分 {sc.total or '—'} · 班排 {sc.class_rank or '—'}",
            "content": f"总分 {sc.total}",
            "is_praise": False,
            "obj": sc,
        })
    for cm in comments:
        # 学期转日期(近似)
        try:
            year = int(cm.term[:4])
            month = 9 if "秋" in cm.term else 3
            cm_date = date(year, month, 1)
        except (ValueError, IndexError):
            cm_date = date.today()
        timeline.append({
            "date": cm_date,
            "type": "comment",
            "label": "评语·" + cm.term,
            "title": "学期评语" + ("（草稿）" if cm.is_draft else "（定稿）"),
            "content": cm.content or "",
            "is_praise": False,
            "obj": cm,
        })
    # 按日期升序
    timeline.sort(key=lambda x: (x["date"], 0))
    # 反转(最新在前)
    timeline.reverse()
    # 统计
    praise_count = sum(1 for r in records if r.is_praise())
    punish_count = sum(1 for r in records if not r.is_praise())
    leave_count = sum(1 for r in records if r.is_leave())
    leave_days = sum(r.leave_days or 0 for r in records if r.is_leave())
    return render_template("daily/growth.html", s=s,
                            scores=scores, records=records,
                            comments=comments, contacts=contacts,
                            timeline=timeline,
                            praise_count=praise_count,
                            punish_count=punish_count,
                            leave_count=leave_count,
                            leave_days=leave_days,
                            subject_label=SUBJECT_LABEL,
                            subject_full=SUBJECT_FULL)


# ==================== 班会/活动记录 ====================
@daily_bp.route("/activity")
def activity_list():
    term = request.args.get("term", "").strip()
    type_ = request.args.get("type", "all")
    q = ClassActivity.query
    if term:
        q = q.filter(ClassActivity.term.contains(term))
    if type_ in ("meeting", "activity"):
        q = q.filter(ClassActivity.activity_type == type_)
    activities = q.order_by(ClassActivity.held_at.desc()).all()
    return render_template("daily/activity_list.html", activities=activities,
                            term=term, type=type_,
                            type_choices=ClassActivity.TYPE_CHOICES)


@daily_bp.route("/activity/new", methods=["GET", "POST"])
def activity_new():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        activity_type = request.form.get("activity_type", ClassActivity.TYPE_MEETING)
        held_at_str = request.form.get("held_at", "").strip()
        term = request.form.get("term", "").strip()
        participants = request.form.get("participants", "").strip()
        agenda = request.form.get("agenda", "").strip()
        summary = request.form.get("summary", "").strip()
        if not title:
            flash("请填写主题", "danger")
            return redirect(url_for("daily.activity_new"))
        try:
            held_at = datetime.strptime(held_at_str, "%Y-%m-%d").date() if held_at_str else date.today()
        except ValueError:
            flash("日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("daily.activity_new"))
        if activity_type not in ClassActivity.TYPE_CHOICES:
            activity_type = ClassActivity.TYPE_MEETING
        a = ClassActivity(title=title, activity_type=activity_type, held_at=held_at,
                          term=term or None, participants=participants or None,
                          agenda=agenda or None, summary=summary or None)
        db.session.add(a)
        db.session.commit()
        flash(f"已记录「{title}」", "success")
        return redirect(url_for("daily.activity_detail", aid=a.id))
    return render_template("daily/activity_form.html", activity=None,
                            type_choices=ClassActivity.TYPE_CHOICES,
                            today=date.today().isoformat())


@daily_bp.route("/activity/<int:aid>")
def activity_detail(aid):
    a = ClassActivity.query.get_or_404(aid)
    return render_template("daily/activity_detail.html", a=a)


@daily_bp.route("/activity/<int:aid>/delete", methods=["POST"])
def activity_delete(aid):
    a = ClassActivity.query.get_or_404(aid)
    title = a.title
    db.session.delete(a)
    db.session.commit()
    flash(f"已删除「{title}」", "success")
    return redirect(url_for("daily.activity_list"))


# ==================== 学生荣誉墙 ====================
@daily_bp.route("/honor")
def honor_list():
    level = request.args.get("level", "all")
    q = Honor.query
    if level in Honor.LEVEL_CHOICES:
        q = q.filter(Honor.level == level)
    honors = q.order_by(Honor.awarded_at.desc()).all()
    students = Student.query.order_by(Student.student_no).all()
    return render_template("daily/honor_list.html", honors=honors,
                            students=students, level=level,
                            level_choices=Honor.LEVEL_CHOICES,
                            today=date.today().isoformat())


@daily_bp.route("/honor/new", methods=["POST"])
def honor_new():
    student_id = request.form.get("student_id", type=int)
    title = request.form.get("title", "").strip()
    level = request.form.get("level", Honor.LEVEL_CLASS)
    awarded_at_str = request.form.get("awarded_at", "").strip()
    org = request.form.get("org", "").strip()
    description = request.form.get("description", "").strip()
    if not student_id or not title:
        flash("请填写学生和荣誉名称", "danger")
        return redirect(url_for("daily.honor_list"))
    s = Student.query.get_or_404(student_id)
    try:
        ad = datetime.strptime(awarded_at_str, "%Y-%m-%d").date() if awarded_at_str else date.today()
    except ValueError:
        flash("日期格式应为 YYYY-MM-DD", "danger")
        return redirect(url_for("daily.honor_list"))
    if level not in Honor.LEVEL_CHOICES:
        level = Honor.LEVEL_CLASS
    h = Honor(student_id=student_id, title=title, level=level, awarded_at=ad,
              org=org or None, description=description or None)
    db.session.add(h)
    db.session.commit()
    flash(f"已登记 {s.name} 荣誉「{title}」", "success")
    return redirect(url_for("daily.honor_list"))


@daily_bp.route("/honor/<int:hid>/delete", methods=["POST"])
def honor_delete(hid):
    h = Honor.query.get_or_404(hid)
    db.session.delete(h)
    db.session.commit()
    flash("已删除该荣誉", "success")
    return redirect(url_for("daily.honor_list"))


@daily_bp.route("/honor/<int:hid>/certificate")
def honor_certificate(hid):
    """荣誉证书打印版"""
    h = Honor.query.get_or_404(hid)
    return render_template("daily/honor_certificate.html", h=h,
                            today=date.today())


# ==================== 心理健康观察 ====================
@daily_bp.route("/psychology")
def psychology_list():
    level = request.args.get("level", "all")
    q = PsychologyObservation.query
    if level in PsychologyObservation.LEVEL_CHOICES:
        q = q.filter(PsychologyObservation.concern_level == level)
    records = q.order_by(PsychologyObservation.observe_date.desc()).all()
    students = Student.query.order_by(Student.student_no).all()
    # 预警关注名单（级别为 attention 或 warning 的最新一条）
    warning_students = []
    today = date.today()
    for s in students:
        latest = (PsychologyObservation.query
                  .filter_by(student_id=s.id)
                  .order_by(PsychologyObservation.observe_date.desc()).first())
        if latest and latest.concern_level in (PsychologyObservation.LEVEL_ATTENTION,
                                                  PsychologyObservation.LEVEL_WARNING):
            warning_students.append({"student": s, "latest": latest,
                                       "need_followup": latest.followup_date and latest.followup_date <= today})
    return render_template("daily/psychology_list.html", records=records,
                            students=students, level=level,
                            level_choices=PsychologyObservation.LEVEL_CHOICES,
                            warning_students=warning_students,
                            today=today.isoformat())


@daily_bp.route("/psychology/new", methods=["POST"])
def psychology_new():
    student_id = request.form.get("student_id", type=int)
    observe_date_str = request.form.get("observe_date", "").strip()
    mood = request.form.get("mood", "").strip()
    behavior = request.form.get("behavior", "").strip()
    concern_level = request.form.get("concern_level", PsychologyObservation.LEVEL_NORMAL)
    followup_date_str = request.form.get("followup_date", "").strip()
    note = request.form.get("note", "").strip()
    if not student_id:
        flash("请选择学生", "danger")
        return redirect(url_for("daily.psychology_list"))
    s = Student.query.get_or_404(student_id)
    try:
        od = datetime.strptime(observe_date_str, "%Y-%m-%d").date() if observe_date_str else date.today()
    except ValueError:
        flash("观察日期格式应为 YYYY-MM-DD", "danger")
        return redirect(url_for("daily.psychology_list"))
    if concern_level not in PsychologyObservation.LEVEL_CHOICES:
        concern_level = PsychologyObservation.LEVEL_NORMAL
    followup_date = None
    if followup_date_str:
        try:
            followup_date = datetime.strptime(followup_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    p = PsychologyObservation(student_id=student_id, observe_date=od,
                               mood=mood or None, behavior=behavior or None,
                               concern_level=concern_level,
                               followup_date=followup_date,
                               note=note or None)
    db.session.add(p)
    db.session.commit()
    flash(f"已记录 {s.name} 的心理观察", "success")
    return redirect(url_for("daily.psychology_list"))


@daily_bp.route("/psychology/<int:pid>/delete", methods=["POST"])
def psychology_delete(pid):
    p = PsychologyObservation.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    flash("已删除该观察记录", "success")
    return redirect(url_for("daily.psychology_list"))


# ==================== 家访记录 ====================
@daily_bp.route("/visit")
def visit_list():
    q = request.args.get("q", "").strip()
    query = HomeVisit.query
    if q:
        # 按学生姓名/学号搜索
        query = (query.join(Student)
                 .filter(Student.name.contains(q) | Student.student_no.contains(q)))
    visits = query.order_by(HomeVisit.visit_date.desc()).all()
    students = Student.query.order_by(Student.student_no).all()
    return render_template("daily/visit_list.html", visits=visits, q=q,
                            students=students, today=date.today().isoformat())


@daily_bp.route("/visit/new", methods=["GET", "POST"])
def visit_new():
    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        visit_date_str = request.form.get("visit_date", "").strip()
        accompany = request.form.get("accompany", "").strip()
        home_situation = request.form.get("home_situation", "").strip()
        parent_attitude = request.form.get("parent_attitude", "").strip()
        content = request.form.get("content", "").strip()
        followup = request.form.get("followup", "").strip()
        if not student_id:
            flash("请选择学生", "danger")
            return redirect(url_for("daily.visit_new"))
        s = Student.query.get_or_404(student_id)
        try:
            vd = datetime.strptime(visit_date_str, "%Y-%m-%d").date() if visit_date_str else date.today()
        except ValueError:
            flash("家访日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("daily.visit_new"))
        v = HomeVisit(student_id=student_id, visit_date=vd,
                      accompany=accompany or None,
                      home_situation=home_situation or None,
                      parent_attitude=parent_attitude or None,
                      content=content or None,
                      followup=followup or None)
        db.session.add(v)
        db.session.commit()
        flash(f"已记录 {s.name} 的家访", "success")
        return redirect(url_for("daily.visit_detail", vid=v.id))
    students = Student.query.order_by(Student.student_no).all()
    return render_template("daily/visit_form.html", visit=None,
                            students=students, today=date.today().isoformat())


@daily_bp.route("/visit/<int:vid>")
def visit_detail(vid):
    v = HomeVisit.query.get_or_404(vid)
    return render_template("daily/visit_detail.html", v=v)


@daily_bp.route("/visit/<int:vid>/delete", methods=["POST"])
def visit_delete(vid):
    v = HomeVisit.query.get_or_404(vid)
    db.session.delete(v)
    db.session.commit()
    flash("已删除该家访记录", "success")
    return redirect(url_for("daily.visit_list"))
