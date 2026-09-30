"""工具蓝图 (模块4): 智能排座 + 值日分组"""
import json
from io import BytesIO
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, \
    send_file, abort

from app.extensions import db
from app.models import Student, ScoreRecord, Exam, SeatingArrangement, SeatingSeat, \
    DutyGroup, DutyMember, ClassFee, HealthRecord, \
    DutyChecklistTemplate, DutyCheckRecord, Budget, ParentMeeting, ParentMeetingAttendee
from app.utils.seating import arrange as seating_arrange, build_features
from app.utils.duty import group_students, group_summary
from app.utils.excel import export_seating, parse_seating_import, \
    export_duty, parse_duty_import
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from io import BytesIO
from collections import defaultdict
from datetime import date, datetime
import json as _json

tools_bp = Blueprint("tools", __name__)


@tools_bp.route("/seating", methods=["GET", "POST"])
def seating():
    if request.method == "POST":
        try:
            rows = int(request.form.get("rows", 6))
            cols = int(request.form.get("cols", 8))
            w1 = float(request.form.get("w1", 1.0))
            w2 = float(request.form.get("w2", 1.2))
            w3 = float(request.form.get("w3", 0.6))
            w4 = float(request.form.get("w4", 0.4))
            force = request.form.get("force_same_gender") == "on"
            name = request.form.get("name", "").strip() or f"{rows}行{cols}列排座"
            iterations = int(request.form.get("iterations", 2000))
        except ValueError:
            flash("参数格式错误", "danger")
            return redirect(url_for("tools.seating"))

        if rows <= 0 or cols <= 0 or rows * cols < 1:
            flash("行列数不合法", "danger")
            return redirect(url_for("tools.seating"))

        students = Student.query.order_by(Student.student_no).all()
        if not students:
            flash("没有学生可排座, 请先导入名单", "warning")
            return redirect(url_for("tools.seating"))
        if len(students) > rows * cols:
            flash(f"学生数 {len(students)} 超过座位数 {rows*cols}", "danger")
            return redirect(url_for("tools.seating"))

        # 收集每学生历史成绩
        records_by_sid = defaultdict(list)
        for r in ScoreRecord.query.all():
            records_by_sid[r.student_id].append(r)

        try:
            result = seating_arrange(
                students, records_by_sid, rows, cols,
                w1=w1, w2=w2, w3=w3, w4=w4, force_same_gender=force,
                iterations=iterations, seed=42,
            )
        except Exception as e:
            flash(f"排座失败: {e}", "danger")
            return redirect(url_for("tools.seating"))

        # 保存到数据库
        sa = SeatingArrangement(
            name=name,
            rows=rows,
            cols=cols,
            params_json=json.dumps({"w1": w1, "w2": w2, "w3": w3, "w4": w4,
                                     "force": force, "iterations": iterations}),
            score_total=result["score"].total,
        )
        db.session.add(sa)
        db.session.flush()
        for r in range(rows):
            for c in range(cols):
                sid = result["grid"][r][c]
                seat = SeatingSeat(arrangement_id=sa.id, student_id=sid,
                                    row_idx=r, col_idx=c)
                db.session.add(seat)
        db.session.commit()
        flash(f"排座完成! 总评分 {round(result['score'].total, 2)}", "success")
        return redirect(url_for("tools.seating_view", aid=sa.id))

    # GET: 展示表单 + 最近一次排座
    latest = SeatingArrangement.query.order_by(SeatingArrangement.created_at.desc()).first()
    history = SeatingArrangement.query.order_by(SeatingArrangement.created_at.desc()).limit(10).all()
    return render_template("tools/seating.html", latest=latest, history=history)


@tools_bp.route("/seating/<int:aid>")
def seating_view(aid):
    sa = SeatingArrangement.query.get_or_404(aid)
    seats = sa.seats.all()
    # 构造网格
    grid = [[None] * sa.cols for _ in range(sa.rows)]
    sid_to_student = {s.id: s for s in Student.query.all()}
    for seat in seats:
        grid[seat.row_idx][seat.col_idx] = seat
    params = json.loads(sa.params_json or "{}")
    return render_template("tools/seating_view.html", sa=sa, grid=grid, params=params,
                            sid_to_student=sid_to_student)


