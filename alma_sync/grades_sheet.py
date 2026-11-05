"""Rebuilds the "Grades" tab of a Google Sheet from a full Alma scrape.

The tab gets a summary table (one row per class) and then one section per
class: a colored header with the class grade, column labels, every assignment
(past, present and upcoming) and a blank spacer row. The whole tab is cleared
and rewritten on every run, so it always matches Alma.

Auth is the same Google Cloud service account as google_store.py; the
spreadsheet must be shared with that account as an editor.
"""
import re
import time
from datetime import date, datetime

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from google_store import KEY_PATH

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
API = "https://sheets.googleapis.com/v4/spreadsheets"
TAB = "Grades"
NCOLS = 10  # A..J

GRADE = re.compile(r"^([A-F][+-]?)\s*\(([\d.]+)%\)$")
WEIGHT = re.compile(r"^[\d.]+%$")
POINTS = re.compile(r"^[\d.]+/[\d.]+$")
GRADED_ON = re.compile(r"^\d{1,2}/\d{1,2}/\d{2}$")

# Section header fill per class, matching the Notion class colors.
CLASS_COLORS = {
    "P1": "#E69138", "P2": "#CC0000", "P3": "#38761D", "P4": "#674EA7",
    "P5": "#85200C", "P6": "#1155CC", "P7": "#A64D79", "P8": "#666666",
}
OTHER_COLOR = "#BF9000"
COL_WIDTHS = [330, 170, 110, 120, 60, 70, 90, 70, 90, 380]


def _rgb(hex_color: str) -> dict:
    h = hex_color.lstrip("#")
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


def _text(s: str) -> str:
    # Leading apostrophe keeps Sheets from turning text like "1.7" or "9/10" into numbers or dates.
    return "'" + s if s else ""


def _class_sort_key(name: str):
    m = re.match(r"P(\d)\b", name)
    return (0, int(m.group(1)), name) if m else (1, 0, name)


def parse_grade(a):
    """Pulls grade details out of a class-page row's raw cells."""
    letter, score, weight, points, graded_on, comments = "", None, None, "", None, []
    for c in a.cells[1:]:
        if not c or c.endswith(a.name) and a.name:
            continue
        if g := GRADE.match(c):
            letter, score = g.group(1), float(g.group(2)) / 100
        elif WEIGHT.match(c):
            weight = float(c[:-1]) / 100
        elif POINTS.match(c):
            points = c
        elif GRADED_ON.match(c):
            graded_on = datetime.strptime(c, "%m/%d/%y").date()
        elif c not in ("(Ungraded)", "Ungraded", "-") and c != f"{a.category} {a.name}".strip():
            comments.append(c)
    return letter, score, weight, points, graded_on, " ".join(comments)


def _status(letter: str, due: date, today: date) -> str:
    if letter:
        return "Graded"
    return "Upcoming" if due > today else "Not graded yet"


def _session() -> AuthorizedSession:
    creds = service_account.Credentials.from_service_account_file(str(KEY_PATH), scopes=SCOPES)
    return AuthorizedSession(creds)


def _call(session, method: str, url: str, **kw) -> dict:
    for attempt in range(4):
        try:
            resp = session.request(method, url, timeout=60, **kw)
        except Exception as e:
            if attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"Sheets {method} failed after retries: {type(e).__name__}: {e}")
        if resp.status_code in (429, 500, 502, 503) and attempt < 3:
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"Sheets {method} {url.split('/')[-1]} failed: {resp.status_code} {resp.text[:300]}")
        return resp.json() if resp.content else {}
    raise RuntimeError("Sheets request kept failing")


