"""ORM 模型: 8 张表

约定:
- 性别/星座用英文枚举存储, 展示层转中文
- daily_record 合表用 record_type 区分(请假/迟到/溜号/违纪/表扬/奖励)
"""
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, Index, func

from app.extensions import db


# ---------- 学生基本信息 ----------
class Student(db.Model):
    __tablename__ = "student"

    id = db.Column(db.Integer, primary_key=True)
    student_no = db.Column(db.String(20), unique=True, nullable=False, index=True, comment="学号")
    name = db.Column(db.String(50), nullable=False, index=True, comment="姓名")
    gender = db.Column(db.String(1), nullable=True, comment="性别 M/F")
    ethnicity = db.Column(db.String(20), default="汉族", comment="民族")
    birth_date = db.Column(db.Date, nullable=True, comment="出生日期")
    id_card = db.Column(db.String(18), nullable=True, comment="身份证号")
    height = db.Column(db.Float, nullable=True, comment="身高cm")
    zodiac_sign = db.Column(db.String(10), nullable=True, comment="星座")
    zodiac_element = db.Column(db.String(2), nullable=True, comment="四象 火/风/土/水")
    father_name = db.Column(db.String(50), nullable=True, comment="父亲姓名")
    father_phone = db.Column(db.String(20), nullable=True, comment="父亲电话")
    mother_name = db.Column(db.String(50), nullable=True, comment="母亲姓名")
    mother_phone = db.Column(db.String(20), nullable=True, comment="母亲电话")
    emergency_contact = db.Column(db.String(50), nullable=True, comment="紧急联系人")
    emergency_phone = db.Column(db.String(20), nullable=True, comment="紧急电话")
    note = db.Column(db.Text, nullable=True, comment="备注")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    scores = db.relationship("ScoreRecord", backref="student", lazy="dynamic")
    daily_records = db.relationship("DailyRecord", backref="student", lazy="dynamic")

    def __repr__(self):
        return f"<Student {self.student_no} {self.name}>"

    def to_dict(self):
        return {
            "id": self.id,
            "student_no": self.student_no,
            "name": self.name,
            "gender": self.gender,
            "ethnicity": self.ethnicity,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "id_card": self.id_card,
            "height": self.height,
            "zodiac_sign": self.zodiac_sign,
            "zodiac_element": self.zodiac_element,
        }


# ---------- 考试 ----------
class Exam(db.Model):
    __tablename__ = "exam"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, comment="考试名称")
    exam_date = db.Column(db.Date, nullable=False, index=True, comment="考试日期")
    year = db.Column(db.Integer, nullable=False, comment="年")
    month = db.Column(db.Integer, nullable=False, comment="月")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    scores = db.relationship("ScoreRecord", backref="exam", lazy="dynamic")

    def __repr__(self):
        return f"<Exam {self.name} {self.exam_date}>"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "exam_date": self.exam_date.isoformat() if self.exam_date else None,
            "year": self.year,
            "month": self.month,
        }


# ---------- 成绩记录 ----------
class ScoreRecord(db.Model):
    __tablename__ = "score_record"

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)

    chinese = db.Column(db.Float, nullable=True, comment="语文")
    math = db.Column(db.Float, nullable=True, comment="数学")
    english = db.Column(db.Float, nullable=True, comment="英语")
    physics = db.Column(db.Float, nullable=True, comment="物理")
    chemistry = db.Column(db.Float, nullable=True, comment="化学")
    biology = db.Column(db.Float, nullable=True, comment="生物")
    politics = db.Column(db.Float, nullable=True, comment="政治")
    history = db.Column(db.Float, nullable=True, comment="历史")
    geography = db.Column(db.Float, nullable=True, comment="地理")
    total = db.Column(db.Float, nullable=True, comment="总分")
    class_rank = db.Column(db.Integer, nullable=True, comment="班级排名")
    grade_rank = db.Column(db.Integer, nullable=True, comment="年级排名")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", name="uq_exam_student"),
        Index("ix_exam_class_rank", "exam_id", "class_rank"),
    )

    SUBJECTS = ["chinese", "math", "english", "physics", "chemistry",
                "biology", "politics", "history", "geography"]

    def subject_scores(self):
        """返回 {subject: score} 不含 None"""
        return {k: getattr(self, k) for k in self.SUBJECTS if getattr(self, k) is not None}

    def __repr__(self):
        return f"<ScoreRecord exam={self.exam_id} student={self.student_id} total={self.total}>"


