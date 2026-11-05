"""Native macOS Calendar (EventKit) access — create/update/delete events for the Alma sync."""
import calendar as _calendar
import time
from datetime import datetime

from EventKit import (
    EKEventStore,
    EKEntityTypeEvent,
    EKSourceTypeLocal,
    EKSourceTypeCalDAV,
    EKSpanThisEvent,
)
from Foundation import NSDate

CALENDAR_NAME = "Alma Assignments"


def _wait_for_access(store):
    """Request calendar access and block until the user responds (or it's already granted)."""
    result = {"done": False, "granted": False}

    def callback(granted, error):
        result["granted"] = granted
        result["done"] = True

    if hasattr(store, "requestFullAccessToEventsWithCompletion_"):
        store.requestFullAccessToEventsWithCompletion_(callback)
    else:
        store.requestAccessToEntityType_completion_(EKEntityTypeEvent, callback)

    from Foundation import NSRunLoop, NSDate as _NSDate
    deadline = time.time() + 60
    while not result["done"] and time.time() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(_NSDate.dateWithTimeIntervalSinceNow_(0.1))
    return result["granted"]


def get_store():
    store = EKEventStore.alloc().init()
    granted = _wait_for_access(store)
    if not granted:
        raise RuntimeError(
            "Calendar access was not granted. Open System Settings > Privacy & Security > "
            "Calendars and allow access for the app running this script (e.g. Terminal or python3), then retry."
        )
    return store


def get_or_create_calendar(store, name=CALENDAR_NAME):
    for cal in store.calendarsForEntityType_(EKEntityTypeEvent):
        if str(cal.title()) == name:
            return cal

    source = None
    for s in store.sources():
        if s.sourceType() == EKSourceTypeCalDAV and "icloud" in str(s.title()).lower():
            source = s
            break
    if source is None:
        for s in store.sources():
            if s.sourceType() == EKSourceTypeLocal:
                source = s
                break
    if source is None and store.sources():
        source = store.sources()[0]
    if source is None:
        raise RuntimeError("No usable Calendar source found to create the 'Alma To-Do' calendar in.")

    from EventKit import EKCalendar
    cal = EKCalendar.calendarForEntityType_eventStore_(EKEntityTypeEvent, store)
    cal.setTitle_(name)
    cal.setSource_(source)
    ok, err = store.saveCalendar_commit_error_(cal, True, None)
    if not ok:
        raise RuntimeError(f"Failed to create calendar: {err}")
    return cal


def _allday_nsdate(dt: datetime) -> NSDate:
    # EventKit computes all-day spans using UTC day boundaries, so treat
    # the naive datetime as UTC midnight rather than local midnight —
    # using local time here caused every event to span two days.
    ts = _calendar.timegm(dt.timetuple())
    return NSDate.dateWithTimeIntervalSince1970_(ts)


def _timed_nsdate(dt: datetime) -> NSDate:
    # Regular (non-all-day) events just need the correct absolute instant,
    # so this uses the system's local timezone via datetime.timestamp().
    return NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())


def find_event(store, event_identifier):
    if not event_identifier:
        return None
    ev = store.calendarItemWithIdentifier_(event_identifier)
    return ev


def upsert_event(store, calendar, event_identifier, title, notes, due_date, url=None, period_time=None):
    """Create or update an event on due_date. Returns the event's calendarItemIdentifier.

    period_time: optional ("HH:MM", "HH:MM") — when given, creates a timed
    event at that class period's actual meeting time instead of an all-day block.
    """
    ev = find_event(store, event_identifier)
    if ev is None:
        from EventKit import EKEvent
        ev = EKEvent.eventWithEventStore_(store)
        ev.setCalendar_(calendar)

    ev.setTitle_(title)
    ev.setNotes_(notes)

    if period_time:
        start_h, start_m = (int(x) for x in period_time[0].split(":"))
        end_h, end_m = (int(x) for x in period_time[1].split(":"))
        start = datetime(due_date.year, due_date.month, due_date.day, start_h, start_m)
        end = datetime(due_date.year, due_date.month, due_date.day, end_h, end_m)
        ev.setAllDay_(False)
        ev.setStartDate_(_timed_nsdate(start))
        ev.setEndDate_(_timed_nsdate(end))
    else:
        # EKEvent all-day events use inclusive start/end: the SAME date on
        # both means a single-day event. (end = start + 1 day, the
        # iCalendar-style exclusive convention, makes EventKit cover two
        # days instead of one.)
        start = datetime(due_date.year, due_date.month, due_date.day)
        ev.setAllDay_(True)
        ev.setStartDate_(_allday_nsdate(start))
        ev.setEndDate_(_allday_nsdate(start))

    if url:
        try:
            from Foundation import NSURL
            ev.setURL_(NSURL.URLWithString_(url))
        except Exception:
            pass

    ok, err = store.saveEvent_span_commit_error_(ev, EKSpanThisEvent, True, None)
    if not ok:
        raise RuntimeError(f"Failed to save event '{title}': {err}")
    return str(ev.calendarItemIdentifier())


def delete_event(store, event_identifier):
    ev = find_event(store, event_identifier)
    if ev is None:
        return
    store.removeEvent_span_commit_error_(ev, EKSpanThisEvent, True, None)
