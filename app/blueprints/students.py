"""学生基本信息蓝图 (模块1)"""
import os
from io import BytesIO
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, \
    flash, send_file, abort, current_app
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (Student, DailyRecord, ScoreRecord, Exam,
                        StudentPhoto, HealthRecord, StudentGroup, StudentGroupMember,
                        OfficerRecord)
from app.utils.excel import build_student_template, parse_student_excel, \
    build_health_template, parse_health_excel
from app.utils.zodiac import calc_zodiac
from app.utils.ranking import compute_class_rank

students_bp = Blueprint("students", __name__)


@students_bp.route("/")
def list_():
    q = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    per_page = 20
    query = Student.query
    if q:
        query = query.filter(or_(Student.name.contains(q), Student.student_no.contains(q)))
    pagination = query.order_by(Student.student_no).paginate(page=page, per_page=per_page, error_out=False)
    # 最近一次考试
    latest_exam = Exam.query.order_by(Exam.exam_date.desc()).first()
    rank_map = {}
    if latest_exam:
        for r in ScoreRecord.query.filter_by(exam_id=latest_exam.id).all():
            rank_map[r.student_id] = (r.class_rank, r.grade_rank)
    return render_template("students/list.html", pagination=pagination, q=q,
                            latest_exam=latest_exam, rank_map=rank_map)


@students_bp.route("/template")
def template():
    data = build_student_template()
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name="学生名单模板.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@students_bp.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("请选择 Excel 文件", "warning")
            return redirect(url_for("students.upload"))
        try:
            data = file.read()
            records = parse_student_excel(data)
        except Exception as e:
            flash(f"解析失败: {e}", "danger")
            return redirect(url_for("students.upload"))

        added, updated = 0, 0
        for rec in records:
            existing = Student.query.filter_by(student_no=rec["student_no"]).first()
            if existing:
                existing.name = rec["name"]
                if rec["gender"]:
                    existing.gender = rec["gender"]
                existing.ethnicity = rec["ethnicity"]
                if rec["birth_date"]:
                    existing.birth_date = rec["birth_date"]
                    zname, elem = calc_zodiac(rec["birth_date"])
                    existing.zodiac_sign = zname
                    existing.zodiac_element = elem
                if rec["height"] is not None:
                    existing.height = rec["height"]
                if rec["id_card"]:
                    existing.id_card = rec["id_card"]
                if rec["father_name"]:
                    existing.father_name = rec["father_name"]
                if rec["father_phone"]:
                    existing.father_phone = rec["father_phone"]
                if rec["mother_name"]:
                    existing.mother_name = rec["mother_name"]
                if rec["mother_phone"]:
                    existing.mother_phone = rec["mother_phone"]
                if rec["emergency_contact"]:
                    existing.emergency_contact = rec["emergency_contact"]
                if rec["emergency_phone"]:
                    existing.emergency_phone = rec["emergency_phone"]
                updated += 1
            else:
                zname, elem = (None, None)
                if rec["birth_date"]:
                    zname, elem = calc_zodiac(rec["birth_date"])
                s = Student(
                    student_no=rec["student_no"],
                    name=rec["name"],
                    gender=rec["gender"],
                    ethnicity=rec["ethnicity"],
                    birth_date=rec["birth_date"],
                    height=rec["height"],
                    id_card=rec["id_card"],
                    father_name=rec["father_name"],
                    father_phone=rec["father_phone"],
                    mother_name=rec["mother_name"],
                    mother_phone=rec["mother_phone"],
                    emergency_contact=rec["emergency_contact"],
                    emergency_phone=rec["emergency_phone"],
                    zodiac_sign=zname,
                    zodiac_element=elem,
                )
                db.session.add(s)
                added += 1
        db.session.commit()
        flash(f"导入完成: 新增 {added} 人, 更新 {updated} 人", "success")
        return redirect(url_for("students.list_"))
    return render_template("students/upload.html")


