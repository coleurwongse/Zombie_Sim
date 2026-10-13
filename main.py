import argparse
import random

import numpy as np
import pygame

import render
import war
import sim
from sim import World

parser = argparse.ArgumentParser(description="Zombie infection simulator")
parser.add_argument("map", nargs="?", default="maps/world")
parser.add_argument("--seed", type=int, default=None, help="random seed (default: a new one every run)")
parser.add_argument("--war", action="store_true", help="nations 1 and 2 start out at war")
parser.add_argument("--deterministic", action="store_true", help="no randomness: same map -> same run")
parser.add_argument("--no-nukes", action="store_true", help="nobody uses nuclear weapons")
parser.add_argument("--no-civil-war", action="store_true", help="regions that break away are let go peacefully")
parser.add_argument("--outbreak", default=None, metavar="CITY",
                    help="start the outbreak in this city instead (e.g. \"New York\", Berlin, Lagos)")
parser.add_argument("--virulence", type=float, default=1.4,
                    help="how fast zombies bite (1.25 = it usually stays in Asia, 1.75 = the world falls)")
args = parser.parse_args()
MAP_FOLDER = args.map
PANEL = 520
LOG_LINES = 14

mode = 4
show_text = True
done = False
paused = False
steps_per_frame = 1
scroll = 0                       # first row of the country list shown

pygame.init()
_info = pygame.display.Info()
DESKTOP = (_info.current_w or 1600, _info.current_h or 900)
# a big window to start with (resizable: drag its edges, or F11 / F for full screen)
WINDOWED = (max(1000, int(DESKTOP[0] * 0.92)), max(700, int(DESKTOP[1] * 0.85)))
fullscreen = False
screen = pygame.display.set_mode(WINDOWED, pygame.RESIZABLE)
SCREEN_W, SCREEN_H = screen.get_size()
VIEW_W, VIEW_H = SCREEN_W - PANEL, SCREEN_H
FIT = 1.0
pygame.display.set_caption("Zombie Infection Simulator")
font = pygame.font.Font(None, 24)
small = pygame.font.Font(None, 19)
clock = pygame.time.Clock()


def start_outbreak(w, city):
    """Patient zero in `city` (a city on the map, by name) instead of the map's own outbreak."""
    import unicodedata

    def plain(text):                             # "Sao Paulo" finds São Paulo
        return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).lower()
    match = ([c for c in w.cities if plain(c[0]) == plain(city)]
             or [c for c in w.cities if plain(city) in plain(c[0])])
    if not match:
        raise SystemExit(f"no city called {city!r} on this map")
    name, r, c, _ = max(match, key=lambda c: c[3])
    w.Z[:] = 0
    w.Z[r, c] = 40
    w.Z[r, (c + 1) % w.cols] = 25
    owner = w.civs[w.O[r, c]]
    for civ in w.civs:                           # (a cover-up belongs to where the outbreak started)
        if civ is not owner:
            civ.traits.pop("denial", None)
    w.note(f"the outbreak starts in {name}")


def new_world():
    seed = args.seed if args.seed is not None else random.randrange(10 ** 6)
    w = World.from_folder(MAP_FOLDER, seed=seed, stochastic=not args.deterministic)
    w.nukes_allowed = not args.no_nukes
    w.civil_wars = not args.no_civil_war
    w.virulence = args.virulence
    if args.outbreak:
        start_outbreak(w, args.outbreak)
    if args.war and len(w.civs) > 2:
        war.declare(w, 1, 2, "already at war")
    pygame.display.set_caption(f"Zombie Infection Simulator - {MAP_FOLDER} - seed {seed}")
    return w


world = new_world()
rows, cols = world.H.shape
cx, cy = cols / 2.0, rows / 2.0  # map point at the centre of the view