def build_layout(result, today: date, synced_at: datetime):
    """Returns (values, plan): the 2D values for the tab and what to format where."""
    by_class: dict[str, list] = {}
    for a in result.assignments:
        by_class.setdefault(a.class_name, []).append(a)
    classes = sorted(set(by_class) | set(result.class_grades), key=_class_sort_key)
    classes = [c for c in classes if by_class.get(c)]

    values = [
        ["Grades"],
        ["Last updated", f"{synced_at:%a, %b %-d, %Y at %-I:%M %p}"],
        ["Rebuilt from Alma every hour. Edits on this tab get overwritten."],
        [],
        ["Class", "Grade", "Percent", "As of", "Graded", "Not graded yet", "Upcoming", "Lowest score so far"],
    ]
    summary_start = len(values)
    plan = {"summary_header": summary_start - 1, "summary_rows": (summary_start, summary_start + len(classes)), "sections": []}
    values += [[] for _ in classes]  # summary rows, filled once section ranges are known
    values.append([])

    # Recently graded: anything Alma marks as graded in the last 7 days, newest first.
    recent = []
    for a in result.assignments:
        letter, score, _, points, graded_on, comment = parse_grade(a)
        if letter and graded_on and 0 <= (today - graded_on).days <= 7:
            recent.append((graded_on, a, letter, score, points, comment))
    recent.sort(key=lambda x: (-x[0].toordinal(), _class_sort_key(x[1].class_name), x[1].name))
    rec_header = len(values)
    values.append(["Recently graded (last 7 days)"])
    values.append(["Assignment", "Class", "Graded on", "Due date", "Grade", "Score", "Points", "", "", "Teacher comment"])
    rec_first = len(values) + 1
    rec_rows = []
    for graded_on, a, letter, score, points, comment in recent:
        rec_rows.append((len(values) + 1, score))
        values.append([_text(a.name), _text(a.class_name), graded_on.isoformat(), a.due.isoformat(),
                       letter, score if score is not None else "", _text(points), "", "", _text(comment)])
    if not recent:
        values.append(["No new grades in the last 7 days."])
    plan["recent"] = {"header_row": rec_header, "labels_row": rec_header + 1, "first": rec_first,
                      "last": len(values), "rows": rec_rows}
    values.append([])

    summary = []
    for cls in classes:
        grade = result.class_grades.get(cls)
        header_row = len(values)
        label = cls if not grade else (
            f"{cls}   {grade.letter}" + (f" ({grade.percent:.1%})" if grade.percent is not None else "")
            + (f"   as of {grade.as_of:%b %-d}" if grade.as_of else "")
        )
        values.append([_text(label)])
        values.append(["Assignment", "Category", "Due date", "Status", "Grade", "Score", "Points", "Weight", "Graded on", "Teacher comment"])
        first = len(values) + 1  # 1-based sheet row of the first assignment
        rows_meta = []
        for a in sorted(by_class[cls], key=lambda a: (a.due, a.name)):
            letter, score, weight, points, graded_on, comment = parse_grade(a)
            r = len(values) + 1
            values.append([
                _text(a.name), _text(a.category), a.due.isoformat(),
                f'=IF(E{r}<>"","Graded",IF(C{r}>TODAY(),"Upcoming","Not graded yet"))',
                letter, score if score is not None else "", _text(points),
                weight if weight is not None else "",
                graded_on.isoformat() if graded_on else "", _text(comment),
            ])
            rows_meta.append((r, score, _status(letter, a.due, today)))
        last = len(values)
        values.append([])
        m = re.match(r"(P\d)\b", cls)
        plan["sections"].append({
            "header_row": header_row, "labels_row": header_row + 1, "first": first, "last": last,
            "color": CLASS_COLORS.get(m.group(1) if m else "", OTHER_COLOR), "rows": rows_meta,
        })
        rng = lambda col: f"${col}${first}:${col}${last}"
        summary.append([
            _text(cls), grade.letter if grade else "",
            grade.percent if grade and grade.percent is not None else "",
            grade.as_of.isoformat() if grade and grade.as_of else "",
            f'=COUNTIF({rng("D")},"Graded")', f'=COUNTIF({rng("D")},"Not graded yet")', f'=COUNTIF({rng("D")},"Upcoming")',
            f'=IFERROR(INDEX(SORT(FILTER({rng("A")}&" ("&TEXT({rng("F")},"0%")&")",{rng("F")}<>""),'
            f'FILTER({rng("F")},{rng("F")}<>""),TRUE),1),"")',
        ])
    for i, row in enumerate(summary):
        values[summary_start + i] = row
    return values, plan


def _grid(gid, r0, r1, c0=0, c1=NCOLS):
    return {"sheetId": gid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}


def _fmt(gid, r0, r1, c0, c1, fmt: dict, fields: str) -> dict:
    return {"repeatCell": {"range": _grid(gid, r0, r1, c0, c1), "cell": {"userEnteredFormat": fmt}, "fields": fields}}


