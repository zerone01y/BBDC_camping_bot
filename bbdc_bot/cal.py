import pytz, dateutil.tz  # timezone libraries
from datetime import timedelta, datetime, timezone
from zoneinfo import ZoneInfo
from icalendar import Calendar, Event, Alarm, vDatetime
import json


def schedule_to_ics(schedule, tz_info="Asia/Singapore"):
    origin_tz = ZoneInfo("Asia/Singapore")

    cal = Calendar()
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "BBDC Sessions")

    alarm_3d_before = Alarm()
    alarm_3d_before.add("action", "DISPLAY")
    alarm_3d_before.add("trigger", timedelta(days=-3))
    alarm_3d_before.add("description", "Reminder: Event in 3 days")

    for i in schedule:
        event = Event()
        event["uid"] = i["bookingId"]
        event.add("summary", f"BBDC {i['dataType']} Session {i['sessionNo']}")
        event.add(
            "dtstart",
            datetime.strptime(
                i["slotRefDate"][:11] + i["startTime"], "%Y-%m-%d %H:%M"
            ).replace(tzinfo=origin_tz),
        )
        event.add(
            "dtend",
            datetime.strptime(
                i["slotRefDate"][:11] + i["endTime"], "%Y-%m-%d %H:%M"
            ).replace(tzinfo=origin_tz),
        )
        event.add(
            "description",
            ", ".join([i["slotRefDesc"], i["stageSubNo"]]) + f" @{i['venueName']}",
        )
        # event.add_component(alarm_1h_before)
        event.add_component(alarm_3d_before)
        event.add("LOCATION", "Bukit Batok Driving Centre Ltd")
        cal.add_component(event)
    return cal.to_ical()


if __name__ == "__main__":
    # WARNING: Hardcoded chat_id for testing - replace with command line argument
    # Example: chat_id = sys.argv[1] if len(sys.argv) > 1 else None
    import sys

    if len(sys.argv) > 1:
        chat_id = sys.argv[1]
    else:
        print("Usage: python cal.py <chat_id>")
        print(
            "WARNING: This is a test script. Do not use hardcoded chat_id in production."
        )
        sys.exit(1)
    with open(f"user/{chat_id}/schedule.json", "r") as f:
        schedule = json.load(f)
    cal = schedule_to_ics(schedule)
    with open(f"user/{chat_id}/bbdc.ics", "wb") as f:
        f.write(cal)
