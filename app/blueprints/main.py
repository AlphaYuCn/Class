"""首页蓝图"""
from datetime import date, timedelta
from flask import Blueprint, render_template
from app.models import Student, Exam, SeatingArrangement, ClassFee

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    stats = {
        "student_count": Student.query.count(),
        "exam_count": Exam.query.count(),
        "seating_count": SeatingArrangement.query.count(),
    }
    # 班费余额
    fees = ClassFee.query.all()
    total_income = sum(f.amount for f in fees if f.fee_type == ClassFee.TYPE_INCOME)
    total_expense = sum(f.amount for f in fees if f.fee_type == ClassFee.TYPE_EXPENSE)
    stats["fee_balance"] = total_income - total_expense
    latest_exam = Exam.query.order_by(Exam.exam_date.desc()).first()
    # 本月 + 近 7 天生日学生
    today = date.today()
    students = Student.query.filter(Student.birth_date.isnot(None)).all()
    month_birthday = []
    upcoming_7days = []
    end_window = today + timedelta(days=7)
    for s in students:
        if not s.birth_date:
            continue
        # 本月生日
        if s.birth_date.month == today.month:
            month_birthday.append(s)
        # 近 7 天生日(按月日匹配, 跨年处理)
        try:
            this_year_bd = s.birth_date.replace(year=today.year)
        except ValueError:
            # 2/29 -> 2/28
            this_year_bd = s.birth_date.replace(year=today.year, day=28)
        if today <= this_year_bd <= end_window:
            upcoming_7days.append((s, this_year_bd))
    month_birthday.sort(key=lambda s: s.birth_date.day)
    upcoming_7days.sort(key=lambda x: x[1])
    return render_template("index.html", stats=stats, latest_exam=latest_exam,
                            month_birthday=month_birthday,
                            upcoming_7days=upcoming_7days,
                            today=today, tomorrow=today + timedelta(days=1))
