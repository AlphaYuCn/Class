"""Excel 模板生成 + 上传解析

模板列表(列顺序固定):
- 学生名单: 学号/姓名/性别/民族/出生日期/身高/身份证号/父亲姓名/父亲电话/母亲姓名/母亲电话/紧急联系人/紧急电话
- 成绩单: 学号/姓名/语文/数学/英语/物理/化学/生物/政治/历史/地理/总分/班级排名/年级排名
"""
from io import BytesIO
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app.utils.zodiac import calc_zodiac


STUDENT_TEMPLATE_HEADERS = ["学号", "姓名", "性别", "民族", "出生日期", "身高", "身份证号",
                            "父亲姓名", "父亲电话", "母亲姓名", "母亲电话", "紧急联系人", "紧急电话"]
SCORE_TEMPLATE_HEADERS = ["学号", "姓名", "语文", "数学", "英语", "物理", "化学",
                            "生物", "政治", "历史", "地理", "总分", "班级排名", "年级排名"]

SCORE_SUBJECT_MAP = {
    "语文": "chinese", "数学": "math", "英语": "english",
    "物理": "physics", "化学": "chemistry", "生物": "biology",
    "政治": "politics", "历史": "history", "地理": "geography",
}


def _style_header(ws, headers):
    fill = PatternFill("solid", fgColor="4472C4")
    font = Font(color="FFFFFF", bold=True, size=11)
    align = Alignment(horizontal="center", vertical="center")
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=i, value=h)
        c.fill = fill
        c.font = font
        c.alignment = align
        ws.column_dimensions[get_column_letter(i)].width = 12
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"


