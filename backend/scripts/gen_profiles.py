"""生成 M5 质检扩展画像 (2026-08-03) — 差异化背景, 补足 ≥10 组测试用例。

一次性数据准备脚本: 读 profile_template.json 结构, 生成 7 个新画像 JSON 到
data/user_profiles/。赛题「实用价值 30 分」要求 ≥3 组不同背景学习者画像测试用例,
扩至 10 组覆盖: 零基础/跨专业/在职转岗/自学补漏/方向专攻 (数据分析/Web)/高中生/跨语言。
"""

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台 GBK 下打印中文/emoji

OUT = Path(__file__).resolve().parent.parent.parent / "data" / "user_profiles"


def _base(profile_id, name, type_, desc, theory, practical, style, target,
          pace, hours, major, edu, exp_months, py_months, langs, weaknesses,
          test_correct, style_quiz):
    """按 template 骨架构造画像 (raw_assessment_data 用简洁但合法的形状)。"""
    return {
        "$schema": "profile_schema.json",
        "profile_id": profile_id,
        "name": name,
        "created_at": "2026-08-03T10:00:00Z",
        "type": type_,
        "description": desc,
        "demographics": {
            "age_range": "18-30",
            "education": edu,
            "major": major,
            "programming_experience_months": exp_months,
            "python_experience_months": py_months,
            "previously_learned_languages": langs,
        },
        "theory_level": theory,
        "practical_level": practical,
        "learning_style": style,
        "target_direction": target,
        "preferred_pace": pace,
        "time_per_week": hours,
        "known_topics": [],
        "weak_topics": [],
        "weakness_areas": weaknesses,
        "raw_assessment_data": {
            "theory_test": {"total_questions": 10, "correct": test_correct, "answers": []},
            "practical_test": {"total_exercises": 5, "completed": 0, "average_score": 0},
            "learning_style_quiz": style_quiz,
        },
        "learning_history": [],
        "recommended_path": {"current_node": "PY-001", "next_nodes": [], "estimated_weeks": 4},
    }


def main():
    profiles = [
        _base(
            "UP-NTC-001", "文科生小林", "零基础转行学习者",
            "汉语言文学大三学生, 想转行互联网, 从未写过代码。对编程充满好奇但完全零基础, "
            "需要从变量/数据类型一步步讲起, 例子要贴近生活。",
            1, 1, "visual",
            "Python 零基础入门到能独立写小脚本",
            "slow", 6, "汉语言文学", "本科在读（大三）", 0, 0, [],
            ["从未接触编程, 对变量/数据类型等基本概念无任何认知", "逻辑思维偏文科, 条件判断和循环需要大量类比讲解"],
            2, {"visual": 4, "auditory": 2, "read_write": 2, "kinesthetic": 1},
        ),
        _base(
            "UP-CSW-001", "财务张姐", "在职转岗学习者",
            "30 岁财务主管, 白天上班晚上学习, 目标转岗数据分析。会用 Excel 但不了解编程, "
            "希望学 Python 提升数据处理效率, 学习时间碎片化。",
            2, 1, "read_write",
            "Python 数据分析基础（pandas 入门）",
            "normal", 8, "会计学", "本科", 0, 0, [],
            ["编程基础薄弱, 只熟悉 Excel 函数概念", "对自动化批处理没有概念, 需要讲清楚脚本是什么"],
            4, {"visual": 2, "auditory": 1, "read_write": 4, "kinesthetic": 2},
        ),
        _base(
            "UP-STH-001", "自学程序员小周", "自学补漏学习者",
            "靠网课自学 Python 一年, 能跑通示例代码但不懂原理, 基础有漏洞。会写简单脚本, "
            "但面向对象/异常处理一知半解, 想系统补全基础。",
            2, 2, "read_write",
            "Python 基础补全 + 面向对象",
            "fast", 10, "机械工程", "本科（毕业1年）", 14, 12, [],
            ["自学无系统, 基础语法有漏: 列表/字典混用、作用域不清", "面向对象只见过类名, 不理解封装/继承的意义"],
            6, {"visual": 2, "auditory": 1, "read_write": 3, "kinesthetic": 3},
        ),
        _base(
            "UP-DAT-001", "数据方向小李", "方向专攻学习者",
            "统计专业研一, 会用 R 但想转 Python 生态做数据分析。数学功底好, 逻辑强, "
            "希望快速掌握 numpy/pandas 并完成真实数据分析项目。",
            3, 2, "visual",
            "Python 数据分析（numpy/pandas）",
            "fast", 12, "统计学", "硕士在读", 4, 3, ["R"],
            ["只会调用示例, 不理解 Python 数据结构的特性", "对 DataFrame 索引/切片等核心操作不熟练"],
            7, {"visual": 3, "auditory": 1, "read_write": 3, "kinesthetic": 2},
        ),
        _base(
            "UP-WEB-001", "全栈目标小陈", "方向专攻学习者",
            "前端开发一年经验, JS 熟练, 想补后端变全栈。理解编程概念, 目标用 Flask 做项目, "
            "希望尽快掌握 Python 语法差异与 Web 开发常用库。",
            3, 3, "visual",
            "Python Web 开发（Flask 项目）",
            "fast", 12, "软件工程", "本科（毕业2年）", 24, 2, ["JavaScript", "HTML/CSS"],
            ["Python 语法细节不熟 (缩进/动态类型/列表推导)", "不熟悉 Python 生态与包管理"],
            8, {"visual": 3, "auditory": 1, "read_write": 2, "kinesthetic": 3},
        ),
        _base(
            "UP-HSC-001", "高一学生小凡", "高中零基础学习者",
            "高一学生, 学校开设信息课, 对编程感兴趣, 想为信息学竞赛打基础。数学不错, "
            "但从未接触代码, 需要趣味化入门。",
            1, 1, "kinesthetic",
            "Python 入门（信息学竞赛基础）",
            "normal", 5, "高中在读", "高中", 0, 0, [],
            ["编程完全零基础, 需要解释什么是程序", "需要趣味案例保持兴趣"],
            3, {"visual": 2, "auditory": 1, "read_write": 1, "kinesthetic": 4},
        ),
        _base(
            "UP-JTP-001", "Java转Python老张", "跨语言学习者",
            "Java 后端 5 年经验, 熟悉 OOP/设计模式, 因新项目要转 Python。概念都已掌握, "
            "只需要快速对齐 Python 语法与生态差异, 不喜欢冗余讲解。",
            4, 3, "read_write",
            "Python 进阶（面向对象/常用库）",
            "fast", 14, "计算机科学与技术", "本科（毕业5年）", 60, 3, ["Java", "C++"],
            ["Python 动态特性 (鸭子类型/装饰器) 需要建立心智模型", "对 Python 的库生态与工程化不熟"],
            9, {"visual": 1, "auditory": 1, "read_write": 5, "kinesthetic": 2},
        ),
    ]

    for p in profiles:
        path = OUT / f"profile_{p['profile_id'].split('-')[1].lower()}.json"
        # 用语义名做文件名 (与现有 beginner/intermediate/advanced 一致)
        name_map = {
            "NTC": "non_tech", "CSW": "career_switch", "STH": "self_taught",
            "DAT": "data_analyst", "WEB": "web_dev", "HSC": "high_school", "JTP": "java_to_python",
        }
        fname = name_map[p["profile_id"].split("-")[1]]
        path = OUT / f"profile_{fname}.json"
        path.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"✔ 生成 {path.name} (理论{p['theory_level']}级/实践{p['practical_level']}级)")


if __name__ == "__main__":
    main()