# ---------- 日常记录(请假/迟到/溜号/违纪/表扬/奖励) ----------
class DailyRecord(db.Model):
    __tablename__ = "daily_record"

    TYPE_LEAVE = "leave"
    TYPE_LATE = "late"
    TYPE_DISTRACTION = "distraction"
    TYPE_DISCIPLINE = "discipline"
    TYPE_PRAISE = "praise"
    TYPE_REWARD = "reward"
    TYPE_OTHER = "other"

    TYPE_CHOICES = {
        TYPE_LEAVE: "请假",
        TYPE_LATE: "迟到",
        TYPE_DISTRACTION: "上课溜号",
        TYPE_DISCIPLINE: "违纪",
        TYPE_PRAISE: "表扬",
        TYPE_REWARD: "奖励",
        TYPE_OTHER: "其他",
    }
    PRAISE_TYPES = {TYPE_PRAISE, TYPE_REWARD}

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    record_type = db.Column(db.String(20), nullable=False, comment="记录类型")
    occurred_at = db.Column(db.Date, nullable=False, index=True, comment="发生日期")
    description = db.Column(db.Text, nullable=True, comment="描述")
    severity = db.Column(db.Integer, default=0, comment="严重程度 0中性 正违纪")
    # 请假扩展字段（仅 record_type='leave' 时使用）
    start_date = db.Column(db.Date, nullable=True, comment="请假开始日期")
    end_date = db.Column(db.Date, nullable=True, comment="请假结束日期")
    leave_days = db.Column(db.Float, nullable=True, comment="请假天数")
    leave_reason = db.Column(db.String(100), nullable=True, comment="请假原因")
    parent_notified = db.Column(db.Boolean, default=False, comment="家长是否知晓")
    cancel_date = db.Column(db.Date, nullable=True, comment="销假日期")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        Index("ix_student_occurred", "student_id", "occurred_at"),
    )

    def type_label(self):
        return self.TYPE_CHOICES.get(self.record_type, self.record_type)

    def is_praise(self):
        return self.record_type in self.PRAISE_TYPES

    def is_leave(self):
        return self.record_type == self.TYPE_LEAVE

    def is_active_leave(self):
        """是否仍在请假中(未销假)"""
        return self.is_leave() and self.cancel_date is None

    def __repr__(self):
        return f"<DailyRecord {self.record_type} {self.occurred_at} student={self.student_id}>"


# ---------- 座位安排 ----------
class SeatingArrangement(db.Model):
    __tablename__ = "seating_arrangement"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, comment="安排名称")
    rows = db.Column(db.Integer, nullable=False, comment="行数")
    cols = db.Column(db.Integer, nullable=False, comment="列数")
    params_json = db.Column(db.Text, nullable=True, comment="权重配置 JSON")
    score_total = db.Column(db.Float, default=0, comment="总评分")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    seats = db.relationship("SeatingSeat", backref="arrangement",
                            lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SeatingArrangement {self.name} {self.rows}x{self.cols}>"


class SeatingSeat(db.Model):
    __tablename__ = "seating_seat"

    id = db.Column(db.Integer, primary_key=True)
    arrangement_id = db.Column(db.Integer, db.ForeignKey("seating_arrangement.id"),
                                nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=True, comment="空座为 None")
    row_idx = db.Column(db.Integer, nullable=False, comment="0-based 行号")
    col_idx = db.Column(db.Integer, nullable=False, comment="0-based 列号")

    student = db.relationship("Student", lazy="joined")

    __table_args__ = (
        UniqueConstraint("arrangement_id", "row_idx", "col_idx", name="uq_arr_row_col"),
        UniqueConstraint("arrangement_id", "student_id", name="uq_arr_student"),
    )


# ---------- 值日分组 ----------
class DutyGroup(db.Model):
    __tablename__ = "duty_group"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False, comment="第N组")
    order_index = db.Column(db.Integer, default=0, comment="排序")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    members = db.relationship("DutyMember", backref="group",
                                lazy="dynamic", cascade="all, delete-orphan")