@students_bp.route("/<int:sid>")
def profile(sid):
    s = Student.query.get_or_404(sid)
    # 最近 5 条奖惩记录
    praise_records = (DailyRecord.query
                      .filter_by(student_id=sid)
                      .filter(DailyRecord.record_type.in_(["praise", "reward"]))
                      .order_by(DailyRecord.occurred_at.desc())
                      .limit(5).all())
    punish_records = (DailyRecord.query
                      .filter_by(student_id=sid)
                      .filter(DailyRecord.record_type.in_(
                          ["late", "discipline", "distraction", "leave", "other"]))
                      .order_by(DailyRecord.occurred_at.desc())
                      .limit(5).all())
    # 最近一次成绩排名
    latest_sr = (ScoreRecord.query
                  .join(Exam)
                  .filter(ScoreRecord.student_id == sid)
                  .order_by(Exam.exam_date.desc())
                  .first())
    # 所有考试成绩(时间线)
    all_records = (ScoreRecord.query
                   .join(Exam)
                   .filter(ScoreRecord.student_id == sid)
                   .order_by(Exam.exam_date.desc()).all())
    return render_template("students/profile.html", s=s,
                            praise_records=praise_records,
                            punish_records=punish_records,
                            latest_sr=latest_sr,
                            all_records=all_records)


@students_bp.route("/<int:sid>/full")
def full(sid):
    """完整档案打印版(用于 PDF 打印: 浏览器 Ctrl+P → 另存为 PDF)"""
    s = Student.query.get_or_404(sid)
    all_records = (ScoreRecord.query
                   .join(Exam)
                   .filter(ScoreRecord.student_id == sid)
                   .order_by(Exam.exam_date.asc()).all())
    daily_records = (DailyRecord.query
                     .filter_by(student_id=sid)
                     .order_by(DailyRecord.occurred_at.desc(),
                               DailyRecord.id.desc()).all())
    praise_count = sum(1 for r in daily_records if r.is_praise())
    punish_count = sum(1 for r in daily_records if not r.is_praise())
    # 最新评语
    from app.models import StudentComment
    latest_comment = (StudentComment.query
                      .filter_by(student_id=sid)
                      .order_by(StudentComment.term.desc()).first())
    return render_template("students/full.html", s=s,
                            all_records=all_records,
                            daily_records=daily_records,
                            praise_count=praise_count,
                            punish_count=punish_count,
                            latest_comment=latest_comment)


@students_bp.route("/<int:sid>/edit", methods=["GET", "POST"])
def edit(sid):
    s = Student.query.get_or_404(sid)
    if request.method == "POST":
        s.name = request.form.get("name", s.name)
        s.gender = request.form.get("gender", s.gender)
        s.ethnicity = request.form.get("ethnicity", s.ethnicity)
        height = request.form.get("height", "").strip()
        try:
            s.height = float(height) if height else None
        except ValueError:
            flash("身高需为数字", "danger")
            return redirect(url_for("students.edit", sid=sid))
        bd_str = request.form.get("birth_date", "").strip()
        if bd_str:
            try:
                s.birth_date = datetime.strptime(bd_str, "%Y-%m-%d").date()
                zname, elem = calc_zodiac(s.birth_date)
                s.zodiac_sign = zname
                s.zodiac_element = elem
            except ValueError:
                flash("出生日期格式应为 YYYY-MM-DD", "danger")
                return redirect(url_for("students.edit", sid=sid))
        else:
            s.birth_date = None
        s.id_card = request.form.get("id_card", "").strip() or None
        s.father_name = request.form.get("father_name", "").strip() or None
        s.father_phone = request.form.get("father_phone", "").strip() or None
        s.mother_name = request.form.get("mother_name", "").strip() or None
        s.mother_phone = request.form.get("mother_phone", "").strip() or None
        s.emergency_contact = request.form.get("emergency_contact", "").strip() or None
        s.emergency_phone = request.form.get("emergency_phone", "").strip() or None
        s.note = request.form.get("note", "").strip() or None
        db.session.commit()
        flash("已保存", "success")
        return redirect(url_for("students.profile", sid=sid))
    return render_template("students/edit.html", s=s)


