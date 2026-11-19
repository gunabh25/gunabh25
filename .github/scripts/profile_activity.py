"""Build the profile's self-contained SVG from GitHub contribution history."""
import json
import math
import os
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGIN = os.environ.get("GITHUB_REPOSITORY_OWNER", "gunabh25")
DAY = timedelta(days=1)


def github(query, **variables):
    command = ["gh", "api", "graphql", "-f", f"query={query}", "-f", f"login={LOGIN}"]
    for key, value in variables.items():
        command.extend(["-f", f"{key}={value}"])
    return json.loads(subprocess.check_output(command))["data"]["user"]


def authored_commits(date_range=None):
    query = f"author:{LOGIN}"
    if date_range:
        query += f" author-date:{date_range}"
    for order in ("desc", "asc"):
        response = json.loads(subprocess.check_output([
            "gh", "api", "-X", "GET", "search/commits", "-f", f"q={query}",
            "-f", "per_page=1", "-f", "sort=author-date", "-f", f"order={order}",
        ]))
        if not response["incomplete_results"]:
            return response["total_count"]
    raise RuntimeError("GitHub commit search returned partial results. Retry the refresh.")


def history(today):
    account = github("""query($login:String!) {
      user(login:$login){createdAt contributionsCollection{contributionYears}}
    }""")
    first_year = min(int(account["createdAt"][:4]), *account["contributionsCollection"]["contributionYears"])
    days = {}
    for year in range(first_year, today.year + 1):
        end = min(today, date(year, 12, 31))
        collection = github("""query($login:String!,$start:DateTime!,$end:DateTime!) {
          user(login:$login){contributionsCollection(from:$start,to:$end) {
            contributionCalendar{weeks{contributionDays{date contributionCount}}}
          }}
        }""", start=f"{year}-01-01T00:00:00Z", end=f"{end}T23:59:59Z")["contributionsCollection"]
        for week in collection["contributionCalendar"]["weeks"]:
            for entry in week["contributionDays"]:
                day = date.fromisoformat(entry["date"])
                if day.year == year and day <= end:
                    days[day] = entry["contributionCount"]
    return days


def longest_streak(days):
    active = sorted(day for day, count in days.items() if count)
    best = run = 0
    previous = end = None
    for day in active:
        run = run + 1 if previous and day == previous + DAY else 1
        if run > best:
            best, end = run, day
        previous = day
    return best, end


def tower(x, y, height, colors):
    # Neighboring weeks recede slightly as the rows advance toward the viewer.
    a, b = (12, -1.3), (5, 4.7)
    roof = [(x, y-height), (x+a[0], y+a[1]-height),
            (x+a[0]+b[0], y+a[1]+b[1]-height), (x+b[0], y+b[1]-height)]
    def face(points, fill):
        coords = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
        return f'<polygon points="{coords}" fill="{fill}"/>'
    faces = []
    for i, j, fill in [(1, 2, colors[1]), (2, 3, colors[2])]:
        p, q = roof[i], roof[j]
        faces.append(face([p, q, (q[0], q[1]+height), (p[0], p[1]+height)], fill))
    return "".join(faces) + face(roof, colors[0])


def render(total, year_count, days, today):
    streak, end = longest_streak(days)
    period = f"{end - (streak-1)*DAY:%d %b %Y} – {end:%d %b %Y}" if end else "No active days"
    summary = f"{total:,} indexed authored commits, {year_count:,} commits in {today.year}, {streak} days longest contribution streak"
    svg = [f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 406" role="img" aria-labelledby="title desc">
<title id="title">GitHub activity skyline</title><desc id="desc">{summary}. {period}. Taller towers represent more daily contributions.</desc>
<style>
text{{font-family:system-ui,-apple-system,sans-serif;fill:#f4f6ff}}
.label{{fill:#b8c3df;font-size:15px}} .micro{{fill:#a6b6cf;font-size:13px}}
.value{{font-size:44px;font-weight:700}}
@keyframes hover{{50%{{transform:translateY(-5px)}}}}
.bot{{animation:hover 3s ease-in-out infinite}}
@media(prefers-reduced-motion:reduce){{.bot{{animation:none}}}}
</style>
<defs><linearGradient id="sky" x2="1" y2="1" gradientUnits="objectBoundingBox">
<stop stop-color="#19213c"/><stop offset="1" stop-color="#101424"/></linearGradient></defs>
<rect width="920" height="406" rx="22" fill="url(#sky)"/>
<path d="M34 38h16m-8-8v16" stroke="#6eedd5" stroke-width="2"/>
<text x="63" y="44" font-size="20" font-weight="600">Activity skyline</text>
<text x="884" y="43" text-anchor="end" class="micro">{today:%d %b %Y} UTC</text>
<path d="M34 62h852 M34 179h852" stroke="#36415d"/>''']
    for x, label, value in [(34, "Authored commits · all time", f"{total:,}"),
                            (316, f"Commits in {today.year}", f"{year_count:,}"),
                            (595, "Longest contribution streak", f"{streak} days")]:
        svg.append(f'<text x="{x}" y="91" class="label">{label}</text><text x="{x}" y="141" class="value">{value}</text>')
    svg.append(f'<text x="597" y="163" class="micro">{period}</text>')
    first = today - 364*DAY
    sunday = first - ((first.weekday()+1) % 7)*DAY
    for weekday in range(7):
        for week in reversed(range(54)):
            day = sunday + (week*7+weekday)*DAY
            if not first <= day <= today:
                continue
            count = days.get(day, 0)
            colors = ("#33445d","#26334b","#293950")
            if count:
                colors = ("#78efdc","#24999c","#36878f") if count < 8 else ("#b3a7ff","#7763d1","#6456ae")
            height = 2 + 12*math.log2(count+1)
            svg.append(tower(52+week*14+weekday*6, 327-week*1.5+weekday*5.8, min(height,92), colors))
    svg.append('''<g transform="translate(107 220)">
<ellipse cx="0" cy="36" rx="20" ry="4" fill="#111726"/>
<g class="bot" stroke-linejoin="round">
<path d="M-19 0l22-6 15 8-23 6z" fill="#dedaff"/>
<path d="M-19 0l14 8v21l-14-9z" fill="#7263b4"/>
<path d="M-5 8l23-6v20l-23 7z" fill="#afa1f7"/>
<path d="M-2 11l16-4v9l-16 4z" fill="#172137"/>
<path d="M2 13v3m8-5v3" stroke="#81ffdb" stroke-width="2.8"/>
<path d="M0-3v-8" stroke="#b4aaff" stroke-width="2"/>
<circle cy="-12" r="3" fill="#87f8d8"/></g></g>''')
    svg.append(f'<text x="34" y="384" class="micro">{first:%b %Y} – {today:%b %Y}</text>')
    svg.append('<text x="884" y="384" text-anchor="end" class="micro">One tower per day · Height shows contributions</text></svg>')
    return "\n".join(svg)+"\n", summary


if __name__ == "__main__":
    today = datetime.now(timezone.utc).date()
    days = history(today)
    total = authored_commits()
    year_count = authored_commits(f"{today.year}-01-01..{today}")
    svg, summary = render(total, year_count, days, today)
    (ROOT / "assets/activity-skyline.svg").write_text(svg)
    print(summary)
