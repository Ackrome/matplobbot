# bot/services/schedule_service.py

from typing import List, Dict, Any
from datetime import datetime, date
from collections import defaultdict

names_shorter = defaultdict(lambda: 'Неизвестно')
to_add = {
    'Практические (семинарские) занятия': 'Семинар',
    'Лекции': 'Лекция',
    'Консультации текущие': 'Консультация',
    'Повторная промежуточная аттестация (экзамен)':'Пересдача'
    }
names_shorter.update(to_add)

    

def format_schedule(schedule_data: List[Dict[str, Any]], lang: str, entity_name: str, start_date: date) -> str:
    """Formats a list of lessons into a readable daily schedule."""
    if not schedule_data:
        return f"🗓 *Расписание для \"{entity_name}\"*\n\nНа запрошенный день занятий нет."

    # Group lessons by date
    days = {}
    for lesson in schedule_data:
        date_str = lesson['date']
        if date_str not in days:
            days[date_str] = []
        days[date_str].append(lesson)

    # Find the first day with lessons that is on or after the start_date
    for date_str, lessons in sorted(days.items()):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        if date_obj >= start_date:
            # Found the first relevant day, format it and return immediately.
            day_header = f"🗓 *Расписание на {date_obj.strftime('%d.%m.%Y')} для \"{entity_name}\"*"
            
            formatted_lessons = []
            for lesson in sorted(lessons, key=lambda x: x['beginLesson']):
                formatted_lessons.append(
                    f"`{lesson['beginLesson']} - {lesson['endLesson']} | {lesson['auditorium']}`\n"
                    f"{lesson['discipline']} | {names_shorter[lesson['kindOfWork']]}\n"
                    # f"{lesson['kindOfWork']}\n"
                    # f"{lesson['auditorium']} ({lesson['building']})\n"
                    f"{lesson['lecturer_title'].replace('_',' ')}\n"
                    f"{lesson['lecturerEmail']}\n"
                )
            
            return f"{day_header}\n" + "\n\n".join(formatted_lessons)

    # If no lessons were found in the entire fetched range
    return f"🗓 *Расписание для \"{entity_name}\"*\n\nВ ближайшую неделю занятий не найдено."