def _format_requests(gid: int, plan: dict) -> list[dict]:
    reqs = [
        _fmt(gid, 0, 1, 0, 1, {"textFormat": {"bold": True, "fontSize": 16}}, "userEnteredFormat.textFormat"),
        _fmt(gid, 1, 2, 0, 2, {"textFormat": {"bold": True, "fontSize": 11}, "backgroundColor": _rgb("#FFF2CC")},
             "userEnteredFormat.textFormat,userEnteredFormat.backgroundColor"),
        _fmt(gid, 2, 3, 0, 1, {"textFormat": {"italic": True, "foregroundColor": _rgb("#777777")}}, "userEnteredFormat.textFormat"),
    ]
    rec = plan["recent"]
    hr, lr, first, last = rec["header_row"], rec["labels_row"], rec["first"], rec["last"]
    reqs += [
        {"mergeCells": {"range": _grid(gid, hr, hr + 1), "mergeType": "MERGE_ALL"}},
        _fmt(gid, hr, hr + 1, 0, NCOLS,
             {"backgroundColor": _rgb("#3C4043"), "textFormat": {"bold": True, "fontSize": 12, "foregroundColor": _rgb("#FFFFFF")}},
             "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat"),
        _fmt(gid, lr, lr + 1, 0, NCOLS, {"textFormat": {"bold": True}, "backgroundColor": _rgb("#EFEFEF")},
             "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"),
        _fmt(gid, first - 1, last, 2, 4, {"numberFormat": {"type": "DATE", "pattern": "mmm d (ddd)"}}, "userEnteredFormat.numberFormat"),
        _fmt(gid, first - 1, last, 5, 6, {"numberFormat": {"type": "PERCENT", "pattern": "0%"}}, "userEnteredFormat.numberFormat"),
        _fmt(gid, first - 1, last, 9, 10, {"wrapStrategy": "WRAP"}, "userEnteredFormat.wrapStrategy"),
        _fmt(gid, lr, last, 0, NCOLS, {"verticalAlignment": "TOP"}, "userEnteredFormat.verticalAlignment"),
        {"updateBorders": {"range": _grid(gid, lr, last), "bottom": _border(), "innerHorizontal": _border("#E0E0E0")}},
    ]
    for r, score in rec["rows"]:
        if score is not None and (score < 0.7 or score >= 0.9):
            reqs.append(_fmt(gid, r - 1, r, 4, 6, {"backgroundColor": _rgb("#F4CCCC" if score < 0.7 else "#D9EAD3")},
                             "userEnteredFormat.backgroundColor"))
    h = plan["summary_header"]
    s0, s1 = plan["summary_rows"]
    reqs += [
        _fmt(gid, h, h + 1, 0, 8, {"textFormat": {"bold": True}, "backgroundColor": _rgb("#D9D9D9")},
             "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"),
        _fmt(gid, s0, s1, 2, 3, {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}, "userEnteredFormat.numberFormat"),
        _fmt(gid, s0, s1, 3, 4, {"numberFormat": {"type": "DATE", "pattern": "mmm d"}}, "userEnteredFormat.numberFormat"),
        {"updateBorders": {"range": _grid(gid, h, s1, 0, 8), "top": _border(), "bottom": _border(),
                           "left": _border(), "right": _border(), "innerHorizontal": _border()}},
    ]
    for sec in plan["sections"]:
        hr, lr, first, last = sec["header_row"], sec["labels_row"], sec["first"], sec["last"]
        reqs += [
            {"mergeCells": {"range": _grid(gid, hr, hr + 1), "mergeType": "MERGE_ALL"}},
            _fmt(gid, hr, hr + 1, 0, NCOLS,
                 {"backgroundColor": _rgb(sec["color"]),
                  "textFormat": {"bold": True, "fontSize": 12, "foregroundColor": _rgb("#FFFFFF")}},
                 "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat"),
            _fmt(gid, lr, lr + 1, 0, NCOLS, {"textFormat": {"bold": True}, "backgroundColor": _rgb("#EFEFEF")},
                 "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor"),
            _fmt(gid, first - 1, last, 2, 3, {"numberFormat": {"type": "DATE", "pattern": "mmm d (ddd)"}}, "userEnteredFormat.numberFormat"),
            _fmt(gid, first - 1, last, 5, 6, {"numberFormat": {"type": "PERCENT", "pattern": "0%"}}, "userEnteredFormat.numberFormat"),
            _fmt(gid, first - 1, last, 7, 8, {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}, "userEnteredFormat.numberFormat"),
            _fmt(gid, first - 1, last, 8, 9, {"numberFormat": {"type": "DATE", "pattern": "mmm d"}}, "userEnteredFormat.numberFormat"),
            _fmt(gid, first - 1, last, 9, 10, {"wrapStrategy": "WRAP"}, "userEnteredFormat.wrapStrategy"),
            _fmt(gid, lr, last, 0, NCOLS, {"verticalAlignment": "TOP"}, "userEnteredFormat.verticalAlignment"),
            {"updateBorders": {"range": _grid(gid, lr, last), "bottom": _border(), "innerHorizontal": _border("#E0E0E0")}},
        ]
        for r, score, status in sec["rows"]:
            if score is not None and (score < 0.7 or score >= 0.9):
                reqs.append(_fmt(gid, r - 1, r, 4, 6, {"backgroundColor": _rgb("#F4CCCC" if score < 0.7 else "#D9EAD3")},
                                 "userEnteredFormat.backgroundColor"))
            if status == "Upcoming":
                reqs.append(_fmt(gid, r - 1, r, 3, 4, {"textFormat": {"foregroundColor": _rgb("#1155CC")}},
                                 "userEnteredFormat.textFormat.foregroundColor"))
            elif status == "Not graded yet":
                reqs.append(_fmt(gid, r - 1, r, 3, 4, {"textFormat": {"italic": True, "foregroundColor": _rgb("#808080")}},
                                 "userEnteredFormat.textFormat.italic,userEnteredFormat.textFormat.foregroundColor"))
    for i, w in enumerate(COL_WIDTHS):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"}})
    return reqs


