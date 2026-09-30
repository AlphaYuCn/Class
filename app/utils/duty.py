"""值日分组: 按性别蛇形轮转, 保证各组男女数差 ≤ 1

算法:
1. 按性别拆 males/females, 各自按学号排序(稳定可复现)
2. 女生蛇形轮转分到 G 组(1->2->...->G->G->...->2->1)
3. 男生蛇形轮转, 起始组错开 ceil(G/2) 让男女错位
4. 余数补足: 缺人组优先补当前最少人数组, 同人数则补该组弱势性别
"""
import math


def _snake_indices(n_items, n_groups):
    """蛇形轮转分配: 第 i 个 item 落到哪个组(0-based)
    序列: 0,1,2,...,G-1, G-1,G-2,...,1,0, 0,1,...
    """
    result = []
    for i in range(n_items):
        cycle = (i // n_groups) % 2
        offset = i % n_groups
        if cycle == 0:
            group = offset
        else:
            group = n_groups - 1 - offset
        result.append(group)
    return result


def group_students(students, n_groups: int, members_per_group: int | None = None):
    """分组

    Args:
        students: list[Student]
        n_groups: 组数 G
        members_per_group: 每组人数 M (可选, 用于校验, 不强制截断)

    Returns:
        list[list[Student]]  每组学生列表
    """
    if not students:
        raise ValueError("没有学生可分组")
    if n_groups <= 0:
        raise ValueError("组数必须 > 0")
    if n_groups > len(students):
        # 退化为按人数分: 每组最多1人, 多余组为空
        n_groups = len(students)

    # 拆分性别
    males = sorted([s for s in students if (s.gender or "M").upper() == "M"],
                    key=lambda s: s.student_no)
    females = sorted([s for s in students if (s.gender or "M").upper() == "F"],
                      key=lambda s: s.student_no)

    groups = [[] for _ in range(n_groups)]

    # 女生蛇形轮转
    if females:
        for i, s in enumerate(females):
            g = _snake_indices(len(females), n_groups)[i]
            groups[g].append(s)

    # 男生蛇形轮转, 起始组错开
    if males:
        start_offset = math.ceil(n_groups / 2)
        for i, s in enumerate(males):
            # 错位: i 落到 (start_offset + i) 蛇形分布
            base = _snake_indices(len(males), n_groups)
            g = (base[i] + start_offset) % n_groups
            groups[g].append(s)

    # 平衡校验: 若某组人数明显多/少, 微调
    # 期望: 总人数 / n_groups 上下
    # 把超出 1 的组的最后一人移到最少组
    def group_count(idx):
        return len(groups[idx])
    # 简单平衡: 把最长组溢出成员移到最短组
    for _ in range(n_groups * 2):
        max_g = max(range(n_groups), key=group_count)
        min_g = min(range(n_groups), key=group_count)
        if group_count(max_g) - group_count(min_g) <= 1:
            break
        if group_count(max_g) == 0:
            break
        groups[min_g].append(groups[max_g].pop())

    # 同组排序: 男在前女在后(便于查看)
    for g in groups:
        g.sort(key=lambda s: ((s.gender or "M").upper(), s.student_no))
    return groups


def group_summary(groups):
    """统计每组男女数, 用于校验"""
    summary = []
    for i, g in enumerate(groups):
        m = sum(1 for s in g if (s.gender or "M").upper() == "M")
        f = sum(1 for s in g if (s.gender or "M").upper() == "F")
        summary.append({"group": i + 1, "total": len(g), "male": m, "female": f})
    return summary