@students_bp.route("/<int:sid>/delete", methods=["POST"])
def delete(sid):
    s = Student.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    flash(f"已删除 {s.name}", "success")
    return redirect(url_for("students.list_"))


# ==================== 学生照片管理 ====================
def _photo_upload_dir():
    """照片存储目录(相对 static)"""
    base = os.path.join(current_app.static_folder, "uploads", "photos")
    os.makedirs(base, exist_ok=True)
    return base


@students_bp.route("/<int:sid>/photo", methods=["GET", "POST"])
def photo_manage(sid):
    s = Student.query.get_or_404(sid)
    if request.method == "POST":
        file = request.files.get("photo")
        taken_at_str = request.form.get("taken_at", "").strip()
        note = request.form.get("note", "").strip()
        if not file or not file.filename:
            flash("请选择照片文件", "warning")
            return redirect(url_for("students.photo_manage", sid=sid))
        # 仅允许常见图片格式
        allowed = {".jpg", ".jpeg", ".png", ".webp"}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed:
            flash("仅支持 jpg/jpeg/png/webp 格式", "danger")
            return redirect(url_for("students.photo_manage", sid=sid))
        filename = secure_filename(f"stu_{sid}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}")
        save_dir = _photo_upload_dir()
        file.save(os.path.join(save_dir, filename))
        # 相对 static 路径
        rel_path = f"uploads/photos/{filename}"
        is_primary = request.form.get("is_primary") == "on"
        # 若设为主照片，先取消其它主照片
        if is_primary:
            for p in StudentPhoto.query.filter_by(student_id=sid, is_primary=True).all():
                p.is_primary = False
        p = StudentPhoto(student_id=sid, photo_path=rel_path,
                        is_primary=is_primary, note=note or None)
        if taken_at_str:
            try:
                p.taken_at = datetime.strptime(taken_at_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        db.session.add(p)
        db.session.commit()
        flash("照片已上传", "success")
        return redirect(url_for("students.photo_manage", sid=sid))
    photos = (StudentPhoto.query
              .filter_by(student_id=sid)
              .order_by(StudentPhoto.created_at.desc()).all())
    return render_template("students/photo_manage.html", s=s, photos=photos)


@students_bp.route("/<int:sid>/photo/<int:pid>/primary", methods=["POST"])
def photo_set_primary(sid, pid):
    p = StudentPhoto.query.get_or_404(pid)
    if p.student_id != sid:
        abort(404)
    for other in StudentPhoto.query.filter_by(student_id=sid, is_primary=True).all():
        other.is_primary = False
    p.is_primary = True
    db.session.commit()
    flash("已设为主照片", "success")
    return redirect(url_for("students.photo_manage", sid=sid))


@students_bp.route("/<int:sid>/photo/<int:pid>/delete", methods=["POST"])
def photo_delete(sid, pid):
    p = StudentPhoto.query.get_or_404(pid)
    if p.student_id != sid:
        abort(404)
    # 删除文件
    try:
        full_path = os.path.join(current_app.static_folder, p.photo_path)
        if os.path.exists(full_path):
            os.remove(full_path)
    except Exception:
        pass
    db.session.delete(p)
    db.session.commit()
    flash("已删除照片", "success")
    return redirect(url_for("students.photo_manage", sid=sid))


# ==================== 健康体检记录 ====================
@students_bp.route("/health-template")
def health_template():
    """下载体检结果上传模板"""
    data = build_health_template()
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name="体检记录模板.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@students_bp.route("/health-upload", methods=["GET", "POST"])
def health_upload():
    """批量上传全班体检记录"""
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("请选择 Excel 文件", "warning")
            return redirect(url_for("students.health_upload"))
        try:
            data = file.read()
            records = parse_health_excel(data)
        except Exception as e:
            flash(f"解析失败: {e}", "danger")
            return redirect(url_for("students.health_upload"))
        students_by_no = {s.student_no: s for s in Student.query.all()}
        added, skipped = 0, 0
        for rec in records:
            s = students_by_no.get(rec["student_no"])
            if not s:
                skipped += 1
                continue
            if not rec["exam_date"]:
                skipped += 1
                continue
            # 同学生同日期去重(覆盖更新)
            existing = HealthRecord.query.filter_by(
                student_id=s.id, exam_date=rec["exam_date"]).first()
            if existing:
                existing.height = rec["height"]
                existing.weight = rec["weight"]
                existing.vision_left = rec["vision_left"]
                existing.vision_right = rec["vision_right"]
                existing.result = rec["result"]
                existing.abnormal = rec["abnormal"]
                existing.abnormal_note = rec["abnormal_note"]
            else:
                db.session.add(HealthRecord(
                    student_id=s.id, exam_date=rec["exam_date"],
                    height=rec["height"], weight=rec["weight"],
                    vision_left=rec["vision_left"], vision_right=rec["vision_right"],
                    result=rec["result"], abnormal=rec["abnormal"],
                    abnormal_note=rec["abnormal_note"],
                ))
            added += 1
        db.session.commit()
        flash(f"体检记录导入完成: 新增/更新 {added} 条, 跳过 {skipped} 条(学号未找到或日期缺失)", "success")
        return redirect(url_for("students.health_summary"))
    return render_template("students/health_upload.html")


@students_bp.route("/<int:sid>/health", methods=["GET", "POST"])
def health_list(sid):
    s = Student.query.get_or_404(sid)
    if request.method == "POST":
        exam_date_str = request.form.get("exam_date", "").strip()
        try:
            ed = datetime.strptime(exam_date_str, "%Y-%m-%d").date() if exam_date_str else date.today()
        except ValueError:
            flash("日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("students.health_list", sid=sid))
        h_str = request.form.get("height", "").strip()
        w_str = request.form.get("weight", "").strip()
        vl_str = request.form.get("vision_left", "").strip()
        vr_str = request.form.get("vision_right", "").strip()
        result = request.form.get("result", "").strip()
        abnormal = request.form.get("abnormal") == "on"
        abnormal_note = request.form.get("abnormal_note", "").strip()
        h = HealthRecord(
            student_id=sid, exam_date=ed,
            height=float(h_str) if h_str else None,
            weight=float(w_str) if w_str else None,
            vision_left=float(vl_str) if vl_str else None,
            vision_right=float(vr_str) if vr_str else None,
            result=result or None,
            abnormal=abnormal,
            abnormal_note=abnormal_note or None,
        )
        db.session.add(h)
        db.session.commit()
        flash("体检记录已添加", "success")
        return redirect(url_for("students.health_list", sid=sid))
    records = (HealthRecord.query
              .filter_by(student_id=sid)
              .order_by(HealthRecord.exam_date.desc()).all())
    # 异常预警
    warnings = [r for r in records if r.abnormal]
    # 视力预警(< 4.8 或 < 1.0)
    vision_warnings = []
    for r in records:
        if (r.vision_left is not None and r.vision_left < 1.0) or \
           (r.vision_right is not None and r.vision_right < 1.0):
            vision_warnings.append(r)
    return render_template("students/health_list.html", s=s, records=records,
                            warnings=warnings, vision_warnings=vision_warnings,
                            today=date.today().isoformat())


@students_bp.route("/<int:sid>/health/<int:hid>/delete", methods=["POST"])
def health_delete(sid, hid):
    h = HealthRecord.query.get_or_404(hid)
    if h.student_id != sid:
        abort(404)
    db.session.delete(h)
    db.session.commit()
    flash("已删除该体检记录", "success")
    return redirect(url_for("students.health_list", sid=sid))


@students_bp.route("/health-summary")
def health_summary():
    """全班健康档案总览(异常预警)"""
    students = Student.query.order_by(Student.student_no).all()
    # 每人最新体检 + 上次体检
    latest_map = {}
    prev_map = {}
    for s in students:
        recs = (HealthRecord.query
                .filter_by(student_id=s.id)
                .order_by(HealthRecord.exam_date.desc()).limit(2).all())
        if recs:
            latest_map[s.id] = recs[0]
            if len(recs) > 1:
                prev_map[s.id] = recs[1]
    # 异常学生
    abnormal_students = [s for s in students
                          if latest_map.get(s.id) and latest_map[s.id].abnormal]
    vision_students = []
    for s in students:
        h = latest_map.get(s.id)
        if h and ((h.vision_left is not None and h.vision_left < 1.0) or
                  (h.vision_right is not None and h.vision_right < 1.0)):
            vision_students.append(s)
    # 视力下降趋势预警: 对比最近两次, 任一眼下降超过 0.2
    vision_decline = []
    for s in students:
        cur = latest_map.get(s.id)
        prev = prev_map.get(s.id)
        if not (cur and prev):
            continue
        for side, attr in [("左眼", "vision_left"), ("右眼", "vision_right")]:
            cv = getattr(cur, attr)
            pv = getattr(prev, attr)
            if cv is not None and pv is not None and pv - cv >= 0.2:
                vision_decline.append({
                    "student": s,
                    "side": side,
                    "prev_vision": pv,
                    "cur_vision": cv,
                    "delta": round(pv - cv, 2),
                    "prev_date": prev.exam_date,
                    "cur_date": cur.exam_date,
                })
    return render_template("students/health_summary.html", students=students,
                            latest_map=latest_map,
                            abnormal_students=abnormal_students,
                            vision_students=vision_students,
                            vision_decline=vision_decline)


# ==================== 学生分组管理 ====================
@students_bp.route("/groups")
def group_list():
    groups = StudentGroup.query.order_by(StudentGroup.created_at.desc()).all()
    # 每组人数
    count_map = {g.id: g.members.count() for g in groups}
    return render_template("students/group_list.html", groups=groups,
                            count_map=count_map,
                            type_choices=StudentGroup.TYPE_CHOICES)


@students_bp.route("/groups/new", methods=["GET", "POST"])
def group_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        group_type = request.form.get("group_type", StudentGroup.TYPE_OTHER)
        note = request.form.get("note", "").strip()
        member_ids = request.form.getlist("member_ids")
        if not name:
            flash("请填写组名", "danger")
            return redirect(url_for("students.group_new"))
        if group_type not in StudentGroup.TYPE_CHOICES:
            group_type = StudentGroup.TYPE_OTHER
        g = StudentGroup(name=name, group_type=group_type, note=note or None)
        db.session.add(g)
        db.session.flush()
        for sid in member_ids:
            try:
                mid = int(sid)
                if Student.query.get(mid):
                    db.session.add(StudentGroupMember(group_id=g.id, student_id=mid))
            except ValueError:
                continue
        db.session.commit()
        flash(f"分组「{name}」已创建", "success")
        return redirect(url_for("students.group_view", gid=g.id))
    students = Student.query.order_by(Student.student_no).all()
    return render_template("students/group_form.html", group=None,
                            students=students,
                            type_choices=StudentGroup.TYPE_CHOICES,
                            action="new")


@students_bp.route("/groups/<int:gid>")
def group_view(gid):
    g = StudentGroup.query.get_or_404(gid)
    members = [m.student for m in g.members.all()]
    all_students = Student.query.order_by(Student.student_no).all()
    member_ids = {s.id for s in members}
    # 按组筛选统计
    # 该组成员最近一次考试成绩
    latest_exam = Exam.query.order_by(Exam.exam_date.desc()).first()
    member_scores = []
    if latest_exam:
        for s in members:
            sr = ScoreRecord.query.filter_by(exam_id=latest_exam.id, student_id=s.id).first()
            member_scores.append({"student": s, "score": sr})
    return render_template("students/group_view.html", g=g, members=members,
                            all_students=all_students, member_ids=member_ids,
                            latest_exam=latest_exam, member_scores=member_scores,
                            type_choices=StudentGroup.TYPE_CHOICES)


@students_bp.route("/groups/<int:gid>/edit", methods=["POST"])
def group_edit(gid):
    g = StudentGroup.query.get_or_404(gid)
    name = request.form.get("name", "").strip()
    if name:
        g.name = name
    g.group_type = request.form.get("group_type", StudentGroup.TYPE_OTHER)
    g.note = request.form.get("note", "").strip() or None
    # 更新成员
    member_ids = set()
    for sid in request.form.getlist("member_ids"):
        try:
            mid = int(sid)
            member_ids.add(mid)
        except ValueError:
            continue
    # 删除不在列表中的
    for m in g.members.all():
        if m.student_id not in member_ids:
            db.session.delete(m)
    # 添加新成员
    existing = {m.student_id for m in g.members.all()}
    for mid in member_ids:
        if mid not in existing and Student.query.get(mid):
            db.session.add(StudentGroupMember(group_id=g.id, student_id=mid))
    db.session.commit()
    flash("分组已更新", "success")
    return redirect(url_for("students.group_view", gid=gid))


@students_bp.route("/groups/<int:gid>/delete", methods=["POST"])
def group_delete(gid):
    g = StudentGroup.query.get_or_404(gid)
    name = g.name
    db.session.delete(g)
    db.session.commit()
    flash(f"已删除分组「{name}」", "success")
    return redirect(url_for("students.group_list"))


# ==================== 干部任职记录 ====================
@students_bp.route("/officers")
def officer_list():
    status = request.args.get("status", "all")
    q = OfficerRecord.query
    if status == "active":
        q = q.filter(OfficerRecord.status == OfficerRecord.STATUS_ACTIVE)
    elif status == "inactive":
        q = q.filter(OfficerRecord.status == OfficerRecord.STATUS_INACTIVE)
    officers = q.order_by(OfficerRecord.start_date.desc(),
                          OfficerRecord.id.desc()).all()
    students = Student.query.order_by(Student.student_no).all()
    return render_template("students/officer_list.html", officers=officers,
                            students=students, status=status,
                            status_choices=OfficerRecord.STATUS_CHOICES,
                            today=date.today().isoformat())


@students_bp.route("/officers/new", methods=["POST"])
def officer_new():
    student_id = request.form.get("student_id", type=int)
    position = request.form.get("position", "").strip()
    start_date_str = request.form.get("start_date", "").strip()
    note = request.form.get("note", "").strip()
    if not student_id or not position:
        flash("请填写学生和职务", "danger")
        return redirect(url_for("students.officer_list"))
    s = Student.query.get_or_404(student_id)
    try:
        sd = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else date.today()
    except ValueError:
        flash("日期格式应为 YYYY-MM-DD", "danger")
        return redirect(url_for("students.officer_list"))
    o = OfficerRecord(student_id=student_id, position=position,
                      start_date=sd, note=note or None)
    db.session.add(o)
    db.session.commit()
    flash(f"已登记 {s.name} 担任 {position}", "success")
    return redirect(url_for("students.officer_list"))


@students_bp.route("/officers/<int:oid>/end", methods=["POST"])
def officer_end(oid):
    o = OfficerRecord.query.get_or_404(oid)
    end_date_str = request.form.get("end_date", "").strip()
    try:
        ed = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else date.today()
    except ValueError:
        ed = date.today()
    if ed < o.start_date:
        flash("卸任日期不能早于任职日期", "danger")
        return redirect(url_for("students.officer_list"))
    o.end_date = ed
    o.status = OfficerRecord.STATUS_INACTIVE
    db.session.commit()
    flash(f"{o.student.name} 已卸任 {o.position}", "success")
    return redirect(url_for("students.officer_list"))


@students_bp.route("/officers/<int:oid>/delete", methods=["POST"])
def officer_delete(oid):
    o = OfficerRecord.query.get_or_404(oid)
    db.session.delete(o)
    db.session.commit()
    flash("已删除该任职记录", "success")
    return redirect(url_for("students.officer_list"))


@students_bp.route("/officers/<int:oid>/certificate")
def officer_certificate(oid):
    """任职证明打印版"""
    o = OfficerRecord.query.get_or_404(oid)
    return render_template("students/officer_certificate.html", o=o,
                            today=date.today())
