"""Realistic Zhengzhou University (ZZU) demo data for preview mode."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .session import UserSession
from .zzu_client import utc_plus_8


def get_demo_campuses() -> list[dict[str, Any]]:
    return [
        {
            "campus_id": 2,
            "campus_name": "主校区",
            "buildings": [
                {"building_id": 5, "building_name": "北1号楼"},
                {"building_id": 6, "building_name": "北2号楼"},
                {"building_id": 7, "building_name": "北3号楼"},
                {"building_id": 8, "building_name": "北4号楼"},
                {"building_id": 9, "building_name": "南1号楼"},
                {"building_id": 10, "building_name": "南2号楼"},
                {"building_id": 11, "building_name": "中核心教学楼"},
            ],
        },
        {
            "campus_id": 1,
            "campus_name": "南校区",
            "buildings": [
                {"building_id": 21, "building_name": "南区1号楼"},
                {"building_id": 22, "building_name": "南区2号楼"},
            ],
        },
        {
            "campus_id": 3,
            "campus_name": "北校区",
            "buildings": [
                {"building_id": 31, "building_name": "北区综合楼"},
                {"building_id": 32, "building_name": "北区教学楼"},
            ],
        },
        {
            "campus_id": 4,
            "campus_name": "东校区",
            "buildings": [
                {"building_id": 41, "building_name": "东区医学楼"},
            ],
        },
    ]


def get_demo_rooms(building_id: str, date_str: str) -> list[dict[str, Any]]:
    prefix_map = {
        "5": "北1",
        "6": "北2",
        "7": "北3",
        "8": "北4",
        "9": "南1",
        "10": "南2",
        "11": "中核",
    }
    prefix = prefix_map.get(str(building_id), f"楼{building_id}")
    patterns = [
        "0011001100",
        "1100000011",
        "0000110000",
        "1111000000",
        "0000000000",
        "0011110000",
        "1100110000",
        "0000001111",
    ]
    rooms = []
    idx = 0
    for floor in range(1, 6):
        for num in range(1, 5):
            room_code = f"{prefix}-{floor}0{num}"
            rooms.append(
                {
                    "room_id": int(f"{building_id}{floor}0{num}"),
                    "room_name": room_code,
                    "floor": floor,
                    "seats": 60 if num <= 2 else 120,
                    "room_type": "多媒体教室" if num <= 3 else "阶梯教室",
                    "occupy_units": patterns[idx % len(patterns)],
                }
            )
            idx += 1
    return [{"date": date_str, "building_id": building_id, "rooms": rooms}]


def get_demo_semesters() -> list[dict[str, Any]]:
    now = utc_plus_8()
    year = now.year
    return [
        {
            "id": 20261,
            "name": f"{year}-{year + 1}学年 第一学期",
            "start_date": f"{year}-09-01",
            "end_date": f"{year + 1}-01-20",
            "is_current": True,
        },
        {
            "id": 20252,
            "name": f"{year - 1}-{year}学年 第二学期",
            "start_date": f"{year}-02-24",
            "end_date": f"{year}-07-05",
            "is_current": False,
        },
        {
            "id": 20251,
            "name": f"{year - 1}-{year}学年 第一学期",
            "start_date": f"{year - 1}-09-02",
            "end_date": f"{year}-01-18",
            "is_current": False,
        },
    ]


def get_demo_timetable() -> list[dict[str, Any]]:
    return [
        {"index": 1, "name": "第1节", "start_time": "08:00", "end_time": "08:45"},
        {"index": 2, "name": "第2节", "start_time": "08:55", "end_time": "09:40"},
        {"index": 3, "name": "第3节", "start_time": "10:10", "end_time": "10:55"},
        {"index": 4, "name": "第4节", "start_time": "11:05", "end_time": "11:50"},
        {"index": 5, "name": "第5节", "start_time": "14:00", "end_time": "14:45"},
        {"index": 6, "name": "第6节", "start_time": "14:55", "end_time": "15:40"},
        {"index": 7, "name": "第7节", "start_time": "16:10", "end_time": "16:55"},
        {"index": 8, "name": "第8节", "start_time": "17:05", "end_time": "17:50"},
        {"index": 9, "name": "第9节", "start_time": "19:00", "end_time": "19:45"},
        {"index": 10, "name": "第10节", "start_time": "19:55", "end_time": "20:40"},
    ]


def get_demo_course_table(start_date: str) -> list[dict[str, Any]]:
    return [
        {
            "course_name": "数据结构与算法",
            "teacher_name": "李明",
            "room_name": "北1-402",
            "weekday": 1,
            "start_unit": 1,
            "end_unit": 2,
            "weeks": "1-16周",
            "date": start_date,
        },
        {
            "course_name": "大学物理(下)",
            "teacher_name": "王芳",
            "room_name": "南2-201",
            "weekday": 1,
            "start_unit": 5,
            "end_unit": 6,
            "weeks": "1-16周",
        },
        {
            "course_name": "操作系统原理",
            "teacher_name": "张伟",
            "room_name": "北3-305",
            "weekday": 2,
            "start_unit": 3,
            "end_unit": 4,
            "weeks": "1-16周",
        },
        {
            "course_name": "计算机网络",
            "teacher_name": "赵敏",
            "room_name": "北2-204",
            "weekday": 3,
            "start_unit": 1,
            "end_unit": 2,
            "weeks": "1-16周",
        },
        {
            "course_name": "概率论与数理统计",
            "teacher_name": "陈静",
            "room_name": "中核-108",
            "weekday": 3,
            "start_unit": 7,
            "end_unit": 8,
            "weeks": "1-14周",
        },
        {
            "course_name": "数据结构与算法",
            "teacher_name": "李明",
            "room_name": "北1-402",
            "weekday": 4,
            "start_unit": 3,
            "end_unit": 4,
            "weeks": "1-16周",
        },
        {
            "course_name": "人工智能导论",
            "teacher_name": "刘洋",
            "room_name": "北4-501",
            "weekday": 4,
            "start_unit": 9,
            "end_unit": 10,
            "weeks": "2-15周",
        },
        {
            "course_name": "操作系统实验",
            "teacher_name": "张伟",
            "room_name": "计算中心302",
            "weekday": 5,
            "start_unit": 5,
            "end_unit": 6,
            "weeks": "4-15周",
        },
    ]


def get_demo_grades() -> list[dict[str, Any]]:
    return [
        {
            "semester": "2025-2026学年 第二学期",
            "course_name": "高等数学(下)",
            "course_code": "MATH102",
            "credits": 5.0,
            "score": "92",
            "gp": 4.0,
            "course_type": "必修",
        },
        {
            "semester": "2025-2026学年 第二学期",
            "course_name": "面向对象程序设计(C++)",
            "course_code": "CS201",
            "credits": 3.5,
            "score": "95",
            "gp": 4.0,
            "course_type": "必修",
        },
        {
            "semester": "2025-2026学年 第二学期",
            "course_name": "大学英语(二)",
            "course_code": "ENG102",
            "credits": 3.0,
            "score": "87",
            "gp": 3.7,
            "course_type": "必修",
        },
        {
            "semester": "2025-2026学年 第二学期",
            "course_name": "数字逻辑电路",
            "course_code": "EE204",
            "credits": 3.0,
            "score": "84",
            "gp": 3.3,
            "course_type": "必修",
        },
        {
            "semester": "2025-2026学年 第一学期",
            "course_name": "高等数学(上)",
            "course_code": "MATH101",
            "credits": 5.0,
            "score": "89",
            "gp": 3.7,
            "course_type": "必修",
        },
        {
            "semester": "2025-2026学年 第一学期",
            "course_name": "线性代数",
            "course_code": "MATH105",
            "credits": 2.5,
            "score": "91",
            "gp": 4.0,
            "course_type": "必修",
        },
        {
            "semester": "2025-2026学年 第一学期",
            "course_name": "中国近现代史纲要",
            "course_code": "POL101",
            "credits": 3.0,
            "score": "90",
            "gp": 4.0,
            "course_type": "公共必修",
        },
    ]


def get_demo_exams() -> list[dict[str, Any]]:
    today = utc_plus_8().date()
    return [
        {
            "course_name": "数据结构与算法",
            "exam_date": (today + timedelta(days=9)).isoformat(),
            "exam_time": "09:00-11:00",
            "room_name": "北1-402",
            "seat_no": "18",
            "exam_type": "期末闭卷",
        },
        {
            "course_name": "操作系统原理",
            "exam_date": (today + timedelta(days=12)).isoformat(),
            "exam_time": "14:30-16:30",
            "room_name": "北3-201",
            "seat_no": "32",
            "exam_type": "期末闭卷",
        },
        {
            "course_name": "计算机网络",
            "exam_date": (today + timedelta(days=16)).isoformat(),
            "exam_time": "09:00-11:00",
            "room_name": "南1-305",
            "seat_no": "07",
            "exam_type": "期末闭卷",
        },
    ]


def get_demo_ecard_details(sess: UserSession) -> dict[str, Any]:
    return {
        "utilityAccount": sess.account,
        "utilityUsername": "演示同学",
        "card_balance": f"{sess.demo_card_balance:.2f}",
        "electric_balance": f"{sess.demo_electric_balance:.2f}",
        "electric_unit": "度",
        "location": {
            "area": "柳园",
            "building": "12号楼",
            "level": "4层",
            "room": "412",
            "utilityType": "electric",
        },
        "templateList": [
            {"name": "校园卡余额", "value": f"{sess.demo_card_balance:.2f}", "unit": "元"},
            {"name": "房间名称", "value": "柳园12号楼412", "unit": ""},
            {"name": "电表状态", "value": "正常供电", "unit": ""},
            {"name": "剩余电量", "value": f"{sess.demo_electric_balance:.2f}", "unit": "度"},
        ],
        "transfers": sess.demo_transfers,
    }