def build_student_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "学生名单"
    _style_header(ws, STUDENT_TEMPLATE_HEADERS)
    # 性别下拉 M/F
    dv = DataValidation(type="list", formula1='"M,F"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"C2:C1000")
    # 联系电话列加宽
    for col_idx in (9, 11, 13):
        ws.column_dimensions[get_column_letter(col_idx)].width = 15
    # 示例行(含家长信息)
    ws.append(["20250001", "张三", "M", "汉族", "2008-05-12", 175, "",
               "张父", "13800138001", "李母", "13900139002", "张父", "13800138001"])
    ws.append(["20250002", "李四", "F", "汉族", "2008-08-08", 165, "",
               "李父", "13700137003", "王母", "13600136004", "", ""])
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()


def build_score_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "成绩单"
    _style_header(ws, SCORE_TEMPLATE_HEADERS)
    # 批注: 总分/排名可空,后端自动算
    ws.cell(row=1, column=12).comment = None
    # 示例行
    ws.append(["20250001", "张三", 110, 120, 105, 80, 75, 70, 80, 75, 70, "", "", ""])
    ws.append(["20250002", "李四", 95, 110, 100, 70, 65, 60, 75, 70, 65, "", "", ""])
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()


def _normalize_header(col):
    """规范化表头: 去空白/全角"""
    if col is None:
        return ""
    return str(col).strip().replace(" ", "").replace("　", "")


def parse_student_excel(file_bytes: bytes):
    """解析学生名单 Excel -> list[dict]
    每行 dict: {student_no, name, gender, ethnicity, birth_date, height, id_card}
    """
    df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
    df.columns = [_normalize_header(c) for c in df.columns]

    required = {"学号", "姓名"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"学生名单缺少必需列: 学号/姓名. 实际列: {list(df.columns)}")

    records = []
    for _, row in df.iterrows():
        if pd.isna(row.get("学号")) or pd.isna(row.get("姓名")):
            continue
        # 性别
        g = str(row.get("性别", "")).strip().upper()
        if g not in ("M", "F"):
            g = "M" if "男" in g else ("F" if "女" in g else None)
        # 出生日期
        bd = row.get("出生日期")
        if pd.notna(bd):
            try:
                bd = pd.to_datetime(bd).date()
            except Exception:
                bd = None
        else:
            bd = None
        # 身高
        h = row.get("身高")
        try:
            h = float(h) if pd.notna(h) else None
        except Exception:
            h = None
        records.append({
            "student_no": str(int(row["学号"])) if isinstance(row["学号"], float) else str(row["学号"]).strip(),
            "name": str(row["姓名"]).strip(),
            "gender": g,
            "ethnicity": str(row.get("民族") or "汉族").strip() or "汉族",
            "birth_date": bd,
            "height": h,
            "id_card": str(row.get("身份证号") or "").strip() or None,
            "father_name": str(row.get("父亲姓名") or "").strip() or None,
            "father_phone": str(row.get("父亲电话") or "").strip() or None,
            "mother_name": str(row.get("母亲姓名") or "").strip() or None,
            "mother_phone": str(row.get("母亲电话") or "").strip() or None,
            "emergency_contact": str(row.get("紧急联系人") or "").strip() or None,
            "emergency_phone": str(row.get("紧急电话") or "").strip() or None,
        })
    if not records:
        raise ValueError("Excel 内没有有效学生记录(请检查学号/姓名是否填写)")
    return records


def parse_score_excel(file_bytes: bytes):
    """解析成绩单 Excel -> list[dict]
    每行 dict: {student_no, name, subjects:{subject:score}, total, class_rank, grade_rank}
    缺考自动 None, 总分/排名 None 时由调用方后算
    """
    df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
    df.columns = [_normalize_header(c) for c in df.columns]

    required = {"学号", "姓名"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"成绩单缺少必需列: 学号/姓名. 实际列: {list(df.columns)}")

    records = []
    for _, row in df.iterrows():
        if pd.isna(row.get("学号")) or pd.isna(row.get("姓名")):
            continue
        subjects = {}
        for cn, key in SCORE_SUBJECT_MAP.items():
            v = row.get(cn)
            if pd.notna(v) and str(v).strip() != "":
                try:
                    subjects[key] = float(v)
                except Exception:
                    pass
        # 总分/排名
        total = row.get("总分")
        try:
            total = float(total) if pd.notna(total) and str(total).strip() != "" else None
        except Exception:
            total = None
        cr = row.get("班级排名")
        try:
            cr = int(cr) if pd.notna(cr) and str(cr).strip() != "" else None
        except Exception:
            cr = None
        gr = row.get("年级排名")
        try:
            gr = int(gr) if pd.notna(gr) and str(gr).strip() != "" else None
        except Exception:
            gr = None
        # 总分后算兜底: 若 total 为空但有 subjects, 用 sum
        if total is None and subjects:
            total = sum(subjects.values())
        records.append({
            "student_no": str(int(row["学号"])) if isinstance(row["学号"], float) else str(row["学号"]).strip(),
            "name": str(row["姓名"]).strip(),
            "subjects": subjects,
            "total": total,
            "class_rank": cr,
            "grade_rank": gr,
        })
    if not records:
        raise ValueError("Excel 内没有有效成绩记录")
    return records


# ==================== 健康体检模板/导入 ====================
HEALTH_TEMPLATE_HEADERS = ["学号", "姓名", "体检日期", "身高", "体重",
                           "左眼视力", "右眼视力", "体检结论", "是否有异常", "异常说明"]


def build_health_template() -> bytes:
    """生成体检结果上传模板 Excel"""
    wb = Workbook()
    ws = wb.active
    ws.title = "体检记录"
    _style_header(ws, HEALTH_TEMPLATE_HEADERS)
    # 异常列下拉 是/否
    dv = DataValidation(type="list", formula1='"是,否"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("I2:I1000")
    # 列宽
    for col_idx, w in enumerate([12, 12, 12, 10, 10, 10, 10, 20, 10, 30], 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = w
    # 示例行
    ws.append(["20250001", "张三", "2026-09-01", 175, 65, 5.0, 4.8, "正常", "否", ""])
    ws.append(["20250002", "李四", "2026-09-01", 165, 55, 4.5, 4.6, "近视", "是", "双眼轻度近视, 建议复查"])
    # 顶部说明
    ws.insert_rows(1)
    ws.cell(row=1, column=1,
            value="说明: 体检日期格式 YYYY-MM-DD; 视力可填 5.0 制或 1.0 制; 异常填'是'时必填异常说明").font = Font(italic=True, color="888888")
    ws.row_dimensions[1].height = 22
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()


def parse_health_excel(file_bytes: bytes):
    """解析体检 Excel -> list[dict]
    每行: {student_no, exam_date, height, weight, vision_left, vision_right,
            result, abnormal, abnormal_note}
    """
    df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
    # 跳过首行说明(若有)
    if len(df) > 0 and isinstance(df.iloc[0, 0], str) and "说明" in str(df.iloc[0, 0]):
        df = df.iloc[1:].reset_index(drop=True)
    df.columns = [_normalize_header(c) for c in df.columns]
    required = {"学号", "姓名", "体检日期"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"体检表缺少必需列: 学号/姓名/体检日期. 实际列: {list(df.columns)}")
    records = []
    for _, row in df.iterrows():
        if pd.isna(row.get("学号")) or pd.isna(row.get("姓名")):
            continue
        # 体检日期
        ed = row.get("体检日期")
        if pd.notna(ed):
            try:
                ed = pd.to_datetime(ed).date()
            except Exception:
                ed = None
        else:
            ed = None
        # 数值字段
        def _float(key):
            v = row.get(key)
            try:
                return float(v) if pd.notna(v) and str(v).strip() != "" else None
            except Exception:
                return None
        # 异常
        ab_str = str(row.get("是否有异常", "")).strip()
        abnormal = ab_str in ("是", "Y", "y", "yes", "true", "1", "异常")
        records.append({
            "student_no": str(int(row["学号"])) if isinstance(row["学号"], float) else str(row["学号"]).strip(),
            "exam_date": ed,
            "height": _float("身高"),
            "weight": _float("体重"),
            "vision_left": _float("左眼视力"),
            "vision_right": _float("右眼视力"),
            "result": str(row.get("体检结论") or "").strip() or None,
            "abnormal": abnormal,
            "abnormal_note": str(row.get("异常说明") or "").strip() or None,
        })
    if not records:
        raise ValueError("Excel 内没有有效体检记录(请检查学号/姓名/体检日期)")
    return records


# ==================== 排座导出/导入 ====================
SEATING_EXPORT_NOTE = (
    "单元格格式: 学号 姓名 (空座留空)。修改后上传可保存为新方案。"
)


def export_seating(sa, students_map) -> bytes:
    """导出排座方案为 Excel
    sa: SeatingArrangement 实例
    students_map: {student_id: Student}
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "座位表"
    # 顶部说明
    ws.cell(row=1, column=1, value=SEATING_EXPORT_NOTE).font = Font(italic=True, color="888888")
    # 第 2 行: 讲台标记 + 列号
    ws.cell(row=2, column=1, value="讲台↓").font = Font(bold=True)
    for c in range(sa.cols):
        cell = ws.cell(row=2, column=c + 2, value=f"第{c+1}列")
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    # 座位网格
    for r in range(sa.rows):
        ws.cell(row=r + 3, column=1, value=f"第{r+1}行").font = Font(bold=True)
        # 找该行该列的 seat
        for c in range(sa.cols):
            seat = next((s for s in sa.seats.all()
                         if s.row_idx == r and s.col_idx == c), None)
            text = ""
            if seat and seat.student_id:
                stu = students_map.get(seat.student_id)
                if stu:
                    text = f"{stu.student_no} {stu.name}"
            cell = ws.cell(row=r + 3, column=c + 2, value=text)
            cell.alignment = Alignment(horizontal="center")
    # 列宽
    ws.column_dimensions["A"].width = 12
    for c in range(sa.cols):
        ws.column_dimensions[get_column_letter(c + 2)].width = 16
    ws.row_dimensions[1].height = 30
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()


def parse_seating_import(file_bytes: bytes, rows: int, cols: int,
                          students_by_no: dict):
    """解析排座 Excel -> grid[[student_id|None, ...], ...]
    每个单元格: 取第一段空白前的 token 作为学号
    """
    df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl", header=None)
    grid = [[None] * cols for _ in range(rows)]
    # 找到网格起点: 跳过说明行 + 表头行, 从第 3 行 (index 2) 开始
    start = 0
    for i in range(min(5, len(df))):
        # 第一列含 "第N行" 字样说明这是网格起点
        val = str(df.iloc[i, 0]) if df.iloc[i, 0] is not None else ""
        if "行" in val:
            start = i
            break
    if start == 0 and len(df) >= 3:
        start = 2  # 默认假设
    for r in range(rows):
        if start + r >= len(df):
            break
        for c in range(cols):
            cell = df.iloc[start + r, c + 1] if c + 1 < df.shape[1] else None
            if cell is None or str(cell).strip() == "":
                grid[r][c] = None
                continue
            token = str(cell).strip().split()[0].split("\n")[0]
            stu = students_by_no.get(token)
            if stu:
                grid[r][c] = stu.id
            else:
                raise ValueError(f"第{r+1}行第{c+1}列: 学号 {token} 未找到学生")
    return grid


# ==================== 值日导出/导入 ====================
DUTY_EXPORT_NOTE = (
    "每组一列, 单元格格式: 学号 姓名。修改后上传可保存为新分组。"
)


def export_duty(groups_data) -> bytes:
    """导出值日分组为 Excel
    groups_data: list[{name: str, members: list[Student]}]
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "值日排程"
    ws.cell(row=1, column=1, value=DUTY_EXPORT_NOTE).font = Font(italic=True, color="888888")
    max_members = max((len(g["members"]) for g in groups_data), default=0)
    # 表头: 组名
    for i, g in enumerate(groups_data):
        cell = ws.cell(row=2, column=i + 1, value=g["name"])
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="4472C4")
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[get_column_letter(i + 1)].width = 18
    # 成员
    for r in range(max_members):
        for i, g in enumerate(groups_data):
            if r < len(g["members"]):
                s = g["members"][r]
                text = f"{s.student_no} {s.name}"
            else:
                text = ""
            cell = ws.cell(row=r + 3, column=i + 1, value=text)
            cell.alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 30
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()


def parse_duty_import(file_bytes: bytes, students_by_no: dict):
    """解析值日 Excel -> list[list[Student]]
    每列一组, 跳过前 2 行(说明 + 表头)
    """
    df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl", header=None)
    if df.shape[0] < 3:
        raise ValueError("Excel 行数不足")
    # 找到表头行: 含组名行
    header_row = 1
    for i in range(min(5, len(df))):
        val = str(df.iloc[i, 0]) if df.iloc[i, 0] is not None else ""
        if "组" in val:
            header_row = i
            break
    groups = []
    for col_idx in range(df.shape[1]):
        header = df.iloc[header_row, col_idx]
        if header is None or str(header).strip() == "":
            continue
        members = []
        for r in range(header_row + 1, len(df)):
            cell = df.iloc[r, col_idx]
            if cell is None or str(cell).strip() == "":
                continue
            token = str(cell).strip().split()[0].split("\n")[0]
            stu = students_by_no.get(token)
            if stu:
                members.append(stu)
            else:
                raise ValueError(f"第{header_row+1+r}行第{col_idx+1}列: 学号 {token} 未找到学生")
        if members:
            groups.append({"name": str(header).strip(), "members": members})
    if not groups:
        raise ValueError("未找到有效分组数据")
    return groups
