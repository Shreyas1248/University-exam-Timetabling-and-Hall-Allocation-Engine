from datetime import datetime, timedelta


def exam_start_time(data, exam_date, session):
    slot = next(
        row for row in data["exam_window"]
        if row["date"] == exam_date and row["session"] == session
    )
    return slot["start_time"]


def exam_end_time(data, exam_date, session, duration, extra_minutes=0):
    start = datetime.strptime(
        exam_start_time(data, exam_date, session), "%H:%M"
    )
    end = start + timedelta(hours=int(duration), minutes=int(extra_minutes))
    return end.strftime("%H:%M")