def layout(size):
    """The window was opened or resized: the map view takes all but the panel; whole map fits at the lowest zoom."""
    global SCREEN_W, SCREEN_H, VIEW_W, VIEW_H, FIT
    SCREEN_W, SCREEN_H = max(size[0], PANEL + 200), max(size[1], 400)
    VIEW_W, VIEW_H = SCREEN_W - PANEL, SCREEN_H
    FIT = min(VIEW_W / cols, VIEW_H / rows)      # (fractional pixels are fine: the map is scaled)


def toggle_fullscreen():
    global screen, fullscreen, zoom
    fullscreen = not fullscreen
    if fullscreen:
        screen = pygame.display.set_mode(DESKTOP, pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode(WINDOWED, pygame.RESIZABLE)
    layout(screen.get_size())
    zoom = max(FIT, zoom)
    clamp_view()


layout(screen.get_size())
zoom = FIT                       # screen pixels per tile


def clamp_view():
    global cx, cy
    half_w, half_h = VIEW_W / zoom / 2, VIEW_H / zoom / 2
    cy = min(max(cy, min(half_h, rows / 2)), max(rows - half_h, rows / 2))
    if not world.wrap:
        cx = min(max(cx, min(half_w, cols / 2)), max(cols - half_w, cols / 2))
    else:
        cx %= cols


def screen_to_tile(px, py):
    j = cx + (px - VIEW_W / 2) / zoom
    i = cy + (py - VIEW_H / 2) / zoom
    if world.wrap:
        j %= cols
    return int(np.floor(i)), int(np.floor(j))


GOV_TAG = {"national": "", "junta": "J", "democracy": "R", "warlord": "W", "tribal": "C"}
ACT = {"quarantine": "Q", "retreat": "Rt", "fortify": "F", "purge": "P", "evacuate": "E", "reclaim": "Rc",
       "offensive": "O", "ignore": "-"}


def hud():
    global scroll
    x0 = VIEW_W
    pygame.draw.rect(screen, (20, 20, 28), (x0, 0, PANEL, SCREEN_H))
    x, y = x0 + 10, 6
    d = world.date
    head = f"{d.month:02d}/{d.day:02d}/{d.year}   (day {world.ticks})   x{steps_per_frame}" + ("  PAUSED" if paused else "")
    screen.blit(font.render(head, True, (255, 255, 255)), (x, y)); y += 22
    pop_line = (f"humans {sim.fmt_people(world.shown(world.H))}   zombies {sim.fmt_people(world.shown(world.Z))}   "
                f"shipping {int(100 * world.trade_index)}%   world alarm {int(100 * world.alarm)}%")
    screen.blit(small.render(pop_line, True, (220, 220, 230)), (x, y)); y += 17
    P = world.people                                   # (people moved today, at the map's real-population scale)
    riot = getattr(world, "riot", None)
    rioting = sim.fmt_people(world.shown(world.H, riot)) if riot is not None and riot.any() else "0"
    sub = (f"rioting {rioting}  fleeing {P(world.last_panic)}  evac {P(world.last_evac)}  "
           f"refugees {P(world.last_refugees)}  by boat {P(world.last_boats)}")
    sub2 = (f"resettled {P(getattr(world, 'last_resettled', 0))}  settlers {P(getattr(world, 'last_settlers', 0))}"
            f"  wars {len(world.wars)}  {'aid' if getattr(world, 'alliance_of', None) else 'UN'} missions "
            f"{len(getattr(world, 'missions', []))}"
            + (f"  nukes {getattr(world, 'nuclear_strikes', 0)}" if getattr(world, "nuclear_strikes", 0) else ""))
    screen.blit(small.render(sub, True, (170, 170, 185)), (x, y)); y += 16
    screen.blit(small.render(sub2, True, (170, 170, 185)), (x, y)); y += 18
    cols_txt = "country                      pop    mor army  forts  doing"
    screen.blit(small.render(cols_txt, True, (140, 140, 160)), (x + 14, y)); y += 16
    pygame.draw.line(screen, (70, 70, 90), (x, y), (x + PANEL - 20, y)); y += 3

    summary = world.summary()
    live = [r for r in summary if not r["collapsed"]]
    # importance: people first, then army
    live.sort(key=lambda r: -(r["shown"] + 2000 * r["military"] * world.pop_scale))
    fallen = [r for r in summary if r["collapsed"]]
    list_top = y
    list_bottom = SCREEN_H - LOG_LINES * 15 - 30
    per_row = 15
    visible = max(1, (list_bottom - list_top) // per_row)
    scroll = max(0, min(scroll, max(0, len(live) - visible)))
    for r in live[scroll:scroll + visible]:
        col = render.civ_color(r["id"])
        pygame.draw.rect(screen, col, (x, y + 3, 9, 9))
        name = r["name"][:21] + ("*" if r["successor"] else "")
        gov = GOV_TAG.get(r["gov"], "")
        flags = ("W" if r["at_war"] else "") + ("Q" if r["closed"] else "") + ("p" if r["peace"] else "")
        acts = "+".join(ACT.get(a, a) for a in r["action"].split("+"))
        txt = small.render(f"{name}", True, (255, 255, 255) if r["morale"] > 3 else (255, 150, 150))
        screen.blit(txt, (x + 14, y))
        stats = f"{gov:1s} {sim.fmt_people(r['shown']):>7s}  {r['morale']:2d}  {r['military']:.2f}  {r['sites']:3d}  {acts}"
        screen.blit(small.render(stats, True, (190, 190, 205)), (x + 175, y))
        if flags:
            screen.blit(small.render(flags, True, (255, 170, 60)), (x + PANEL - 30, y))
        y += per_row
    more = f"{scroll + 1}-{min(len(live), scroll + visible)} of {len(live)} governments (wheel / PgUp PgDn)"
    screen.blit(small.render(more, True, (130, 130, 150)), (x, list_bottom + 1))
    y = list_bottom + 15
    if fallen:
        names = ", ".join(r["name"] + (f" ({r['sites']} garrisons)" if r["sites"] else "") for r in fallen[-3:])
        screen.blit(small.render(("fallen: " + names)[:80], True, (200, 120, 120)), (x, y))
    y += 15
    pygame.draw.line(screen, (70, 70, 90), (x, y), (x + PANEL - 20, y)); y += 3
    rows_ = []                                          # newest last; long messages wrap onto further lines
    for tick, text in reversed(list(world.events)[-LOG_LINES:]):
        d = world.start_date.fromordinal(world.start_date.toordinal() + tick)
        lines = wrap(f"{d.month:02d}/{d.day:02d}/{d.year % 100:02d} {text}", PANEL - 24, small, indent="      ")
        if len(rows_) + len(lines) > LOG_LINES and rows_:
            break
        rows_[:0] = lines
    for line in rows_[-LOG_LINES:]:
        screen.blit(small.render(line, True, (210, 210, 130)), (x, y))
        y += 15


def wrap(text, width, fnt, indent=""):
    """`text` broken into lines no wider than `width` pixels (at word boundaries; continuation lines indented)."""
    lines, cur = [], ""
    for word in text.split(" "):
        trial = word if not cur else cur + " " + word
        if fnt.size(trial)[0] <= width or not cur.strip():
            cur = trial
        else:
            lines.append(cur)
            cur = indent + word
    if cur:
        lines.append(cur)
    return lines


_frame = {}


def draw():
    key = (id(world), world.ticks, mode)                # (the map only changes when the world does)
    if _frame.get("key") != key:
        _frame["key"], _frame["rgb"] = key, render.render_rgb(world, mode)
    rgb = _frame["rgb"]
    # the part of the map in view
    half_w, half_h = VIEW_W / zoom / 2, VIEW_H / zoom / 2
    r0 = int(np.floor(cy - half_h)); r1 = int(np.ceil(cy + half_h)) + 1
    c0 = int(np.floor(cx - half_w)); c1 = int(np.ceil(cx + half_w)) + 1
    r0, r1 = max(r0, 0), min(r1, rows)             # nothing above / below the map
    if not world.wrap:
        c0, c1 = max(c0, 0), min(c1, cols)
    rr = np.arange(r0, r1)
    cc = np.arange(c0, c1)
    cc = cc % cols if world.wrap else np.clip(cc, 0, cols - 1)
    sub = rgb[rr][:, cc]
    surface = pygame.surfarray.make_surface(np.ascontiguousarray(sub.swapaxes(0, 1)))
    w, h = int(round(sub.shape[1] * zoom)), int(round(sub.shape[0] * zoom))
    surface = pygame.transform.scale(surface, (w, h))
    screen.fill((0, 0, 0))
    ox = int(round((c0 - (cx - half_w)) * zoom))
    oy = int(round((r0 - (cy - half_h)) * zoom))
    screen.blit(surface, (ox, oy))
    if show_text:
        mx, my = pygame.mouse.get_pos()
        if mx < VIEW_W:
            i, j = screen_to_tile(mx, my)
            if 0 <= i < rows and 0 <= j < cols:
                text = render.describe(world, i, j)
                img = small.render(text, True, (255, 255, 255))
                pygame.draw.rect(screen, (0, 0, 0), (4, VIEW_H - 24, img.get_width() + 8, 20))
                screen.blit(img, (8, VIEW_H - 21))
    hud()
    pygame.display.update()


dragging = None
while not done:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            done = True
        elif event.type == pygame.VIDEORESIZE and not fullscreen:
            WINDOWED = (event.w, event.h)
            screen = pygame.display.set_mode(WINDOWED, pygame.RESIZABLE)
            layout(WINDOWED)
            zoom = max(FIT, zoom)
            clamp_view()
        elif event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if mx >= VIEW_W:
                scroll -= 3 * event.y
            else:                                   # zoom about the cursor
                bi, bj = cy + (my - VIEW_H / 2) / zoom, cx + (mx - VIEW_W / 2) / zoom
                zoom = min(24.0, max(FIT, zoom * (1.25 ** event.y)))
                cy, cx = bi - (my - VIEW_H / 2) / zoom, bj - (mx - VIEW_W / 2) / zoom
                clamp_view()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (2, 3):
            dragging = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button in (2, 3):
            dragging = None
        elif event.type == pygame.MOUSEMOTION and dragging:
            dx, dy = event.pos[0] - dragging[0], event.pos[1] - dragging[1]
            cx -= dx / zoom
            cy -= dy / zoom
            dragging = event.pos
            clamp_view()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_1:
                mode = 1
            elif event.key == pygame.K_2:
                mode = 2
            elif event.key == pygame.K_3:
                mode = 4
            elif event.key == pygame.K_4:
                mode = 3
            elif event.key in (pygame.K_F11, pygame.K_f):
                toggle_fullscreen()
            elif event.key == pygame.K_ESCAPE and fullscreen:
                toggle_fullscreen()
            elif event.key == pygame.K_t:
                show_text = not show_text
            elif event.key == pygame.K_SPACE:
                paused = not paused
            elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                steps_per_frame = min(steps_per_frame * 2, 16)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                steps_per_frame = max(steps_per_frame // 2, 1)
            elif event.key == pygame.K_PAGEDOWN:
                scroll += 20
            elif event.key == pygame.K_PAGEUP:
                scroll -= 20
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                cx -= 40 / zoom; clamp_view()
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                cx += 40 / zoom; clamp_view()
            elif event.key in (pygame.K_UP, pygame.K_w):
                cy -= 40 / zoom; clamp_view()
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                cy += 40 / zoom; clamp_view()
            elif event.key == pygame.K_HOME:
                zoom, cx, cy = FIT, cols / 2.0, rows / 2.0
            elif event.key == pygame.K_r:
                world = new_world()
    draw()
    if not paused:
        for _ in range(steps_per_frame):
            world.tick()
    clock.tick(60)

pygame.quit()
