#!/usr/bin/env python3
"""
Generate a GitHub contribution animation where the snake travels ONLY through
cells with zero contributions. Contribution cells are never used by the snake.

Requires:
  pip install requests
Environment:
  GITHUB_TOKEN - workflow token
  GITHUB_USER  - GitHub username
"""
import os, sys, math, html
import requests
from collections import defaultdict, deque

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
        colors
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
            color
            weekday
          }
        }
      }
    }
  }
}
"""

r = requests.post(
    API,
    json={"query": QUERY, "variables": {"login": USERNAME}},
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
    },
    timeout=30,
)
r.raise_for_status()
payload = r.json()

if payload.get("errors"):
    raise SystemExit("GitHub GraphQL error: " + str(payload["errors"]))

user = payload.get("data", {}).get("user")
if not user:
    raise SystemExit(f"GitHub user not found: {USERNAME}")

calendar = user["contributionsCollection"]["contributionCalendar"]
weeks = calendar["weeks"]

# GitHub's contribution calendar is a 7-row by ~53-column grid.
# x = week, y = weekday. The API gives weekday explicitly.
grid = {}
for x, week in enumerate(weeks):
    for day in week["contributionDays"]:
        grid[(x, (int(day["weekday"]) - 1))] = day

max_x = len(weeks) - 1
occupied = {
    pos for pos, day in grid.items()
    if day["contributionCount"] > 0
}
empty = {
    pos for pos in grid
    if pos not in occupied
}

# Find connected components among ZERO-contribution cells.
def neighbors(p):
    x, y = p
    for q in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)):
        if q in empty:
            yield q

components = []
remaining = set(empty)
while remaining:
    start = next(iter(remaining))
    comp = {start}
    dq = deque([start])
    remaining.remove(start)
    while dq:
        p = dq.popleft()
        for q in neighbors(p):
            if q in remaining:
                remaining.remove(q)
                comp.add(q)
                dq.append(q)
    components.append(comp)

if not components:
    raise SystemExit("No empty contribution cells were found.")

# Use the largest empty region. This guarantees every snake position is a
# zero-contribution cell, even if contribution cells split the grid.
component = max(components, key=len)

# Build a long walk through the component. A DFS traversal may revisit cells,
# which is fine: the snake remains entirely inside empty cells.
start = min(component, key=lambda p: (p[0], p[1]))
walk = []
visited = set()

def dfs(p):
    visited.add(p)
    walk.append(p)
    # Prefer moves that keep us away from dead ends.
    opts = [q for q in neighbors(p) if q not in visited and q in component]
    opts.sort(key=lambda q: sum(1 for z in neighbors(q) if z not in visited))
    for q in opts:
        dfs(q)
        # Return to p through the same empty-cell corridor.
        walk.append(p)

dfs(start)

# If the component is very large, keep the animation compact while still
# preserving the property that every point is an empty cell.
# We don't remove points; the SVG animation simply uses the generated walk.

CELL = 16
GAP = 4
STEP = CELL + GAP
MARGIN = 10
WIDTH = len(weeks) * STEP + MARGIN * 2
HEIGHT = 7 * STEP + MARGIN * 2

def center(pos):
    x, y = pos
    return MARGIN + x * STEP + CELL / 2, MARGIN + y * STEP + CELL / 2

# SVG path: every segment joins adjacent empty cells.
path_d = []
for i, pos in enumerate(walk):
    cx, cy = center(pos)
    path_d.append(("M" if i == 0 else "L") + f"{cx:.1f},{cy:.1f}")
path_d = " ".join(path_d)

# Duration is based on the number of moves, capped for profile readability.
duration = max(12, min(45, len(walk) * 0.07))

# Draw contribution cells using GitHub's actual API colors. The zero level is
# drawn as a subtle empty square; non-zero cells remain completely untouched
# by the snake path.
svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="GitHub contributions with a snake moving only through empty cells">',
    '<style>',
    '.cell{shape-rendering:geometricPrecision}',
    '.snake{filter:url(#shadow)}',
    '</style>',
    '<defs>',
    '<filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">',
    '<feDropShadow dx="0" dy="1" stdDeviation="1" flood-opacity=".25"/>',
    '</filter>',
    '</defs>',
    '<rect width="100%" height="100%" fill="transparent"/>',
]

for (x, y), day in sorted(grid.items()):
    cx = MARGIN + x * STEP
    cy = MARGIN + y * STEP
    color = day["color"] if day["contributionCount"] > 0 else "#ebedf0"
    svg.append(
        f'<rect class="cell" x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" '
        f'rx="3" fill="{html.escape(color)}">'
        f'<title>{html.escape(day["date"])}: {day["contributionCount"]} contributions</title>'
        '</rect>'
    )

# Invisible motion path. The visible body is a set of circles following it.
svg.append(f'<path id="snakePath" d="{path_d}" fill="none" stroke="none"/>')

# Body circles. Each follows the exact same empty-cell-only path with an offset.
body_count = 7
for i in range(body_count, 0, -1):
    radius = 4.8 if i == body_count else 4.0
    color = "#ff6b35" if i == body_count else "#ff8c5a"
    delay = -(i * duration / (body_count + 2))
    svg.append(
        f'<circle class="snake" r="{radius}" fill="{color}">'
        f'<animateMotion dur="{duration:.2f}s" repeatCount="indefinite" '
        f'begin="{delay:.2f}s" rotate="auto">'
        '<mpath href="#snakePath"/>'
        '</animateMotion>'
        '</circle>'
    )

# Head marker.
svg.append(
    f'<circle r="6" fill="#ff5a36" stroke="#ffffff" stroke-width="1.5" class="snake">'
    f'<animateMotion dur="{duration:.2f}s" repeatCount="indefinite" rotate="auto">'
    '<mpath href="#snakePath"/>'
    '</animateMotion>'
    '</circle>'
)

svg.append("</svg>")

out = os.environ.get("OUTPUT", "dist/empty-snake.svg")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(svg))

print(f"Generated {out}")
print(f"Empty-cell component: {len(component)} cells")
print(f"Animation path points: {len(walk)}")

