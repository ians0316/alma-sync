"""Logs into an Alma SIS portal (getalma.com) and scrapes the student's to-do/assignments list."""
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from platform_support import get_secret as get_keychain_password, notify  # noqa: F401 (re-exported)

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Seoul Academy's fixed period bell times, from the Class Schedule "grid" view
# (/home/schedule). Each period keeps the same clock time every day it meets,
# even though which class occupies it rotates on a Day 1/2/3/4 cycle.
PERIOD_TIMES = {
    "P1": ("08:20", "09:45"),
    "P2": ("10:25", "11:50"),
    "P3": ("12:50", "14:15"),
    "P4": ("14:25", "15:50"),
    "P5": ("08:20", "09:40"),
    "P6": ("10:50", "12:10"),
    "P7": ("13:00", "14:20"),
    "P8": ("14:30", "15:50"),
    "CC": ("09:50", "10:40"),
    "AD": ("09:55", "10:15"),
}


def get_period_code(class_name: str) -> str | None:
    m = re.match(r"P(\d)\b", class_name)
    if m:
        code = f"P{m.group(1)}"
        return code if code in PERIOD_TIMES else None
    lowered = class_name.lower()
    if "cocurricular" in lowered:
        return "CC"
    if "advisory" in lowered:
        return "AD"
    return None


@dataclass
class Assignment:
    id: str
    class_name: str
    name: str
    due: date
    url: str
    period: str | None = None
    category: str = ""
    # Raw text of every cell in the class-page row (grade, weight, points, comment, graded date).
    cells: list[str] = field(default_factory=list)


@dataclass
class ClassGrade:
    letter: str
    percent: float | None  # 0.948 for 94.8%
    as_of: date | None


@dataclass
class ScrapeResult:
    assignments: list[Assignment]  # every assignment on every class page, past and future
    class_grades: dict[str, ClassGrade]


def _infer_due_date(month_abbr: str, day: int, today: date) -> date:
    month = MONTHS[month_abbr]
    year = today.year
    candidate = date(year, month, day)
    delta = (candidate - today).days
    if delta < -180:
        candidate = date(year + 1, month, day)
    elif delta > 180:
        candidate = date(year - 1, month, day)
    return candidate


def login(page, base_url: str, username: str, password: str, otp_prompt=None) -> bool:
    """Returns True if we end up on an authenticated page."""
    page.goto(f"{base_url}/home/assignments", wait_until="domcontentloaded")

    if page.locator("#login-form").count() == 0:
        return True  # already logged in (persisted session)

    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)

    trust = page.locator('input[name="trustDevice"]')
    if trust.count() > 0 and trust.is_visible():
        trust.check()

    page.click('#login-form button[type="submit"], #login-form input[type="submit"]')
    page.wait_for_load_state("domcontentloaded")

    otp_input = page.locator('input[name="otp"]:not([disabled])')
    try:
        otp_input.wait_for(state="visible", timeout=3000)
        needs_otp = True
    except PWTimeoutError:
        needs_otp = False

    if needs_otp:
        if otp_prompt is None:
            notify("Alma Sync", "2FA code needed — run setup mode to re-authenticate.")
            return False
        code = otp_prompt()
        otp_input.fill(code)
        page.click('#login-form button[type="submit"], #login-form input[type="submit"]')
        page.wait_for_load_state("domcontentloaded")

    page.goto(f"{base_url}/home/assignments", wait_until="domcontentloaded")
    return page.locator("#login-form").count() == 0


def get_classes(page, base_url: str) -> dict[str, str]:
    """Returns {class_id: class_name} for every class on the student's schedule."""
    page.goto(f"{base_url}/home/schedule", wait_until="domcontentloaded")
    page.wait_for_selector("a[href*='/home/class/']", timeout=15000)
    links = page.locator("a[href*='/home/class/']")
    classes = {}
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href") or ""
        m = re.search(r"/home/class/([a-f0-9]+)", href)
        name = links.nth(i).inner_text().strip()
        if m and name and m.group(1) not in classes:
            classes[m.group(1)] = name
    return classes