class DutyMember(db.Model):
    __tablename__ = "duty_member"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("duty_group.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)

    student = db.relationship("Student", lazy="joined")

    __table_args__ = (
        UniqueConstraint("group_id", "student_id", name="uq_group_student"),
    )


# ---------- 班费收支 ----------
class ClassFee(db.Model):
    __tablename__ = "class_fee"

    TYPE_INCOME = "income"
    TYPE_EXPENSE = "expense"
    TYPE_CHOICES = {TYPE_INCOME: "收入", TYPE_EXPENSE: "支出"}

    id = db.Column(db.Integer, primary_key=True)
    fee_type = db.Column(db.String(10), nullable=False, comment="income/expense")
    amount = db.Column(db.Float, nullable=False, comment="金额(元)")
    occurred_at = db.Column(db.Date, nullable=False, index=True, comment="发生日期")
    category = db.Column(db.String(30), nullable=True, comment="分类: 班费/活动/采购/其他")
    description = db.Column(db.String(200), nullable=True, comment="说明")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def type_label(self):
        return self.TYPE_CHOICES.get(self.fee_type, self.fee_type)


# ---------- 学生评语 ----------
class StudentComment(db.Model):
    __tablename__ = "student_comment"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    term = db.Column(db.String(20), nullable=False, comment="学期: 如 2025秋季")
    content = db.Column(db.Text, nullable=True, comment="评语正文")
    is_draft = db.Column(db.Boolean, default=True, comment="是否草稿")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    student = db.relationship("Student", lazy="joined")

    __table_args__ = (
        UniqueConstraint("student_id", "term", name="uq_student_term"),
    )


# ---------- 家校联系日志 ----------
class ParentContact(db.Model):
    """班主任与家长沟通记录"""
    __tablename__ = "parent_contact"

    TYPE_PHONE = "phone"
    TYPE_WECHAT = "wechat"
    TYPE_MEET = "meet"
    TYPE_HOME_VISIT = "home_visit"
    TYPE_OTHER = "other"

    TYPE_CHOICES = {
        TYPE_PHONE: "电话",
        TYPE_WECHAT: "微信",
        TYPE_MEET: "面谈",
        TYPE_HOME_VISIT: "家访",
        TYPE_OTHER: "其他",
    }

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    contact_date = db.Column(db.Date, nullable=False, index=True, comment="沟通日期")
    contact_type = db.Column(db.String(20), nullable=False, comment="沟通方式")
    contact_person = db.Column(db.String(50), nullable=True, comment="沟通对象(父/母/其他)")
    content = db.Column(db.Text, nullable=True, comment="沟通内容")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    student = db.relationship("Student", lazy="joined")

    def type_label(self):
        return self.TYPE_CHOICES.get(self.contact_type, self.contact_type)


# ---------- 目标成绩 ----------
class ScoreGoal(db.Model):
    """学生目标成绩（按学期设定，可选关联到具体考试）"""
    __tablename__ = "score_goal"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    term = db.Column(db.String(20), nullable=False, comment="学期: 如 2026秋季")
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=True,
                        comment="关联到具体考试(可选), 为空表示学期总目标")
    # 各科目标 + 总分目标
    chinese = db.Column(db.Float, nullable=True)
    math = db.Column(db.Float, nullable=True)
    english = db.Column(db.Float, nullable=True)
    physics = db.Column(db.Float, nullable=True)
    chemistry = db.Column(db.Float, nullable=True)
    biology = db.Column(db.Float, nullable=True)
    politics = db.Column(db.Float, nullable=True)
    history = db.Column(db.Float, nullable=True)
    geography = db.Column(db.Float, nullable=True)
    total = db.Column(db.Float, nullable=True, comment="总分目标")
    class_rank_target = db.Column(db.Integer, nullable=True, comment="班级排名目标")
    note = db.Column(db.Text, nullable=True, comment="目标说明")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    student = db.relationship("Student", lazy="joined")
    exam = db.relationship("Exam", lazy="joined")

    SUBJECTS = ["chinese", "math", "english", "physics", "chemistry",
                "biology", "politics", "history", "geography"]

    def subject_targets(self):
        return {k: getattr(self, k) for k in self.SUBJECTS if getattr(self, k) is not None}

    def __repr__(self):
        return f"<ScoreGoal student={self.student_id} term={self.term} total={self.total}>"


