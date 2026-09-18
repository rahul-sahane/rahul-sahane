#!/usr/bin/env python3
"""Generate a dark GitHub contribution-grid snake that travels only through empty cells."""
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
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
    },
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

# The snake is allowed to occupy ONLY cells with zero contributions.
occupied = {
    p for p, day in grid.items()
    if day["contributionCount"] > 0
}
empty = set(grid) - occupied


def neighbors(p):
    x, y = p
    for q in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
        if q in empty:
            yield q


# Find the largest connected empty area so the snake has plenty of room.
components = []
remaining = set(empty)

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

# Build a long path using empty cells only.
start = min(component, key=lambda p: (p[0], p[1]))
walk = []
visited = set()


def dfs(p):
    visited.add(p)
    walk.append(p)

    options = [
        n for n in neighbors(p)
        if n in component and n not in visited
    ]

    # Prefer cells with fewer exits to make the route look less random.
    options.sort(
        key=lambda n: sum(1 for z in neighbors(n) if z not in visited)
    )

    for n in options:
        dfs(n)
        # Return through the same empty cell; never crosses a contribution cell.
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
PANEL = "#0d1117"
EMPTY = "#161b22"
BORDER = "#30363d"


def center(pos):
    x, y = pos
    return (
        MARGIN_X + x * STEP + CELL / 2,
        MARGIN_Y + y * STEP + CELL / 2,
    )


path_d = " ".join(
    ("M" if i == 0 else "L")
    + f"{center(p)[0]:.1f},{center(p)[1]:.1f}"
    for i, p in enumerate(walk)
)

duration = max(18, min(48, len(walk) * 0.07))

svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
    'role="img" aria-label="Animated dark GitHub contribution snake">',
    """<style>
      .cell { shape-rendering: geometricPrecision; }
      .snake-body {
        filter: url(#snakeGlow);
      }
    </style>""",
    """<defs>
      <linearGradient id="snakeGradient" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#a855f7"/>
        <stop offset="45%" stop-color="#d946ef"/>
        <stop offset="100%" stop-color="#f43f5e"/>
      </linearGradient>

      <linearGradient id="headGradient" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#c026d3"/>
        <stop offset="55%" stop-color="#e879f9"/>
        <stop offset="100%" stop-color="#fb7185"/>
      </linearGradient>

      <filter id="snakeGlow" x="-100%" y="-100%" width="300%" height="300%">
        <feGaussianBlur stdDeviation="2.2" result="blur"/>
        <feMerge>
          <feMergeNode in="blur"/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>

      <filter id="headShadow" x="-100%" y="-100%" width="300%" height="300%">
        <feDropShadow dx="0" dy="1.5" stdDeviation="1.6" flood-opacity=".45"/>
      </filter>
    </defs>""",
    f'<rect width="100%" height="100%" rx="10" fill="{BG}"/>',
    f'<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" rx="10" '
    f'fill="{PANEL}" stroke="{BORDER}" stroke-width="1"/>',
]

# Draw the contribution calendar.
for (x, y), day in sorted(grid.items()):
    px = MARGIN_X + x * STEP
    py = MARGIN_Y + y * STEP

    # Real contribution cells keep GitHub's own green shade.
    # Zero-contribution cells remain dark and are the only cells the snake uses.
    color = day["color"] if day["contributionCount"] > 0 else EMPTY

    svg.append(
        f'<rect class="cell" x="{px}" y="{py}" width="{CELL}" height="{CELL}" rx="3" '
        f'fill="{html.escape(color)}">'
        f'<title>{html.escape(day["date"])}: '
        f'{day["contributionCount"]} contributions</title></rect>'
    )

# Invisible motion path used by the snake head.
svg.append(
    f'<path id="snakePath" d="{path_d}" fill="none" stroke="none" pathLength="1000"/>'
)

# One continuous body: a moving dash on a single SVG path.
# This intentionally avoids the old "many moving dots" look.
body_length = min(95, max(52, len(walk) * 0.11))

svg.append(
    f'''
<g class="snake-body">
  <path d="{path_d}" fill="none" stroke="url(#snakeGradient)"
        stroke-width="11" stroke-linecap="round" stroke-linejoin="round"
        pathLength="1000" stroke-dasharray="{body_length} 1000"
        stroke-dashoffset="0">
    <animate attributeName="stroke-dashoffset"
             from="0" to="-1000"
             dur="{duration:.2f}s" repeatCount="indefinite"/>
  </path>

  <!-- Square head, matching the block-like snake style. -->
  <rect x="-7" y="-7" width="14" height="14" rx="3.5"
        fill="url(#headGradient)" stroke="#f5d0fe" stroke-width="1"
        filter="url(#headShadow)">
    <animateMotion dur="{duration:.2f}s" repeatCount="indefinite" rotate="auto">
      <mpath href="#snakePath"/>
    </animateMotion>
  </rect>
</g>
'''
)

svg.append("</svg>")

out = os.environ.get("OUTPUT", "dist/empty-snake.svg")
os.makedirs(os.path.dirname(out), exist_ok=True)

with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(svg))

print(f"Generated {out}")
print(f"Zero-contribution cells in selected region: {len(component)}")
print(f"Animation path points: {len(walk)}")
