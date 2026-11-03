#!/usr/bin/env python3
"""Generate dist/github-stats.svg for a GitHub profile README.

Layout: total contributions, current streak, longest streak,
commits by hour, top languages by repo and by commit.

Env vars:
  GH_USERNAME  GitHub login (required unless --demo)
  GH_TOKEN     token for the API (Actions' github.token works for public data;
               a PAT with read:user also counts private contributions)
  DISPLAY_NAME / TAGLINE  header text (optional)
  STATS_TZ     IANA timezone for the hour chart (default Asia/Kolkata)
"""
import json, os, sys, urllib.request
from collections import Counter
from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

API = "https://api.github.com"
OUT = os.environ.get("STATS_OUT", "dist/github-stats.svg")
MAX_REPOS, MAX_PAGES = 40, 5  # commit history cap per repo = MAX_PAGES * 100


# ---------------------------------------------------------------- data
def _req(url, token, body=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "stats-card"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers)) as r:
        return json.load(r)


def gql(query, token):
    res = _req(f"{API}/graphql", token, {"query": query})
    if "errors" in res:
        raise RuntimeError(res["errors"])
    return res["data"]


def fetch(user, token, tz):
    info = gql(
        '{ user(login:"%s"){ createdAt repositories(ownerAffiliations:OWNER,isFork:false,'
        "first:100,orderBy:{field:PUSHED_AT,direction:DESC}){nodes{name isArchived "
        "primaryLanguage{name color}}}}}" % user, token)["user"]
    created = int(info["createdAt"][:4])
    now = datetime.utcnow()
    parts = []
    for y in range(created, now.year + 1):
        parts.append(
            f'y{y}: contributionsCollection(from:"{y}-01-01T00:00:00Z",to:"{y}-12-31T23:59:59Z")'
            "{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}")
    cal = gql('{ user(login:"%s"){ %s }}' % (user, " ".join(parts)), token)["user"]
    days = {}
    for v in cal.values():
        for w in v["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    repos = [r for r in info["repositories"]["nodes"]][:MAX_REPOS]
    hours, lang_repo, lang_commit = Counter(), Counter(), Counter()
    colors = {}
    for r in repos:
        pl = r["primaryLanguage"]
        lang = pl["name"] if pl else None
        if lang:
            lang_repo[lang] += 1
            colors[lang] = pl["color"] or "#8B94B3"
        for page in range(1, MAX_PAGES + 1):
            try:
                commits = _req(f"{API}/repos/{user}/{r['name']}/commits?author={user}"
                               f"&per_page=100&page={page}", token)
            except Exception:
                break
            for c in commits:
                ts = c["commit"]["author"]["date"].replace("Z", "+00:00")
                hours[datetime.fromisoformat(ts).astimezone(tz).hour] += 1
                if lang:
                    lang_commit[lang] += 1
            if len(commits) < 100:
                break
    return days, hours, lang_repo, lang_commit, colors, created


def demo():
    import random
    random.seed(7)
    days, d = {}, date.today() - timedelta(days=700)
    while d <= date.today():
        days[d.isoformat()] = random.choice([0, 0, 1, 2, 3, 5, 8]) if d.weekday() < 6 else random.choice([0, 0, 1])
        d += timedelta(days=1)
    for i in range(23):  # make a current streak
        days[(date.today() - timedelta(days=i)).isoformat()] = max(1, days[(date.today() - timedelta(days=i)).isoformat()])
    hours = Counter({h: int(40 * (1 - abs(h - 21) / 14) ** 2) + random.randint(0, 6) for h in range(24)})
    return (days, hours, Counter({"Java": 9, "JavaScript": 6, "HTML": 3, "CSS": 2, "Python": 1}),
            Counter({"Java": 410, "JavaScript": 240, "HTML": 90, "CSS": 40, "Python": 12}),
            {"Java": "#b07219", "JavaScript": "#f1e05a", "HTML": "#e34c26", "CSS": "#663399",
             "Python": "#3572A5"}, 2023)


# -------------------------------------------------------------- compute
def streaks(days):
    today = date.today()
    ds = sorted(days)
    longest = run = 0
    best_end = None
    prev = None
    for s in ds:
        d = date.fromisoformat(s)
        if days[s] > 0:
            run = run + 1 if prev and (d - prev).days == 1 else 1
            prev = d
            if run > longest:
                longest, best_end = run, d
        else:
            run, prev = 0, None
    # current streak: walk back from today (today may still be empty)
    cur, d = 0, today
    if days.get(d.isoformat(), 0) == 0:
        d -= timedelta(days=1)
    cur_end = d
    while days.get(d.isoformat(), 0) > 0:
        cur += 1
        d -= timedelta(days=1)
    cur_start = cur_end - timedelta(days=cur - 1) if cur else None
    best_start = best_end - timedelta(days=longest - 1) if longest else None
    return cur, (cur_start, cur_end if cur else None), longest, (best_start, best_end)


def fmt_range(rng):
    a, b = rng
    if not a:
        return "No active streak"
    f = lambda x: x.strftime("%b %-d")
    return f"{f(a)} – {f(b)}" if a != b else f(a)


def hour_label(h):
    return f"{h % 12 or 12}{'AM' if h < 12 else 'PM'}"


# --------------------------------------------------------------- render
CIRC = 427.26
PALETTE = ["#4F8EF7", "#F34B7D", "#F1E05A", "#2DD4BF", "#F97316", "#8B94B3"]


def donut(cx, cy, items, delay):
    """items: [(name, value, color)] -> svg + legend rows."""
    total = sum(v for _, v, _ in items) or 1
    out = [f'<circle cx="{cx}" cy="{cy}" r="68" fill="none" stroke="#fff" stroke-opacity=".06" stroke-width="26"/>']
    acc, d = 0.0, delay
    for _, v, c in items:
        ln = CIRC * v / total
        out.append(
            f'<circle class="seg" cx="{cx}" cy="{cy}" r="68" fill="none" stroke="{c}" stroke-width="26" '
            f'stroke-dasharray="{max(ln - 1.5, 0.5):.2f} {CIRC}" stroke-dashoffset="{-acc - 0.75:.2f}" '
            f'transform="rotate(-90 {cx} {cy})" style="animation-delay:{d:.2f}s;--len:{max(ln - 1.5, 0.5):.2f}"/>')
        acc += ln
        d += 0.12
    return "\n".join(out), total


def lang_panel(x, title, counter, colors, legend_x, pct_x, ring_cx, delay, width=550):
    top = counter.most_common(5)
    rest = sum(counter.values()) - sum(v for _, v in top)
    items = [(n, v, colors.get(n) or PALETTE[i]) for i, (n, v) in enumerate(top)]
    if rest > 0:
        items.append(("Other", rest, PALETTE[5]))
    s = [f'<rect class="tile" style="animation-delay:{delay:.2f}s" x="{x}" y="526" width="{width}" height="250" rx="20" '
         f'fill="#fff" fill-opacity=".04" stroke="#fff" stroke-opacity=".09"/>',
         f'<g class="fade" style="animation-delay:{delay + .2:.2f}s">'
         f'<text x="{x + 28}" y="566" font-size="15" font-weight="600" fill="#8B94B3">{escape(title)}</text></g>']
    if not items:
        s.append(f'<text x="{x + width / 2}" y="660" text-anchor="middle" font-size="14" fill="#8B94B3">No data yet</text>')
        return "\n".join(s)
    ring, total = donut(ring_cx, 668, items, delay + 0.3)
    s.append(ring)
    lead = items[0]
    s.append(f'<g class="fade" style="animation-delay:{delay + .8:.2f}s">'
             f'<text x="{ring_cx}" y="672" text-anchor="middle" font-size="24" font-weight="800" fill="url(#numfill)">'
             f'{round(100 * lead[1] / total)}%</text>'
             f'<text x="{ring_cx}" y="690" text-anchor="middle" font-size="12" fill="#8B94B3">{escape(lead[0][:12])}</text></g>')
    for i, (n, v, c) in enumerate(items):
        y = 604 + i * 31
        s.append(f'<g class="fade" style="animation-delay:{delay + .4 + i * .08:.2f}s">'
                 f'<circle cx="{legend_x + 6}" cy="{y - 5}" r="6" fill="{c}"/>'
                 f'<text x="{legend_x + 22}" y="{y}" font-size="15" font-weight="600" fill="#E8ECF8">{escape(n[:20])}</text>'
                 f'<text x="{pct_x}" y="{y}" text-anchor="end" font-size="14" font-weight="600" fill="#8B94B3">'
                 f'{100 * v / total:.0f}%</text></g>')
    return "\n".join(s)


def render(user, name, tagline, days, hours, lang_repo, lang_commit, colors, since, tz_name):
    total = sum(days.values())
    cur, cur_rng, longest, best_rng = streaks(days)
    prog = min(cur / longest, 1) if longest else 0
    RC = 2 * 3.14159265 * 62

    # hour bars
    mx = max(hours.values()) if hours else 0
    peak = max(range(24), key=lambda h: hours.get(h, 0)) if mx else None
    bars = []
    for h in range(24):
        v = hours.get(h, 0)
        ht = 6 + 104 * v / mx if mx else 4
        x = 68 + h * 44.2
        grad = "barPeak" if h == peak else "bar"
        bars.append(f'<rect class="bar" style="animation-delay:{.5 + h * .03:.2f}s" x="{x:.1f}" y="{476 - ht:.1f}" '
                    f'width="28" height="{ht:.1f}" rx="6" fill="url(#{grad})"><title>{hour_label(h)}: {v} commits</title></rect>')
        if h % 3 == 0:
            bars.append(f'<text x="{x + 14:.1f}" y="496" text-anchor="middle" font-size="12" fill="#8B94B3">{hour_label(h)}</text>')
    if peak is not None:
        bars.append(f'<text x="{68 + peak * 44.2 + 14:.1f}" y="{470 - (6 + 104):.1f}" text-anchor="middle" '
                    f'font-size="13" font-weight="700" fill="#7CF3E0">{hours[peak]}</text>')
    peak_txt = f"Most active around {hour_label(peak)} ({tz_name})" if peak is not None else "No commit data yet"

    tile = lambda x, y, w, h, d, edge="": (
        f'<rect class="tile" style="animation-delay:{d}s" x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="#fff" '
        f'fill-opacity=".04" ' + (f'stroke="url(#tileEdge)" stroke-width="1.4"' if edge else 'stroke="#fff" stroke-opacity=".09"') + '/>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800" width="1200" height="800" role="img" aria-labelledby="t d">
<title id="t">GitHub stats for {escape(name)}</title>
<desc id="d">Total contributions, current and longest streak, commits by hour, and top languages by repository and by commit.</desc>
<style>
text{{font-family:'Segoe UI Variable Display','Segoe UI','SF Pro Display',Inter,system-ui,-apple-system,Roboto,'Helvetica Neue',Arial,sans-serif;font-variant-numeric:tabular-nums}}
.tile,.fade{{opacity:0;animation:fade .7s ease forwards}}
.bar{{transform-box:fill-box;transform-origin:50% 100%;transform:scaleY(0);animation:grow .8s cubic-bezier(.2,.8,.2,1) forwards}}
.seg{{stroke-dasharray:0 {CIRC};animation:seg .9s ease forwards}}
.ring{{stroke-dashoffset:{RC:.2f};animation:ringin 1.2s cubic-bezier(.2,.8,.2,1) .4s forwards}}
@keyframes fade{{to{{opacity:1}}}}
@keyframes grow{{to{{transform:scaleY(1)}}}}
@keyframes seg{{to{{stroke-dasharray:var(--len) {CIRC}}}}}
@keyframes ringin{{to{{stroke-dashoffset:{RC * (1 - prog):.2f}}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.tile,.fade{{opacity:1}}.bar{{transform:none}}.seg{{stroke-dasharray:var(--len) {CIRC}}}.ring{{stroke-dashoffset:{RC * (1 - prog):.2f}}}}}
</style>
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0A0F1F"/><stop offset="1" stop-color="#0F1530"/></linearGradient>
<radialGradient id="glowA" cx=".12" cy=".05" r=".55"><stop offset="0" stop-color="#7C5CFF" stop-opacity=".28"/><stop offset="1" stop-color="#7C5CFF" stop-opacity="0"/></radialGradient>
<radialGradient id="glowB" cx=".92" cy=".98" r=".5"><stop offset="0" stop-color="#22D3EE" stop-opacity=".2"/><stop offset="1" stop-color="#22D3EE" stop-opacity="0"/></radialGradient>
<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#fff" fill-opacity=".055"/></pattern>
<linearGradient id="numfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#C9D2F5"/></linearGradient>
<linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5EEAD4"/><stop offset=".55" stop-color="#818CF8"/><stop offset="1" stop-color="#C084FC"/></linearGradient>
<linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8B9BFF"/><stop offset="1" stop-color="#4338CA" stop-opacity=".75"/></linearGradient>
<linearGradient id="barPeak" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7CF3E0"/><stop offset="1" stop-color="#6366F1"/></linearGradient>
<linearGradient id="tileEdge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5EEAD4" stop-opacity=".55"/><stop offset=".5" stop-color="#818CF8" stop-opacity=".35"/><stop offset="1" stop-color="#C084FC" stop-opacity=".55"/></linearGradient>
<clipPath id="frame"><rect width="1200" height="800" rx="28"/></clipPath>
</defs>
<g clip-path="url(#frame)"><rect width="1200" height="800" fill="url(#bg)"/><rect width="1200" height="800" fill="url(#dots)"/><rect width="1200" height="800" fill="url(#glowA)"/><rect width="1200" height="800" fill="url(#glowB)"/></g>
<rect x=".5" y=".5" width="1199" height="799" rx="28" fill="none" stroke="#fff" stroke-opacity=".08"/>

<text x="40" y="54" font-size="27" font-weight="800" fill="#E8ECF8" letter-spacing="-.4">GitHub stats</text>
<text x="40" y="78" font-size="14" fill="#8B94B3">{escape(name)}{', ' + escape(tagline) if tagline else ''}</text>

{tile(40, 96, 300, 190, 0.0)}
<g class="fade" style="animation-delay:.2s">
<text x="68" y="138" font-size="15" font-weight="600" fill="#8B94B3">Total contributions</text>
<text x="68" y="218" font-size="68" font-weight="800" fill="url(#numfill)">{total:,}</text>
<text x="68" y="254" font-size="14" fill="#8B94B3">since {since}</text></g>

{tile(360, 96, 480, 190, 0.1, edge=True)}
<circle cx="462" cy="196" r="62" fill="none" stroke="#fff" stroke-opacity=".06" stroke-width="14"/>
<circle class="ring" cx="462" cy="196" r="62" fill="none" stroke="url(#ring)" stroke-width="14" stroke-linecap="round" stroke-dasharray="{RC:.2f}" transform="rotate(-90 462 196)"/>
<g class="fade" style="animation-delay:.5s">
<text x="462" y="210" text-anchor="middle" font-size="40" font-weight="800" fill="url(#numfill)">{cur}</text>
<text x="570" y="138" font-size="15" font-weight="600" fill="#8B94B3">Current streak</text>
<text x="570" y="196" font-size="44" font-weight="800" fill="url(#numfill)">{cur} <tspan font-size="20" font-weight="600" fill="#8B94B3">{'day' if cur == 1 else 'days'}</tspan></text>
<text x="570" y="236" font-size="14" fill="#8B94B3">{escape(fmt_range(cur_rng))}</text></g>

{tile(860, 96, 300, 190, 0.2)}
<g class="fade" style="animation-delay:.4s">
<text x="888" y="138" font-size="15" font-weight="600" fill="#8B94B3">Longest streak</text>
<text x="888" y="206" font-size="60" font-weight="800" fill="url(#numfill)">{longest} <tspan font-size="20" font-weight="600" fill="#8B94B3">{'day' if longest == 1 else 'days'}</tspan></text>
<text x="888" y="246" font-size="14" fill="#8B94B3">{escape(fmt_range(best_rng))}</text></g>

{tile(40, 306, 1120, 200, 0.3)}
<g class="fade" style="animation-delay:.5s">
<text x="68" y="342" font-size="15" font-weight="600" fill="#8B94B3">Commits by hour</text>
<text x="1132" y="342" text-anchor="end" font-size="13" fill="#8B94B3">{escape(peak_txt)}</text></g>
{chr(10).join(bars)}

{lang_panel(40, "Top languages by repository", lang_repo, colors, 650, 1120, 400, 0.6, width=1120)}
</svg>
'''
    return svg


def main():
    tz_name = os.environ.get("STATS_TZ", "Asia/Kolkata")
    tz = ZoneInfo(tz_name)
    if "--demo" in sys.argv:
        user, data = "demo", demo()
    else:
        user = os.environ["GH_USERNAME"]
        data = fetch(user, os.environ.get("GH_TOKEN"), tz)
    days, hours, lr, lc, colors, since = data
    name = os.environ.get("DISPLAY_NAME", user)
    tagline = os.environ.get("TAGLINE", "")
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(user, name, tagline, days, hours, lr, lc, colors, since, tz_name))
    print("wrote", OUT)


if __name__ == "__main__":
    main()

