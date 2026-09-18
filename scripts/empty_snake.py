#!/usr/bin/env python3
"""Generate a polished SVG snake that travels only through zero-contribution cells."""
import os, html
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

# GitHub weekday is 0=Sunday ... 6=Saturday.
grid = {}
for x, week in enumerate(weeks):
    for day in week["contributionDays"]:
        grid[(x, int(day["weekday"]))] = day

occupied = {p for p, d in grid.items() if d["contributionCount"] > 0}
empty = set(grid) - occupied

def neighbors(p):
    x, y = p
    for q in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
        if q in empty:
            yield q

# Select the largest connected region of empty cells.
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

# Depth-first traversal through empty cells only.
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

duration = max(14, min(42, len(walk) * 0.06))

svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="GitHub contribution snake animation">',
    """<style>
      .cell{shape-rendering:geometricPrecision}
      .snake{filter:url(#snakeShadow)}
      .eye{fill:#fff}
      .pupil{fill:#111}
    </style>""",
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
      <filter id="snakeShadow" x="-100%" y="-100%" width="300%" height="300%">
        <feDropShadow dx="0" dy="1.5" stdDeviation="1.4" flood-opacity=".35"/>
      </filter>
      <filter id="glow" x="-100%" y="-100%" width="300%" height="300%">
        <feGaussianBlur stdDeviation="1.6" result="blur"/>
        <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>""",
    '<rect width="100%" height="100%" fill="transparent"/>',
]

# Preserve the real contribution colors. Empty cells stay neutral.
for (x, y), day in sorted(grid.items()):
    px = MARGIN + x * STEP
    py = MARGIN + y * STEP
    color = day["color"] if day["contributionCount"] > 0 else "#0d1117"
    svg.append(
        f'<rect class="cell" x="{px}" y="{py}" width="{CELL}" height="{CELL}" rx="3" fill="{html.escape(color)}">'
        f'<title>{html.escape(day["date"])}: {day["contributionCount"]} contributions</title></rect>'
    )

svg.append(f'<path id="snakePath" d="{path_d}" fill="none" stroke="none"/>')

# Continuous snake body: one moving stroke, not separate moving dots.
snake_length = min(180, max(70, len(walk) * 0.18))
svg.append(f'''
<g class="snake" filter="url(#glow)">
  <path d="{path_d}" fill="none" stroke="url(#snakeGradient)" stroke-width="7"
        stroke-linecap="round" stroke-linejoin="round"
        stroke-dasharray="{snake_length} 10000">
    <animate attributeName="stroke-dashoffset"
             from="0" to="-{max(1, len(walk))*STEP}"
             dur="{duration:.2f}s" repeatCount="indefinite"/>
  </path>
  <circle r="6.5" fill="url(#headGradient)" stroke="#ffffff" stroke-width="1.1">
    <animateMotion dur="{duration:.2f}s" repeatCount="indefinite" rotate="auto">
      <mpath href="#snakePath"/>
    </animateMotion>
  </circle>
</g>
''')

svg.append("</svg>")

out = os.environ.get("OUTPUT", "dist/empty-snake.svg")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(svg))

print(f"Generated {out}")
print(f"Zero-contribution cells in selected region: {len(component)}")
print(f"Animation path points: {len(walk)}")