# ---------- 学生照片 ----------
class StudentPhoto(db.Model):
    """学生照片(档案/PDF 自动嵌入)"""
    __tablename__ = "student_photo"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    photo_path = db.Column(db.String(255), nullable=False, comment="相对 static 路径")
    is_primary = db.Column(db.Boolean, default=False, comment="是否主照片")
    taken_at = db.Column(db.Date, nullable=True, comment="拍摄日期")
    note = db.Column(db.String(100), nullable=True, comment="说明")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    student = db.relationship("Student", lazy="joined")


# ---------- 健康体检 ----------
class HealthRecord(db.Model):
    """健康体检记录"""
    __tablename__ = "health_record"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    exam_date = db.Column(db.Date, nullable=False, index=True, comment="体检日期")
    height = db.Column(db.Float, nullable=True, comment="身高cm")
    weight = db.Column(db.Float, nullable=True, comment="体重kg")
    vision_left = db.Column(db.Float, nullable=True, comment="左眼视力")
    vision_right = db.Column(db.Float, nullable=True, comment="右眼视力")
    result = db.Column(db.Text, nullable=True, comment="体检结果")
    abnormal = db.Column(db.Boolean, default=False, comment="是否有异常")
    abnormal_note = db.Column(db.String(200), nullable=True, comment="异常说明")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    student = db.relationship("Student", lazy="joined")


# ---------- 学生分组 ----------
class StudentGroup(db.Model):
    """自定义分组(住宿/走读/兴趣小组/学习互助组)"""
    __tablename__ = "student_group"

    TYPE_BOARDING = "boarding"
    TYPE_DAY = "day"
    TYPE_INTEREST = "interest"
    TYPE_STUDY = "study"
    TYPE_OTHER = "other"
    TYPE_CHOICES = {
        TYPE_BOARDING: "住宿",
        TYPE_DAY: "走读",
        TYPE_INTEREST: "兴趣小组",
        TYPE_STUDY: "学习互助组",
        TYPE_OTHER: "其他",
    }

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, comment="组名")
    group_type = db.Column(db.String(20), default=TYPE_OTHER, comment="分组类型")
    note = db.Column(db.String(200), nullable=True, comment="说明")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    members = db.relationship("StudentGroupMember", backref="group",
                              lazy="dynamic", cascade="all, delete-orphan")

    def type_label(self):
        return self.TYPE_CHOICES.get(self.group_type, self.group_type)


class StudentGroupMember(db.Model):
    __tablename__ = "student_group_member"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("student_group.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    student = db.relationship("Student", lazy="joined")

    __table_args__ = (
        UniqueConstraint("group_id", "student_id", name="uq_sgroup_student"),
    )


# ---------- 干部任职 ----------
class OfficerRecord(db.Model):
    """班委/课代表任职记录"""
    __tablename__ = "officer_record"

    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = {STATUS_ACTIVE: "在任", STATUS_INACTIVE: "离任"}

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    position = db.Column(db.String(50), nullable=False, comment="职务: 班长/学习委员/语文课代表等")
    start_date = db.Column(db.Date, nullable=False, comment="任职日期")
    end_date = db.Column(db.Date, nullable=True, comment="卸任日期(空=在任)")
    status = db.Column(db.String(10), default=STATUS_ACTIVE, comment="状态")
    note = db.Column(db.String(200), nullable=True, comment="说明")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    student = db.relationship("Student", lazy="joined")

    def status_label(self):
        return self.STATUS_CHOICES.get(self.status, self.status)


# ---------- 试卷题目 ----------
class ExamQuestion(db.Model):
    """试卷逐题: 题号/满分/知识点"""
    __tablename__ = "exam_question"

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False, index=True)
    subject = db.Column(db.String(20), nullable=False, comment="科目")
    question_no = db.Column(db.String(20), nullable=False, comment="题号")
    full_score = db.Column(db.Float, nullable=False, comment="满分")
    knowledge_points = db.Column(db.String(200), nullable=True, comment="知识点(分号分隔)")
    question_type = db.Column(db.String(20), nullable=True, comment="题型: 选择/填空/解答")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    exam = db.relationship("Exam", lazy="joined")

    __table_args__ = (
        UniqueConstraint("exam_id", "subject", "question_no", name="uq_exam_subj_qno"),
    )


