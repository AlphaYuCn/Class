"""演示数据生成器: 40 学生 + 2 次考试 + 若干日常记录"""
import random
from datetime import date, timedelta
from app.extensions import db
from app.models import Student, Exam, ScoreRecord, DailyRecord
from app.utils.zodiac import calc_zodiac
from app.utils.ranking import compute_class_rank

SURNAMES = list("王李张刘陈杨黄赵周吴徐孙朱马胡郭林何高梁郑")
GIVEN_M = ["浩然", "宇航", "俊杰", "天佑", "睿", "博", "晨阳", "雨泽", "鸿煊", "鹏涛"]
GIVEN_F = ["诗涵", "雨欣", "梓涵", "怡然", "欣怡", "梦琪", "佳怡", "若彤", "雨萱", "睿婕"]
ETHNICS = ["汉族", "回族", "满族", "壮族", "苗族", "维吾尔族"]


def _rand_name(gender, rng):
    surname = rng.choice(SURNAMES)
    given = rng.choice(GIVEN_M if gender == "M" else GIVEN_F)
    return surname + given


def seed_all(students_count=40, seed=20260928):
    rng = random.Random(seed)
    # 清空(谨慎: 仅演示场景使用)
    db.session.query(DailyRecord).delete()
    db.session.query(ScoreRecord).delete()
    db.session.query(Exam).delete()
    db.session.query(Student).delete()
    db.session.commit()

    # 生成学生
    base_date = date(2008, 1, 1)
    end_date = date(2008, 12, 31)
    days_span = (end_date - base_date).days

    students = []
    for i in range(1, students_count + 1):
        gender = rng.choices(["M", "F"], weights=[1, 1])[0]
        birth = base_date + timedelta(days=rng.randint(0, days_span))
        zname, elem = calc_zodiac(birth)
        s = Student(
            student_no=f"2025{i:03d}",
            name=_rand_name(gender, rng),
            gender=gender,
            ethnicity=rng.choice(ETHNICS),
            birth_date=birth,
            height=float(rng.randint(155, 185) if gender == "M" else rng.randint(150, 175)),
            id_card=None,
            zodiac_sign=zname,
            zodiac_element=elem,
        )
        students.append(s)
        db.session.add(s)
    db.session.flush()

    # 两次考试
    exam1 = Exam(name="2025年10月月考", exam_date=date(2025, 10, 15),
                  year=2025, month=10)
    exam2 = Exam(name="2025年11月月考", exam_date=date(2025, 11, 20),
                  year=2025, month=11)
    db.session.add_all([exam1, exam2])
    db.session.flush()

    for exam in (exam1, exam2):
        records = []
        # 给每个学生生成成绩(随机但稳定: 用学号尾数种子)
        for s in students:
            local_rng = random.Random(seed + int(s.student_no[-3:]) + (exam.id * 1000))
            # 各科基础分 ± 随机扰动
            subjects = {}
            for subj in ScoreRecord.SUBJECTS:
                # 语数外 60-145, 选科 35-95
                full = 150 if subj in ("chinese", "math", "english") else 100
                base = full * 0.6 + local_rng.uniform(-0.1, 0.3) * full
                if local_rng.random() < 0.05:
                    subjects[subj] = None  # 5% 缺考
                else:
                    subjects[subj] = round(max(0, base), 1)
            total = sum(v for v in subjects.values() if v is not None)
            r = ScoreRecord(
                exam_id=exam.id,
                student_id=s.id,
                total=total,
                **{k: subjects.get(k) for k in ScoreRecord.SUBJECTS},
            )
            records.append(r)
            db.session.add(r)
        compute_class_rank(records)
        # 给一个年级排名(随机, 略大于班级排名)
        for r in records:
            r.grade_rank = r.class_rank + rng.randint(50, 200)
    db.session.flush()

    # 日常记录
    record_types = ["late", "late", "late", "leave", "distraction", "discipline",
                    "praise", "reward", "other"]
    descs = {
        "late": ["早读迟到", "上课迟到 5 分钟", "午休后迟到"],
        "leave": ["病假半天", "事假一天", "家中有事请假"],
        "distraction": ["上课看课外书", "传纸条", "走神发呆"],
        "discipline": ["未交作业", "自习讲话", "走廊追逐"],
        "praise": ["帮助同学讲题", "主动擦黑板", "课堂发言积极"],
        "reward": ["月度进步奖", "纪律之星", "志愿服务时长"],
        "other": ["其他事项"],
    }
    today = date.today()
    for s in students:
        # 每人 0-5 条记录
        n = rng.randint(0, 5)
        for _ in range(n):
            rtype = rng.choice(record_types)
            d = DailyRecord(
                student_id=s.id,
                record_type=rtype,
                occurred_at=today - timedelta(days=rng.randint(0, 90)),
                description=rng.choice(descs[rtype]),
                severity=rng.randint(1, 3) if rtype in ("late", "distraction", "discipline") else 0,
            )
            db.session.add(d)

    db.session.commit()
    return {
        "students": len(students),
        "exams": 2,
        "records": DailyRecord.query.count(),
    }