@tools_bp.route("/seating/<int:aid>/swap", methods=["POST"])
def seating_swap(aid):
    """手动交换两个座位的学生(支持空座, 拖拽或表单均可)"""
    sa = SeatingArrangement.query.get_or_404(aid)
    r1 = request.form.get("r1", type=int)
    c1 = request.form.get("c1", type=int)
    r2 = request.form.get("r2", type=int)
    c2 = request.form.get("c2", type=int)
    if r1 is None or c1 is None or r2 is None or c2 is None:
        flash("缺少座位坐标参数", "danger")
        return redirect(url_for("tools.seating_view", aid=aid))
    if not (0 <= r1 < sa.rows and 0 <= c1 < sa.cols and 0 <= r2 < sa.rows and 0 <= c2 < sa.cols):
        flash("座位坐标越界", "danger")
        return redirect(url_for("tools.seating_view", aid=aid))
    if r1 == r2 and c1 == c2:
        flash("两个座位坐标相同, 无需交换", "warning")
        return redirect(url_for("tools.seating_view", aid=aid))
    seat1 = SeatingSeat.query.filter_by(arrangement_id=aid, row_idx=r1, col_idx=c1).first()
    seat2 = SeatingSeat.query.filter_by(arrangement_id=aid, row_idx=r2, col_idx=c2).first()
    if not seat1 or not seat2:
        flash("座位不存在", "danger")
        return redirect(url_for("tools.seating_view", aid=aid))
    # 交换 student_id (允许 None 空座)
    # 注意: (arrangement_id, student_id) 有唯一约束,
    # 直接交换会导致中间状态冲突, 所以先用 None 暂存再 flush
    sid1, sid2 = seat1.student_id, seat2.student_id
    seat1.student_id = None
    seat2.student_id = None
    db.session.flush()
    seat1.student_id = sid2
    seat2.student_id = sid1
    db.session.commit()
    flash(f"已交换座位 ({r1+1},{c1+1}) 与 ({r2+1},{c2+1})", "success")
    return redirect(url_for("tools.seating_view", aid=aid))


@tools_bp.route("/seating/<int:aid>/delete", methods=["POST"])
def seating_delete(aid):
    sa = SeatingArrangement.query.get_or_404(aid)
    db.session.delete(sa)
    db.session.commit()
    flash("已删除该排座方案", "success")
    return redirect(url_for("tools.seating"))


@tools_bp.route("/seating/<int:aid>/export")
def seating_export(aid):
    sa = SeatingArrangement.query.get_or_404(aid)
    students_map = {s.id: s for s in Student.query.all()}
    data = export_seating(sa, students_map)
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name=f"{sa.name}_座位表.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@tools_bp.route("/seating/import", methods=["POST"])
def seating_import():
    file = request.files.get("file")
    name = request.form.get("name", "").strip()
    try:
        rows = int(request.form.get("rows", 6))
        cols = int(request.form.get("cols", 8))
    except ValueError:
        flash("行列数格式错误", "danger")
        return redirect(url_for("tools.seating"))
    if not file or not file.filename:
        flash("请选择 Excel 文件", "warning")
        return redirect(url_for("tools.seating"))
    if rows <= 0 or cols <= 0:
        flash("行列数必须 > 0", "danger")
        return redirect(url_for("tools.seating"))

    students = Student.query.all()
    students_by_no = {s.student_no: s for s in students}
    try:
        data = file.read()
        grid = parse_seating_import(data, rows, cols, students_by_no)
    except Exception as e:
        flash(f"导入失败: {e}", "danger")
        return redirect(url_for("tools.seating"))

    # 校验: 学号唯一, 数量不超
    seen = set()
    for r in grid:
        for sid in r:
            if sid is not None:
                if sid in seen:
                    flash("导入失败: 学号重复出现, 请检查 Excel", "danger")
                    return redirect(url_for("tools.seating"))
                seen.add(sid)

    if not name:
        name = f"{rows}行{cols}列导入方案"

    sa = SeatingArrangement(
        name=name, rows=rows, cols=cols,
        params_json=json.dumps({"source": "excel_import"}),
        score_total=0.0,
    )
    db.session.add(sa)
    db.session.flush()
    for r in range(rows):
        for c in range(cols):
            sid = grid[r][c]
            seat = SeatingSeat(arrangement_id=sa.id, student_id=sid,
                                row_idx=r, col_idx=c)
            db.session.add(seat)
    db.session.commit()
    flash(f"已导入排座方案「{name}」, 共 {len(seen)} 人入座", "success")
    return redirect(url_for("tools.seating_view", aid=sa.id))


