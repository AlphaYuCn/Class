"""Jinja 全局过滤器"""
from markupsafe import Markup


def register_filters(app):
    @app.template_filter("gender_label")
    def gender_label(v):
        if not v:
            return ""
        if v.upper() == "M":
            return "男"
        if v.upper() == "F":
            return "女"
        return v

    @app.template_filter("element_label")
    def element_label(v):
        m = {"火": "火象", "风": "风象", "土": "土象", "水": "水象"}
        return m.get(v, "")

    @app.template_filter("date_cn")
    def date_cn(d):
        if not d:
            return ""
        try:
            return f"{d.year}年{d.month:02d}月{d.day:02d}日"
        except Exception:
            return str(d)

    @app.template_filter("datetime_cn")
    def datetime_cn(d):
        if not d:
            return ""
        try:
            return f"{d.year}-{d.month:02d}-{d.day:02d} {d.hour:02d}:{d.minute:02d}"
        except Exception:
            return str(d)

    @app.template_filter("score1")
    def score1(v):
        """成绩格式化: 保留1位小数, None/空/未定义返回空串"""
        if v is None or v == "":
            return ""
        try:
            return f"{float(v):.1f}"
        except Exception:
            return ""

    @app.template_filter("delta_badge")
    def delta_badge(d):
        """Δ 数字 -> 带颜色的徽章 HTML"""
        if d is None:
            return Markup('<span class="badge text-muted">—</span>')
        if isinstance(d, (int, float)):
            if d > 0:
                return Markup(f'<span class="badge bg-success">+{d}</span>')
            elif d < 0:
                return Markup(f'<span class="badge bg-danger">{d}</span>')
            return Markup('<span class="badge bg-secondary">0</span>')
        return str(d)

    @app.template_filter("rank_delta_badge")
    def rank_delta_badge(d):
        """排名 Δ: 进步=正数=绿色"""
        if d is None:
            return Markup('<span class="badge text-muted">—</span>')
        if d > 0:
            return Markup(f'<span class="badge bg-success">↑{d}名</span>')
        elif d < 0:
            return Markup(f'<span class="badge bg-danger">↓{-d}名</span>')
        return Markup('<span class="badge bg-secondary">持平</span>')

    @app.template_filter("subject_label")
    def subject_label(k):
        from app.utils.suggestion import SUBJECT_LABEL
        return SUBJECT_LABEL.get(k, k)

    @app.template_filter("nl2br")
    def nl2br(text):
        """把换行转成 <br>"""
        if not text:
            return ""
        from markupsafe import Markup
        return Markup(str(text).replace("\n", "<br>\n").replace("\r\n", "<br>\n"))