class QuestionScore(db.Model):
    """每生每题得分"""
    __tablename__ = "question_score"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("exam_question.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    score = db.Column(db.Float, nullable=False, comment="得分")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    question = db.relationship("ExamQuestion", lazy="joined")
    student = db.relationship("Student", lazy="joined")

    __table_args__ = (
        UniqueConstraint("question_id", "student_id", name="uq_q_stu"),
    )


# ---------- 知识点 ----------
class KnowledgePoint(db.Model):
    """学科知识点字典"""
    __tablename__ = "knowledge_point"

    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(20), nullable=False, index=True, comment="科目")
    name = db.Column(db.String(100), nullable=False, comment="知识点名称")
    chapter = db.Column(db.String(100), nullable=True, comment="所属章节")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint("subject", "name", name="uq_subj_kname"),
    )


# ---------- 学生荣誉 ----------
class Honor(db.Model):
    """学生荣誉墙"""
    __tablename__ = "honor"

    LEVEL_CLASS = "class"
    LEVEL_GRADE = "grade"
    LEVEL_SCHOOL = "school"
    LEVEL_CITY = "city"
    LEVEL_CHOICES = {
        LEVEL_CLASS: "班级",
        LEVEL_GRADE: "年级",
        LEVEL_SCHOOL: "校级",
        LEVEL_CITY: "市级及以上",
    }

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False, comment="荣誉名称")
    level = db.Column(db.String(20), default=LEVEL_CLASS, comment="级别")
    awarded_at = db.Column(db.Date, nullable=False, index=True, comment="颁奖日期")
    org = db.Column(db.String(100), nullable=True, comment="颁奖单位")
    description = db.Column(db.Text, nullable=True, comment="描述")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    student = db.relationship("Student", lazy="joined")

    def level_label(self):
        return self.LEVEL_CHOICES.get(self.level, self.level)


# ---------- 心理健康观察 ----------
class PsychologyObservation(db.Model):
    """心理健康观察记录"""
    __tablename__ = "psychology_observation"

    LEVEL_NORMAL = "normal"
    LEVEL_ATTENTION = "attention"
    LEVEL_WARNING = "warning"
    LEVEL_CHOICES = {
        LEVEL_NORMAL: "正常",
        LEVEL_ATTENTION: "关注",
        LEVEL_WARNING: "预警",
    }

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    observe_date = db.Column(db.Date, nullable=False, index=True, comment="观察日期")
    mood = db.Column(db.String(50), nullable=True, comment="情绪状态")
    behavior = db.Column(db.Text, nullable=True, comment="行为描述")
    concern_level = db.Column(db.String(20), default=LEVEL_NORMAL, comment="关注级别")
    followup_date = db.Column(db.Date, nullable=True, comment="下次回访日期")
    note = db.Column(db.Text, nullable=True, comment="备注")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    student = db.relationship("Student", lazy="joined")

    def level_label(self):
        return self.LEVEL_CHOICES.get(self.concern_level, self.concern_level)


# ---------- 家访记录 ----------
class HomeVisit(db.Model):
    """家访记录(独立于家校联系)"""
    __tablename__ = "home_visit"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    visit_date = db.Column(db.Date, nullable=False, index=True, comment="家访日期")
    accompany = db.Column(db.String(100), nullable=True, comment="陪同人")
    home_situation = db.Column(db.Text, nullable=True, comment="家庭情况")
    parent_attitude = db.Column(db.Text, nullable=True, comment="家长态度")
    content = db.Column(db.Text, nullable=True, comment="家访内容")
    followup = db.Column(db.Text, nullable=True, comment="后续跟进")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    student = db.relationship("Student", lazy="joined")


