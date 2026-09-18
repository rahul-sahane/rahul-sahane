#!/usr/bin/env python3
"""Generate an SVG snake that travels only through zero-contribution cells."""
import os, sys, html
from collections import deque
import requests

API = "https://api.github.com/graphql"
USERNAME = os.environ.get("GITHUB_USER", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
if not USERNAME or not TOKEN:
    raise SystemExit("GITHUB_USER and GITHUB_TOKEN are required")

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
            color
            weekday
          }
        }
      }
    }
  }
}
"""

resp = requests.post(
    API,
    json={"query": QUERY, "variables": {"login": USERNAME}},
    headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"},
    timeout=30,
)
resp.raise_for_status()
payload = resp.json()
if payload.get("errors"):
    raise SystemExit("GitHub GraphQL error: " + str(payload["errors"]))

user = payload.get("data", {}).get("user")
if not user:
    raise SystemExit(f"GitHub user not found: {USERNAME}")

weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]

# GitHub weekday is 0=Sunday ... 6=Saturday. Do NOT subtract 1.
grid = {}
for x, week in enumerate(weeks):
    for day in week["contributionDays"]:
        grid[(x, int(day["weekday"]))] = day

occupied = {p for p, d in grid.items() if d["contributionCount"] > 0}
empty = set(grid) - occupied

def neighbors(p):
    x, y = p
    for q in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)):
        if q in empty:
            yield q

# Find connected empty-cell regions.
components = []
remaining = set(empty)
while remaining:
    start = next(iter(remaining))
    comp = {start}
    q = deque([start])
    remaining.remove(start)
    while q:
        p = q.popleft()
        for n in neighbors(p):
            if n in remaining:
                remaining.remove(n)
                comp.add(n)
                q.append(n)
    components.append(comp)

if not components:
    raise SystemExit("No zero-contribution cells found.")

component = max(components, key=len)

# DFS walk. Every point is taken from component, so the snake never occupies
# a contribution cell. Revisiting empty cells is intentional.
start = min(component, key=lambda p: (p[0], p[1]))
walk = []
visited = set()

def dfs(p):
    visited.add(p)
    walk.append(p)
    options = [n for n in neighbors(p) if n in component and n not in visited]
    options.sort(key=lambda n: sum(1 for z in neighbors(n) if z not in visited))
    for n in options:
        dfs(n)
        walk.append(p)

dfs(start)

CELL = 16
GAP = 4
STEP = CELL + GAP
MARGIN = 10
WIDTH = len(weeks) * STEP + MARGIN * 2
HEIGHT = 7 * STEP + MARGIN * 2

def center(pos):
    x, y = pos
    return MARGIN + x * STEP + CELL / 2, MARGIN + y * STEP + CELL / 2

path_d = " ".join(
    ("M" if i == 0 else "L") + f"{center(p)[0]:.1f},{center(p)[1]:.1f}"
    for i, p in enumerate(walk)
)

duration = max(12, min(45, len(walk) * 0.07))

svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="GitHub contributions with a snake moving only through empty cells">',
    "<style>.cell{shape-rendering:geometricPrecision}.snake{filter:url(#shadow)}</style>",
    '<defs><filter id="shadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="0" dy="1" stdDeviation="1" flood-opacity=".25"/></filter></defs>',
    '<rect width="100%" height="100%" fill="transparent"/>',
]

for (x, y), day in sorted(grid.items()):
    px = MARGIN + x * STEP
    py = MARGIN + y * STEP
    color = day["color"] if day["contributionCount"] > 0 else "#ebedf0"
    svg.append(
        f'<rect class="cell" x="{px}" y="{py}" width="{CELL}" height="{CELL}" rx="3" fill="{html.escape(color)}">'
        f'<title>{html.escape(day["date"])}: {day["contributionCount"]} contributions</title></rect>'
    )

svg.append(f'<path id="snakePath" d="{path_d}" fill="none" stroke="none"/>')

for i in range(7, 0, -1):
    radius = 4.8 if i == 7 else 4.0
    color = "#ff6b35" if i == 7 else "#ff8c5a"
    delay = -(i * duration / 9)
    svg.append(
        f'<circle class="snake" r="{radius}" fill="{color}">'
        f'<animateMotion dur="{duration:.2f}s" repeatCount="indefinite" begin="{delay:.2f}s" rotate="auto">'
        '<mpath href="#snakePath"/></animateMotion></circle>'
    )

svg.append(
    '<circle r="6" fill="#ff5a36" stroke="#ffffff" stroke-width="1.5" class="snake">'
    f'<animateMotion dur="{duration:.2f}s" repeatCount="indefinite" rotate="auto">'
    '<mpath href="#snakePath"/></animateMotion></circle>'
)
svg.append("</svg>")

out = os.environ.get("OUTPUT", "dist/empty-snake.svg")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(svg))

print(f"Generated {out}")
print(f"Zero-contribution cells in selected region: {len(component)}")
print(f"Animation path points: {len(walk)}")
