# Custom empty-cell contribution snake by Rahul Sahane.
# Feel free to copy and customize this generator; please keep the credit.
#!/usr/bin/env python3
"""Generate a simple dark GitHub contribution-grid snake.

The snake is exactly four small blocks and moves cell-by-cell through
zero-contribution cells only. Contribution cells are never part of its route.
"""
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

# IMPORTANT: the snake can use only zero-contribution cells.
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


# Find the largest connected region of empty cells.
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

# Route through all empty-cell components.
# Contribution cells are never crossed. Between disconnected empty regions,
# the snake leaves the grid and re-enters from outside.
remaining = set(empty)
walk = []

while remaining:
    start = min(remaining, key=lambda p: (p[0], p[1]))
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

    visited = set()
    component_walk = []

    def dfs(p):
        visited.add(p)
        component_walk.append(p)
        options = [n for n in neighbors(p) if n in component and n not in visited]
        options.sort(key=lambda n: sum(1 for z in neighbors(n) if z not in visited))
        for n in options:
            dfs(n)
            component_walk.append(p)

    dfs(start)

    if walk:
        last = walk[-1]
        first = component_walk[0]
        walk.extend([(last[0], -1), (first[0], -1)])

    walk.extend(component_walk)

if not walk:
    raise SystemExit("No zero-contribution cells found.")

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
    return (
        MARGIN_X + x * STEP + CELL / 2,
        MARGIN_Y + y * STEP + CELL / 2,
    )


# SVG motion path. Every point is an empty contribution cell.
path_d = " ".join(
    ("M" if i == 0 else "L")
    + f"{center(p)[0]:.1f},{center(p)[1]:.1f}"
    for i, p in enumerate(walk)
)

# Keep the speed calm: one grid-cell step is visually clear.
duration = max(24, min(55, len(walk) * 0.10))

svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
    'role="img" aria-label="Four-block dark GitHub contribution snake">',
    f'<rect width="100%" height="100%" rx="10" fill="{BG}"/>',
    f'<rect x="1" y="1" width="{WIDTH - 2}" height="{HEIGHT - 2}" rx="10" '
    f'fill="none" stroke="{BORDER}" stroke-width="1"/>',
]

# Draw the GitHub-style grid.
for (x, y), day in sorted(grid.items()):
    px = MARGIN_X + x * STEP
    py = MARGIN_Y + y * STEP

    # Green cells are real contributions.
    # Dark cells are empty and are the ONLY cells used by the snake.
    color = day["color"] if day["contributionCount"] > 0 else EMPTY

    svg.append(
        f'<rect x="{px}" y="{py}" width="{CELL}" height="{CELL}" rx="3" '
        f'fill="{html.escape(color)}">'
        f'<title>{html.escape(day["date"])}: '
        f'{day["contributionCount"]} contributions</title></rect>'
    )

# Hidden path used only for motion.
svg.append(f'<path id="snakePath" d="{path_d}" fill="none" stroke="none"/>')

# EXACTLY FOUR small blocks — the first animation style.
# No second animation, trail, glow, or gradient.
block_size = 13
one_cell_delay = duration / max(1, len(walk) - 1)
body_delays = [0.0, one_cell_delay, 2 * one_cell_delay, 3 * one_cell_delay]

svg.append('<g aria-label="four block snake">')

for i, delay in enumerate(body_delays):
    fill = "#a855f7" if i == 3 else "#d946ef"
    block = (
        f'<rect x="{-block_size/2:.1f}" y="{-block_size/2:.1f}" '
        f'width="{block_size}" height="{block_size}" rx="3" fill="{fill}"/>'
    )

    svg.append(
        f'''
        <g>
          {block}
          <animateMotion dur="{duration:.2f}s" repeatCount="indefinite"
                         rotate="0" calcMode="linear"
                         begin="{delay:.2f}s">
            <mpath href="#snakePath"/>
          </animateMotion>
        </g>
        '''
    )

# The head eyes are part of the same first animation.
svg.append(
    f'''
    <g>
      <circle cx="-3.2" cy="-2.0" r="1.25" fill="#ffffff"/>
      <circle cx="3.2" cy="-2.0" r="1.25" fill="#ffffff"/>
      <animateMotion dur="{duration:.2f}s" repeatCount="indefinite"
                     rotate="0" calcMode="linear">
        <mpath href="#snakePath"/>
      </animateMotion>
    </g>
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
