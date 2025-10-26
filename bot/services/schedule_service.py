# bot/services/schedule_service.py

from typing import List, Dict, Any
from datetime import datetime

def format_schedule(schedule_data: List[Dict[str, Any]], lang: str) -> str:
    """Formats a list of lessons into a readable daily schedule."""
    if not schedule_data:
        # We will use the translator here later
        return "На этот день занятий нет."

    # Group lessons by date
    days = {}
    for lesson in schedule_data:
        date_str = lesson['date']
        if date_str not in days:
            days[date_str] = []
        days[date_str].append(lesson)

    # Format each day's schedule
    formatted_days = []
    for date_str, lessons in sorted(days.items()):
        date_obj = datetime.strptime(date_str, "%Y.%m.%d")
        # Example format, we'll use i18n later
        day_header = f"🗓 *{date_obj.strftime('%A, %d %B %Y')}*"
        
        formatted_lessons = []
        for lesson in sorted(lessons, key=lambda x: x['beginLesson']):
            formatted_lessons.append(
                f"    `{lesson['beginLesson']} - {lesson['endLesson']}`\n"
                f"    *Предмет:* {lesson['discipline']}\n"
                f"    *Тип:* {lesson['kindOfWork']}\n"
                f"    *Аудитория:* {lesson['auditorium']} ({lesson['building']})\n"
                f"    *Преподаватель:* {lesson['lecturer']}"
            )
        
        formatted_days.append(f"{day_header}\n" + "\n\n".join(formatted_lessons))

    return "\n\n---\n\n".join(formatted_days)