CLASS_GRADE = re.compile(r"In Progress Grade\s+As of ([\d/]+)\s+([A-F][+-]?)\s*(?:\(([\d.]+)%\))?", re.I)


def _split_name_cell(cell: str, name: str) -> tuple[str, str]:
    """The name cell reads "<Category> <Assignment name>". Returns (category, name)."""
    if name and cell.endswith(name):
        return cell[: -len(name)].strip(), name
    # Untitled links: Alma still shows text such as "MIDTERM PRESENTATION Presentation".
    m = re.match(r"^([A-Z0-9 &/]+?)\s+([A-Z][a-z].*)$", cell)
    return (m.group(1), m.group(2)) if m else ("", cell or name)


def scrape_class_assignments(page, base_url: str, class_id: str, class_name: str,
                             today: date) -> tuple[list[Assignment], ClassGrade | None]:
    """Scrapes one class's own assignment list, which — unlike the aggregated
    /home/assignments To Do page — includes assignments that are already
    graded, even ones due today. The To Do page drops those immediately,
    which was causing legitimately-current assignments to go unsynced.
    Also returns the class's In Progress grade shown at the top of the page."""
    page.goto(f"{base_url}/home/class/{class_id}", wait_until="domcontentloaded")
    try:
        page.wait_for_selector("a[href*='/home/assignment/']", timeout=5000)
    except PWTimeoutError:
        return [], None  # this class has no assignments at all

    g = CLASS_GRADE.search(page.inner_text("body"))
    grade = ClassGrade(
        letter=g.group(2),
        percent=float(g.group(3)) / 100 if g.group(3) else None,
        as_of=datetime.strptime(g.group(1), "%m/%d/%y").date(),
    ) if g else None

    assignments = []
    rows = page.locator("table tbody tr")
    for i in range(rows.count()):
        row = rows.nth(i)
        link = row.locator("a[href*='/home/assignment/']").first
        if link.count() == 0:
            continue

        cells = [c.replace("\n", " ").strip() for c in row.locator("td").all_inner_texts()]
        m = re.match(r"([A-Za-z]{3})\s+(\d{1,2})", cells[0]) if cells else None
        if not m:
            continue
        due = _infer_due_date(m.group(1), int(m.group(2)), today)

        href = link.get_attribute("href") or ""
        link_text = link.inner_text().strip()
        name_cell = next((c for c in cells[1:] if c and (not link_text or c.endswith(link_text))), "")
        category, assignment_name = _split_name_cell(name_cell, link_text)
        id_match = re.search(r"/assignment/([a-f0-9]+)", href)
        assignment_id = id_match.group(1) if id_match else href
        url = base_url + href if href.startswith("/") else href

        assignments.append(Assignment(
            id=assignment_id,
            class_name=class_name,
            name=assignment_name,
            due=due,
            url=url,
            period=get_period_code(class_name),
            category=category.title() if category.isupper() else category,
            cells=cells,
        ))
    return assignments, grade


def scrape_assignments(page, base_url: str, today: date = None) -> ScrapeResult:
    """Collects every assignment from every class page (see scrape_class_assignments)
    rather than the single /home/assignments To Do list, plus each class's grade."""
    today = today or date.today()
    classes = get_classes(page, base_url)

    by_id: dict[str, Assignment] = {}
    grades: dict[str, ClassGrade] = {}
    for class_id, class_name in classes.items():
        found, grade = scrape_class_assignments(page, base_url, class_id, class_name, today)
        for a in found:
            by_id[a.id] = a
        if grade:
            grades[class_name] = grade
    return ScrapeResult(assignments=list(by_id.values()), class_grades=grades)


def run_scrape(base_url: str, username: str, password: str, profile_dir: str,
                headless: bool = True, otp_prompt=None):
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            # Wide enough that class pages show the grade, weight and points columns.
            profile_dir, headless=headless, viewport={"width": 1300, "height": 900},
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            ok = login(page, base_url, username, password, otp_prompt=otp_prompt)
            if not ok:
                return None
            return scrape_assignments(page, base_url)
        finally:
            context.close()