# ---------- 班会/活动 ----------
class ClassActivity(db.Model):
    """班会/活动记录"""
    __tablename__ = "class_activity"

    TYPE_MEETING = "meeting"
    TYPE_ACTIVITY = "activity"
    TYPE_CHOICES = {TYPE_MEETING: "班会", TYPE_ACTIVITY: "活动"}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False, comment="主题")
    activity_type = db.Column(db.String(20), default=TYPE_MEETING, comment="类型")
    held_at = db.Column(db.Date, nullable=False, index=True, comment="举办日期")
    term = db.Column(db.String(20), nullable=True, comment="学期")
    participants = db.Column(db.String(200), nullable=True, comment="参与人(简化为文本)")
    agenda = db.Column(db.Text, nullable=True, comment="流程/议程")
    summary = db.Column(db.Text, nullable=True, comment="总结")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def type_label(self):
        return self.TYPE_CHOICES.get(self.activity_type, self.activity_type)


# ---------- 值日检查清单 ----------
class DutyChecklistTemplate(db.Model):
    """值日检查项模板"""
    __tablename__ = "duty_checklist_template"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, comment="清单名称")
    items_json = db.Column(db.Text, nullable=False, comment="检查项JSON数组")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)


class DutyCheckRecord(db.Model):
    """值日检查记录"""
    __tablename__ = "duty_check_record"

    id = db.Column(db.Integer, primary_key=True)
    check_date = db.Column(db.Date, nullable=False, index=True, comment="检查日期")
    group_id = db.Column(db.Integer, db.ForeignKey("duty_group.id"), nullable=True, comment="值日组")
    template_id = db.Column(db.Integer, db.ForeignKey("duty_checklist_template.id"),
                            nullable=True, comment="使用的模板")
    scores_json = db.Column(db.Text, nullable=True, comment="各项评分JSON")
    total_score = db.Column(db.Float, default=0, comment="总分")
    note = db.Column(db.Text, nullable=True, comment="备注")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    group = db.relationship("DutyGroup", lazy="joined")
    template = db.relationship("DutyChecklistTemplate", lazy="joined")


# ---------- 班费预算 ----------
class Budget(db.Model):
    """班费预算(按学期/分类)"""
    __tablename__ = "budget"

    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(20), nullable=False, index=True, comment="学期")
    category = db.Column(db.String(30), nullable=False, comment="分类")
    amount = db.Column(db.Float, nullable=False, comment="预算金额")
    note = db.Column(db.String(200), nullable=True, comment="说明")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint("term", "category", name="uq_term_cat"),
    )


# ---------- 年级对标 ----------
class GradeBenchmark(db.Model):
    """年级均分/排名对标数据"""
    __tablename__ = "grade_benchmark"

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False, index=True)
    subject = db.Column(db.String(20), nullable=False, comment="科目; total表示年级总均分")
    grade_avg = db.Column(db.Float, nullable=True, comment="年级均分")
    grade_max = db.Column(db.Float, nullable=True, comment="年级最高分")
    grade_stu_count = db.Column(db.Integer, nullable=True, comment="年级人数")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    exam = db.relationship("Exam", lazy="joined")

    __table_args__ = (
        UniqueConstraint("exam_id", "subject", name="uq_exam_subj_bm"),
    )


# ---------- 家长会 ----------
class ParentMeeting(db.Model):
    """家长会"""
    __tablename__ = "parent_meeting"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False, comment="主题")
    held_at = db.Column(db.Date, nullable=False, index=True, comment="召开日期")
    term = db.Column(db.String(20), nullable=True, comment="学期")
    agenda = db.Column(db.Text, nullable=True, comment="议程")
    notice = db.Column(db.Text, nullable=True, comment="通知正文")
    summary = db.Column(db.Text, nullable=True, comment="会议总结")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    attendees = db.relationship("ParentMeetingAttendee", backref="meeting",
                                lazy="dynamic", cascade="all, delete-orphan")


class ParentMeetingAttendee(db.Model):
    """家长会签到"""
    __tablename__ = "parent_meeting_attendee"

    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("parent_meeting.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    parent_name = db.Column(db.String(50), nullable=True, comment="家长姓名")
    attended = db.Column(db.Boolean, default=False, comment="是否到会")
    note = db.Column(db.String(100), nullable=True, comment="备注")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    student = db.relationship("Student", lazy="joined")