@tools_bp.route("/duty", methods=["GET", "POST"])
def duty():
    if request.method == "POST":
        try:
            n_groups = int(request.form.get("n_groups", 5))
            members_per_group = request.form.get("members_per_group", "").strip()
            members_per_group = int(members_per_group) if members_per_group else None
        except ValueError:
            flash("参数格式错误", "danger")
            return redirect(url_for("tools.duty"))

        students = Student.query.order_by(Student.student_no).all()
        if not students:
            flash("没有学生可分组, 请先导入名单", "warning")
            return redirect(url_for("tools.duty"))
        if n_groups <= 0:
            flash("组数必须 > 0", "danger")
            return redirect(url_for("tools.duty"))

        try:
            groups = group_students(students, n_groups, members_per_group)
        except ValueError as e:
            flash(f"分组失败: {e}", "danger")
            return redirect(url_for("tools.duty"))

        # 保存
        DutyGroup.query.delete()
        DutyMember.query.delete()
        for i, g in enumerate(groups):
            dg = DutyGroup(name=f"第{i+1}组", order_index=i)
            db.session.add(dg)
            db.session.flush()
            for s in g:
                dm = DutyMember(group_id=dg.id, student_id=s.id)
                db.session.add(dm)
        db.session.commit()
        flash(f"已分组为 {n_groups} 组", "success")
        return redirect(url_for("tools.duty"))

    # GET: 展示当前分组
    groups = DutyGroup.query.order_by(DutyGroup.order_index).all()
    summary = group_summary([[m.student for m in g.members.all()] for g in groups]) if groups else []
    # 各组成员(已按需查询)
    group_data = []
    for g in groups:
        members = g.members.all()
        group_data.append({
            "name": g.name,
            "members": [m.student for m in members],
        })
    return render_template("tools/duty.html", groups=group_data, summary=summary)


@tools_bp.route("/duty/export")
def duty_export():
    groups = DutyGroup.query.order_by(DutyGroup.order_index).all()
    if not groups:
        flash("当前无分组可导出, 请先生成", "warning")
        return redirect(url_for("tools.duty"))
    group_data = []
    for g in groups:
        group_data.append({
            "name": g.name,
            "members": [m.student for m in g.members.all()],
        })
    data = export_duty(group_data)
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name="值日排程表.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@tools_bp.route("/duty/import", methods=["POST"])
def duty_import():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("请选择 Excel 文件", "warning")
        return redirect(url_for("tools.duty"))
    students_by_no = {s.student_no: s for s in Student.query.all()}
    try:
        data = file.read()
        groups_data = parse_duty_import(data, students_by_no)
    except Exception as e:
        flash(f"导入失败: {e}", "danger")
        return redirect(url_for("tools.duty"))

    # 校验: 学号唯一
    seen = set()
    for g in groups_data:
        for s in g["members"]:
            if s.id in seen:
                flash("导入失败: 学号重复出现在多个组", "danger")
                return redirect(url_for("tools.duty"))
            seen.add(s.id)

    # 覆盖现有分组
    DutyGroup.query.delete()
    DutyMember.query.delete()
    for i, g in enumerate(groups_data):
        dg = DutyGroup(name=g["name"] or f"第{i+1}组", order_index=i)
        db.session.add(dg)
        db.session.flush()
        for s in g["members"]:
            db.session.add(DutyMember(group_id=dg.id, student_id=s.id))
    db.session.commit()
    flash(f"已导入 {len(groups_data)} 组, 共 {len(seen)} 人", "success")
    return redirect(url_for("tools.duty"))


