#!/usr/bin/env python3
"""Generate a dark GitHub contribution-grid snake using four close blocks."""
import os
import html
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

# GitHub weekday: 0=Sunday ... 6=Saturday.
grid = {}
for x, week in enumerate(weeks):
    for day in week["contributionDays"]:
        grid[(x, int(day["weekday"]))] = day

# The snake may ONLY occupy zero-contribution cells.
occupied = {p for p, d in grid.items() if d["contributionCount"] > 0}
empty = set(grid) - occupied


def neighbors(p):
    x, y = p
    for q in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
        if q in empty:
            yield q


# Find the largest connected empty region.
remaining = set(empty)
components = []
while remaining:
    start = next(iter(remaining))
    component = {start}
    queue = deque([start])
    remaining.remove(start)
    while queue:
        p = queue.popleft()
        for n in neighbors(p):
            if n in remaining:
                remaining.remove(n)
                component.add(n)
                queue.append(n)
    components.append(component)

if not components:
    raise SystemExit("No zero-contribution cells found.")

component = max(components, key=len)

# Build a long orthogonal route through empty cells only.
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
MARGIN_X = 12
MARGIN_Y = 24
WIDTH = len(weeks) * STEP + MARGIN_X * 2
HEIGHT = 7 * STEP + MARGIN_Y * 2
BG = "#0d1117"
EMPTY = "#161b22"
BORDER = "#30363d"


def center(pos):
    x, y = pos
    return MARGIN_X + x * STEP + CELL / 2, MARGIN_Y + y * STEP + CELL / 2


# The FIRST animation style: a single continuous moving dash on one path.
path_d = " ".join(
    ("M" if i == 0 else "L") + f"{center(p)[0]:.1f},{center(p)[1]:.1f}"
    for i, p in enumerate(walk)
)
duration = max(18, min(42, len(walk) * 0.06))

svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
    'role="img" aria-label="Dark GitHub contribution snake">',
    """<defs>
      <linearGradient id="snakeGradient" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#ff3d81"/>
        <stop offset="48%" stop-color="#ff6b35"/>
        <stop offset="100%" stop-color="#ffd166"/>
      </linearGradient>
      <linearGradient id="headGradient" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#ff2d75"/>
        <stop offset="55%" stop-color="#ff6b35"/>
        <stop offset="100%" stop-color="#ffb347"/>
      </linearGradient>
      <filter id="glow" x="-100%" y="-100%" width="300%" height="300%">
        <feGaussianBlur stdDeviation="1.6" result="blur"/>
        <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>""",
    f'<rect width="100%" height="100%" rx="10" fill="{BG}"/>',
]

for (x, y), day in sorted(grid.items()):
    px = MARGIN_X + x * STEP
    py = MARGIN_Y + y * STEP
    color = day["color"] if day["contributionCount"] > 0 else EMPTY
    svg.append(
        f'<rect x="{px}" y="{py}" width="{CELL}" height="{CELL}" rx="3" fill="{html.escape(color)}">'
        f'<title>{html.escape(day["date"])}: {day["contributionCount"]} contributions</title></rect>'
    )

svg.append(f'<path id="snakePath" d="{path_d}" fill="none" stroke="none"/>')

# Four small blocks, kept close together. This recreates the first animation
# style while avoiding the large-body version.
block_size = 11
close_delay = 0.10

svg.append('<g filter="url(#glow)" aria-label="four-block snake">')

for i in range(4):
    # 0 = head, 1..3 = close-following body blocks.
    fill = "#ff3d81" if i == 0 else "#ff6b35"
    delay = i * close_delay
    svg.append(
        f'''
        <rect x="{-block_size/2:.1f}" y="{-block_size/2:.1f}"
              width="{block_size}" height="{block_size}" rx="3"
              fill="{fill}">
          <animateMotion dur="{duration:.2f}s" repeatCount="indefinite"
                         calcMode="linear" begin="{delay:.2f}s">
            <mpath href="#snakePath"/>
          </animateMotion>
        </rect>
        '''
    )

svg.append("</g>")
svg.append("</svg>")

out = os.environ.get("OUTPUT", "dist/empty-snake.svg")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(svg))

print(f"Generated {out}")
print(f"Zero-contribution cells in selected region: {len(component)}")
print(f"Animation path points: {len(walk)}")