def _border(color: str = "#BFBFBF") -> dict:
    return {"style": "SOLID", "width": 1, "colorStyle": {"rgbColor": _rgb(color)}}


def write_grades(spreadsheet_id: str, result, today: date | None = None) -> int:
    """Clears and rebuilds the Grades tab. Returns the number of assignment rows written."""
    today = today or date.today()
    session = _session()
    base = f"{API}/{spreadsheet_id}"

    meta = _call(session, "GET", base, params={"fields": "sheets(properties(sheetId,title,gridProperties),conditionalFormats)"})
    sheet = next((s for s in meta.get("sheets", []) if s["properties"]["title"] == TAB), None)
    if sheet is None:
        reply = _call(session, "POST", f"{base}:batchUpdate",
                      json={"requests": [{"addSheet": {"properties": {"title": TAB, "gridProperties": {"rowCount": 400, "columnCount": 12}}}}]})
        gid, row_count, n_rules = reply["replies"][0]["addSheet"]["properties"]["sheetId"], 400, 0
    else:
        gid = sheet["properties"]["sheetId"]
        row_count = sheet["properties"]["gridProperties"]["rowCount"]
        n_rules = len(sheet.get("conditionalFormats", []))

    values, plan = build_layout(result, today, datetime.now())
    needed = len(values) + 20

    clear = [{"deleteConditionalFormatRule": {"sheetId": gid, "index": 0}} for _ in range(n_rules)]
    if row_count < needed:
        clear.append({"appendDimension": {"sheetId": gid, "dimension": "ROWS", "length": needed - row_count}})
    total_rows = max(row_count, needed)
    clear += [
        {"unmergeCells": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": total_rows}}},
        {"repeatCell": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": total_rows},
                        "cell": {}, "fields": "userEnteredValue,userEnteredFormat"}},
        {"updateBorders": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": total_rows, "startColumnIndex": 0, "endColumnIndex": 12},
                           "top": {"style": "NONE"}, "bottom": {"style": "NONE"}, "left": {"style": "NONE"},
                           "right": {"style": "NONE"}, "innerHorizontal": {"style": "NONE"}, "innerVertical": {"style": "NONE"}}},
        {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 0, "frozenColumnCount": 0}},
                                   "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}},
        {"updateCells": {"rows": [{"values": [{"note": (
            "Source: Alma class pages (seoulacademy.getalma.com/home/class/...) for every class on the schedule. "
            "Rebuilt hourly by alma_sync (grades_sheet.py). Class grades are Alma's In Progress grades; "
            "Weight is each assignment's share of the class grade.")}]}],
                         "fields": "note", "start": {"sheetId": gid, "rowIndex": 0, "columnIndex": 0}}},
    ]
    _call(session, "POST", f"{base}:batchUpdate", json={"requests": clear})
    _call(session, "POST", f"{base}/values:batchUpdate", json={
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": f"'{TAB}'!A1", "values": values}],
    })
    _call(session, "POST", f"{base}:batchUpdate", json={"requests": _format_requests(gid, plan)})
    return sum(len(s["rows"]) for s in plan["sections"])