# ==================== 班费管理 ====================
@tools_bp.route("/fee", methods=["GET", "POST"])
def fee():
    if request.method == "POST":
        fee_type = request.form.get("fee_type")
        amount_str = request.form.get("amount", "0").strip()
        occurred = request.form.get("occurred_at")
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        if fee_type not in ClassFee.TYPE_CHOICES:
            flash("类型不合法", "danger")
            return redirect(url_for("tools.fee"))
        try:
            amount = float(amount_str)
        except ValueError:
            flash("金额格式错误", "danger")
            return redirect(url_for("tools.fee"))
        if amount <= 0:
            flash("金额必须 > 0", "danger")
            return redirect(url_for("tools.fee"))
        try:
            od = datetime.strptime(occurred, "%Y-%m-%d").date() if occurred else date.today()
        except ValueError:
            flash("日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("tools.fee"))
        fee = ClassFee(fee_type=fee_type, amount=amount, occurred_at=od,
                       category=category or None, description=description or None)
        db.session.add(fee)
        db.session.commit()
        flash(f"已记录{fee.type_label()} {amount:.2f} 元", "success")
        return redirect(url_for("tools.fee"))
    # GET: 列表 + 余额
    fees = ClassFee.query.order_by(ClassFee.occurred_at.desc(),
                                    ClassFee.id.desc()).all()
    total_income = sum(f.amount for f in fees if f.fee_type == ClassFee.TYPE_INCOME)
    total_expense = sum(f.amount for f in fees if f.fee_type == ClassFee.TYPE_EXPENSE)
    balance = total_income - total_expense
    return render_template("tools/fee.html", fees=fees,
                            total_income=total_income,
                            total_expense=total_expense,
                            balance=balance,
                            today=date.today().isoformat())


@tools_bp.route("/fee/<int:fid>/delete", methods=["POST"])
def fee_delete(fid):
    f = ClassFee.query.get_or_404(fid)
    db.session.delete(f)
    db.session.commit()
    flash("已删除该班费记录", "success")
    return redirect(url_for("tools.fee"))


@tools_bp.route("/fee/export")
def fee_export():
    fees = ClassFee.query.order_by(ClassFee.occurred_at.desc(),
                                    ClassFee.id.desc()).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "班费流水"
    # 表头
    headers = ["日期", "类型", "金额(元)", "分类", "说明", "记录时间"]
    for i, h in enumerate(headers):
        c = ws.cell(row=1, column=i + 1, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="4472C4")
        c.alignment = Alignment(horizontal="center")
    for r, f in enumerate(fees):
        ws.cell(row=r + 2, column=1, value=f.occurred_at.isoformat())
        ws.cell(row=r + 2, column=2, value=f.type_label())
        ws.cell(row=r + 2, column=3, value=f.amount)
        ws.cell(row=r + 2, column=4, value=f.category or "")
        ws.cell(row=r + 2, column=5, value=f.description or "")
        ws.cell(row=r + 2, column=6, value=f.created_at.strftime("%Y-%m-%d %H:%M"))
    # 汇总
    total_income = sum(f.amount for f in fees if f.fee_type == ClassFee.TYPE_INCOME)
    total_expense = sum(f.amount for f in fees if f.fee_type == ClassFee.TYPE_EXPENSE)
    summary_row = len(fees) + 3
    ws.cell(row=summary_row, column=1, value="汇总").font = Font(bold=True)
    ws.cell(row=summary_row, column=2, value="收入").font = Font(bold=True)
    ws.cell(row=summary_row, column=3, value=total_income).font = Font(bold=True)
    ws.cell(row=summary_row + 1, column=2, value="支出").font = Font(bold=True)
    ws.cell(row=summary_row + 1, column=3, value=total_expense).font = Font(bold=True)
    ws.cell(row=summary_row + 2, column=2, value="余额").font = Font(bold=True)
    ws.cell(row=summary_row + 2, column=3,
            value=total_income - total_expense).font = Font(bold=True)
    # 列宽
    for i, w in enumerate([12, 8, 12, 12, 30, 18]):
        ws.column_dimensions[get_column_letter(i + 1)].width = w
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return send_file(
        BytesIO(bio.getvalue()),
        as_attachment=True,
        download_name="班费流水.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ==================== 视力/身高排座建议 ====================
@tools_bp.route("/seating/vision")
def seating_vision():
    """基于视力+身高的排座建议（按视力差+身高排序，优先排到前排）"""
    students = Student.query.order_by(Student.student_no).all()
    # 收集每人最新体检数据
    items = []
    for s in students:
        latest_hr = (HealthRecord.query
                     .filter_by(student_id=s.id)
                     .order_by(HealthRecord.exam_date.desc()).first())
        # 视力: 取双眼较低值
        vision = None
        if latest_hr and latest_hr.vision_left is not None and latest_hr.vision_right is not None:
            vision = min(latest_hr.vision_left, latest_hr.vision_right)
        elif latest_hr and latest_hr.vision_left is not None:
            vision = latest_hr.vision_left
        elif latest_hr and latest_hr.vision_right is not None:
            vision = latest_hr.vision_right
        # 身高
        height = s.height
        if latest_hr and latest_hr.height:
            height = latest_hr.height
        items.append({
            "student": s, "vision": vision, "height": height,
            "has_data": latest_hr is not None,
        })
    # 排序: 视力差（低）的在前，身高矮的在前
    def sort_key(it):
        # 无视力数据的视为中等（1.0）
        v = it["vision"] if it["vision"] is not None else 1.0
        # 无身高数据视为中等（165）
        h = it["height"] if it["height"] is not None else 165.0
        return (-v, h)  # 视力低（v小）的负值更小排前面，身高矮的排前面
    items.sort(key=sort_key)
    # 默认 6 行 8 列布局
    rows = 6
    cols = 8
    grid = [[None] * cols for _ in range(rows)]
    for i, it in enumerate(items):
        if i >= rows * cols:
            break
        r = i // cols
        c = i % cols
        grid[r][c] = it["student"]
    # 统计
    total = len(items)
    no_vision = sum(1 for it in items if it["vision"] is None)
    poor_vision = sum(1 for it in items if it["vision"] is not None and it["vision"] < 1.0)
    return render_template("tools/seating_vision.html", grid=grid,
                            rows=rows, cols=cols,
                            items=items, total=total,
                            no_vision=no_vision, poor_vision=poor_vision)


# ==================== 值日检查清单 ====================
@tools_bp.route("/duty/checklist", methods=["GET", "POST"])
def duty_checklist():
    """检查项模板管理"""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        items_text = request.form.get("items", "").strip()
        if not name or not items_text:
            flash("请填写清单名称和检查项", "danger")
            return redirect(url_for("tools.duty_checklist"))
        items = [item.strip() for item in items_text.split("\n") if item.strip()]
        if not items:
            flash("至少需要一项检查项", "danger")
            return redirect(url_for("tools.duty_checklist"))
        t = DutyChecklistTemplate(name=name, items_json=_json.dumps(items, ensure_ascii=False))
        db.session.add(t)
        db.session.commit()
        flash(f"已创建检查清单「{name}」（{len(items)} 项）", "success")
        return redirect(url_for("tools.duty_checklist"))
    templates = DutyChecklistTemplate.query.order_by(DutyChecklistTemplate.created_at.desc()).all()
    # 解析每模板的检查项
    parsed = []
    for t in templates:
        try:
            items = _json.loads(t.items_json) if t.items_json else []
        except Exception:
            items = []
        parsed.append({"template": t, "items": items})
    return render_template("tools/duty_checklist.html", parsed=parsed)


@tools_bp.route("/duty/checklist/<int:tid>/delete", methods=["POST"])
def duty_checklist_delete(tid):
    t = DutyChecklistTemplate.query.get_or_404(tid)
    name = t.name
    db.session.delete(t)
    db.session.commit()
    flash(f"已删除清单「{name}」", "success")
    return redirect(url_for("tools.duty_checklist"))


@tools_bp.route("/duty/check", methods=["GET", "POST"])
def duty_check():
    """录入一次检查记录"""
    if request.method == "POST":
        check_date_str = request.form.get("check_date", "").strip()
        group_id = request.form.get("group_id", type=int)
        template_id = request.form.get("template_id", type=int)
        note = request.form.get("note", "").strip()
        try:
            cd = datetime.strptime(check_date_str, "%Y-%m-%d").date() if check_date_str else date.today()
        except ValueError:
            flash("日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("tools.duty_check"))
        # 收集各项得分：score_<idx>
        scores = {}
        total = 0
        for key, val in request.form.items():
            if not key.startswith("score_"):
                continue
            try:
                idx = int(key[6:])
                v = float(val) if val.strip() else 0
                scores[str(idx)] = v
                total += v
            except ValueError:
                continue
        rec = DutyCheckRecord(
            check_date=cd,
            group_id=group_id if group_id else None,
            template_id=template_id if template_id else None,
            scores_json=_json.dumps(scores, ensure_ascii=False) if scores else None,
            total_score=total,
            note=note or None,
        )
        db.session.add(rec)
        db.session.commit()
        flash(f"已保存检查记录（总分 {total}）", "success")
        return redirect(url_for("tools.duty_check_detail", rid=rec.id))
    # GET: 显示表单
    templates = DutyChecklistTemplate.query.order_by(DutyChecklistTemplate.created_at.desc()).all()
    groups = DutyGroup.query.order_by(DutyGroup.order_index).all()
    selected_tid = request.args.get("tid", type=int)
    selected_items = []
    selected_template = None
    if selected_tid:
        selected_template = DutyChecklistTemplate.query.get(selected_tid)
        if selected_template:
            try:
                selected_items = _json.loads(selected_template.items_json) if selected_template.items_json else []
            except Exception:
                selected_items = []
    return render_template("tools/duty_check_form.html",
                            templates=templates, groups=groups,
                            selected_template=selected_template,
                            selected_items=selected_items,
                            today=date.today().isoformat())


@tools_bp.route("/duty/check/<int:rid>")
def duty_check_detail(rid):
    """检查记录详情"""
    rec = DutyCheckRecord.query.get_or_404(rid)
    items = []
    if rec.template and rec.template.items_json:
        try:
            item_names = _json.loads(rec.template.items_json)
            scores = _json.loads(rec.scores_json) if rec.scores_json else {}
            for i, name in enumerate(item_names):
                items.append({
                    "name": name,
                    "score": scores.get(str(i), None),
                })
        except Exception:
            pass
    return render_template("tools/duty_check_detail.html", rec=rec, items=items)


@tools_bp.route("/duty/check/list")
def duty_check_list():
    """检查记录列表"""
    records = DutyCheckRecord.query.order_by(DutyCheckRecord.check_date.desc(),
                                              DutyCheckRecord.id.desc()).all()
    return render_template("tools/duty_check_list.html", records=records)


@tools_bp.route("/duty/check/<int:rid>/delete", methods=["POST"])
def duty_check_delete(rid):
    rec = DutyCheckRecord.query.get_or_404(rid)
    db.session.delete(rec)
    db.session.commit()
    flash("已删除该检查记录", "success")
    return redirect(url_for("tools.duty_check_list"))


# ==================== 班费预算管理 ====================
@tools_bp.route("/fee/budget", methods=["GET", "POST"])
def fee_budget():
    """班费预算管理 + 执行率分析"""
    if request.method == "POST":
        term = request.form.get("term", "").strip()
        category = request.form.get("category", "").strip()
        amount_str = request.form.get("amount", "").strip()
        note = request.form.get("note", "").strip()
        if not term or not category or not amount_str:
            flash("学期、分类、金额必填", "danger")
            return redirect(url_for("tools.fee_budget"))
        try:
            amount = float(amount_str)
        except ValueError:
            flash("金额需为数字", "danger")
            return redirect(url_for("tools.fee_budget"))
        existing = Budget.query.filter_by(term=term, category=category).first()
        if existing:
            existing.amount = amount
            existing.note = note or None
        else:
            db.session.add(Budget(term=term, category=category, amount=amount, note=note or None))
        db.session.commit()
        flash("已保存预算", "success")
        return redirect(url_for("tools.fee_budget"))
    # 默认当前学期
    today = date.today()
    default_term = f"{today.year}{'秋' if today.month >= 8 else '春'}"
    term = request.args.get("term", default_term)
    budgets = Budget.query.filter_by(term=term).order_by(Budget.category).all()
    # 实际支出（按 category 聚合 ClassFee）
    actual_map = {}
    fees = ClassFee.query.filter(ClassFee.category.isnot(None)).all()
    for f in fees:
        if f.fee_type == ClassFee.TYPE_EXPENSE and f.category:
            actual_map[f.category] = actual_map.get(f.category, 0) + f.amount
    # 汇总
    budget_total = sum(b.amount for b in budgets)
    actual_total = sum(actual_map.get(b.category, 0) for b in budgets)
    over_budget = [(b, actual_map.get(b.category, 0)) for b in budgets
                   if actual_map.get(b.category, 0) > b.amount]
    # 总余额（收入-支出）
    total_income = sum(f.amount for f in ClassFee.query.filter_by(fee_type=ClassFee.TYPE_INCOME).all())
    total_expense = sum(f.amount for f in ClassFee.query.filter_by(fee_type=ClassFee.TYPE_EXPENSE).all())
    return render_template("tools/fee_budget.html", budgets=budgets,
                            actual_map=actual_map, term=term,
                            budget_total=budget_total, actual_total=actual_total,
                            over_budget=over_budget,
                            total_income=total_income, total_expense=total_expense,
                            balance=total_income - total_expense)


@tools_bp.route("/fee/budget/<int:bid>/delete", methods=["POST"])
def fee_budget_delete(bid):
    b = Budget.query.get_or_404(bid)
    db.session.delete(b)
    db.session.commit()
    flash("已删除该预算项", "success")
    return redirect(url_for("tools.fee_budget"))


# ==================== 家长会工具 ====================
@tools_bp.route("/meeting")
def meeting_list():
    meetings = ParentMeeting.query.order_by(ParentMeeting.held_at.desc()).all()
    # 每次会议签到人数
    count_map = {m.id: m.attendees.count() for m in meetings}
    return render_template("tools/meeting_list.html", meetings=meetings,
                            count_map=count_map)


@tools_bp.route("/meeting/new", methods=["GET", "POST"])
def meeting_new():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        held_at_str = request.form.get("held_at", "").strip()
        term = request.form.get("term", "").strip()
        agenda = request.form.get("agenda", "").strip()
        notice = request.form.get("notice", "").strip()
        summary = request.form.get("summary", "").strip()
        if not title:
            flash("请填写主题", "danger")
            return redirect(url_for("tools.meeting_new"))
        try:
            hd = datetime.strptime(held_at_str, "%Y-%m-%d").date() if held_at_str else date.today()
        except ValueError:
            flash("日期格式应为 YYYY-MM-DD", "danger")
            return redirect(url_for("tools.meeting_new"))
        m = ParentMeeting(title=title, held_at=hd, term=term or None,
                          agenda=agenda or None, notice=notice or None,
                          summary=summary or None)
        db.session.add(m)
        db.session.commit()
        flash(f"已创建家长会「{title}」", "success")
        return redirect(url_for("tools.meeting_detail", mid=m.id))
    today = date.today()
    default_term = f"{today.year}{'秋' if today.month >= 8 else '春'}"
    return render_template("tools/meeting_form.html", meeting=None,
                            default_term=default_term,
                            today=today.isoformat())


@tools_bp.route("/meeting/<int:mid>", methods=["GET", "POST"])
def meeting_detail(mid):
    """家长会详情 + 签到"""
    m = ParentMeeting.query.get_or_404(mid)
    if request.method == "POST":
        # 签到: 添加家长
        student_id = request.form.get("student_id", type=int)
        parent_name = request.form.get("parent_name", "").strip()
        if not student_id:
            flash("请选择学生", "danger")
            return redirect(url_for("tools.meeting_detail", mid=mid))
        # 检查重复签到
        existing = ParentMeetingAttendee.query.filter_by(meeting_id=mid, student_id=student_id).first()
        if existing:
            flash("该学生家长已签到", "warning")
            return redirect(url_for("tools.meeting_detail", mid=mid))
        s = Student.query.get_or_404(student_id)
        db.session.add(ParentMeetingAttendee(
            meeting_id=mid, student_id=student_id,
            parent_name=parent_name or None,
        ))
        db.session.commit()
        flash(f"{s.name} 家长已签到", "success")
        return redirect(url_for("tools.meeting_detail", mid=mid))
    attendees = m.attendees.order_by(ParentMeetingAttendee.id).all()
    students = Student.query.order_by(Student.student_no).all()
    # 签到率
    total_students = Student.query.count()
    signed = len(attendees)
    rate = (signed / total_students * 100) if total_students > 0 else 0
    return render_template("tools/meeting_detail.html", m=m,
                            attendees=attendees, students=students,
                            total_students=total_students, signed=signed,
                            rate=round(rate, 1))


@tools_bp.route("/meeting/<int:mid>/attendee/<int:aid>/delete", methods=["POST"])
def meeting_attendee_delete(mid, aid):
    a = ParentMeetingAttendee.query.get_or_404(aid)
    if a.meeting_id != mid:
        abort(404)
    db.session.delete(a)
    db.session.commit()
    flash("已删除该签到记录", "success")
    return redirect(url_for("tools.meeting_detail", mid=mid))


@tools_bp.route("/meeting/<int:mid>/delete", methods=["POST"])
def meeting_delete(mid):
    m = ParentMeeting.query.get_or_404(mid)
    title = m.title
    db.session.delete(m)
    db.session.commit()
    flash(f"已删除家长会「{title}」", "success")
    return redirect(url_for("tools.meeting_list"))
