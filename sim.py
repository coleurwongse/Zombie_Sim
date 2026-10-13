"""Simulation core (no pygame): the world, and one tick of everything - the per-tile rules (engine.py), the economy,
people, boats, governments and their decisions, wars, rebuilding.

Arrays (all int32, shape (rows, cols)):
    H humans, Z zombies, D defense, T terrain, O owner (civilization id)
"""
import datetime
import json
import os
import random
from collections import deque

import numpy as np

import mapio
import nukes
import boats
import economy
import engine
import fracture
import holdouts
import aid
import expeditions
import resolve
import settlers
import front
import peace
import people
import quarantine
import restart
import union
import zombies
import war
from civilization import Civilization, box_sum, round_sum, DIRECTIONS, _slices, MIL_START

UNORG = (1.3, 1.3)     # unowned land: casualties x, zombie movement into populated tiles x (see engine.py)
MAX_CIVS = 500
BIG = 10 ** 6
LAPSE = 0               # (off: it turns every national collapse into extinction) defenses on ungoverned land decay down to this unless a garrison holds them (0 = off) ...
LAPSE_EVERY = 10        # ... losing one level this often (a fallen country's walls crumble, they don't vanish)
OVERSEAS_REACH = 6      # away from the landmass of its capital a government only takes land this close to what it held
                        # at the start (an overseas territory doesn't annex the continent it sits on) ...
HOME_REACH = 25.0       # ... and on its own landmass, beyond that, only within this many degrees of its capital
GUARD_REACH = 3         # an emptied tile stays a government's land only within this many tiles (through its own land)
GUARD_EVERY = 3         # ... of tiles where its people live (checked this often); land that was always empty
                        # (wilderness: ice, tundra, deep desert) is the exception - it stays its land until zombies take it
ALARM_ZOMBIES = 2500    # the world takes notice once this many zombies are about (after any cover-up) ...
ALARM_RATE = 0.002      # ... and its alarm (0..1) rises this much a tick while they are, plus ALARM_FALL per fallen
ALARM_FALL = 0.02       # government; it fades by ALARM_FADE a tick once the zombies are (nearly) gone
ALARM_FADE = 0.001


def fmt_people(v):
    v = float(v)
    for div, suffix in ((1e9, "b"), (1e6, "m"), (1e3, "k")):
        if abs(v) >= div:
            return f"{v / div:.1f}{suffix}"
    return str(int(round(v)))


class World:
    def __init__(self, humans, zombies, defense, terrain, owner, airports, ai=True, seed=0,
                 stochastic=None, wars=(), meta=None):
        self.H = humans.astype(np.int32).copy()
        self.Z = zombies.astype(np.int32).copy()
        self.D = defense.astype(np.int32).copy()
        self.T = terrain.astype(np.int32).copy()
        self.O = owner.astype(np.int32).copy()
        self.airports = {k: list(v) for k, v in airports.items() if v}
        self.ai = ai                 # False = original rules only (used to check the port)
        self.civil_wars = True           # regions that break away may be fought for (war.py)
        self.nukes_allowed = True        # governments with nuclear weapons may use them (nukes.py)
        self.virulence = 1.0             # how fast zombies bite (engine.py): 1.5 = a much deadlier outbreak
        self._statics = None
        # stochastic=False: every run with the same map is identical (tests use that)
        self.stochastic = bool(ai if stochastic is None else stochastic) and ai
        self.seed = seed
        base = seed if self.stochastic else 0        # deterministic mode ignores the seed entirely
        self.rng = np.random.default_rng(base)
        self.pyrng = random.Random(base)
        # civs[0] is "nobody / anarchy"; civs[k] owns the tiles painted with k in owner.png
        self.civs = [Civilization(k, ai=ai, traits=self._traits() if k else None)
                     for k in range(int(self.O.max(initial=1)) + 1)]
        self.events = deque(maxlen=5000)          # (tick, text)
        self.closed = set()                      # civilizations with shut borders
        self.qfac = None
        self.wars = {}
        self.last_evac = 0
        self.last_hunt = 0
        self.last_owner = self.O.copy()          # who governed each tile most recently (to trace fragments)
        self.U = np.zeros(self.H.shape, dtype=np.float32)          # unrest per tile
        self.R = np.zeros(self.H.shape, dtype=np.float32)          # recent riots per tile
        self.riot = np.zeros(self.H.shape, dtype=bool)
        self.last_riots = 0
        self.last_panic = 0
        self.last_refugees = 0
        self.last_boats = 0
        self.trade_index = 1.0
        self.food_shipped = 0.0
        self.ticks = 0
        self._near_cache = {}
        self._near_tick = -1
        self.knowledge_current = 0
        self.knowledge_past = 0
        # map metadata (maps/<map>/meta.json, optional): wrap, names, cities, capitals ...
        meta = meta or {}
        self.meta = meta
        self.wrap = bool(meta.get("wrap", True))
        self.sea_min = int(meta.get("sea_min", 0)) if ai else 0
        self.cities = [(c["name"], int(c["row"]), int(c["col"]), float(c.get("pop", 0))) for c in meta.get("cities", [])]
        for k, name in meta.get("names", {}).items():
            if int(k) < len(self.civs):
                self.civs[int(k)].name = name
        for k, rc in meta.get("capitals", {}).items():
            if int(k) < len(self.civs):
                self.civs[int(k)].capital = (int(rc[0]), int(rc[1]))
        # armies (0..1 strength), warheads, forms of government, who broke away from whom (make_world.py)
        for k, s in meta.get("military", {}).items():
            if int(k) < len(self.civs):
                c = self.civs[int(k)]
                c.strength = float(s)
                c.military = MIL_START * (0.6 + 1.2 * float(s))     # peacetime army; strength = how fast it mobilizes
        for k, n in meta.get("nukes", {}).items():
            if int(k) < len(self.civs):
                self.civs[int(k)].nukes = int(n)
        for k, t in meta.get("traits", {}).items():
            if int(k) < len(self.civs):
                self.civs[int(k)].traits.update(t)
        for k, g in meta.get("governments", {}).items():
            if int(k) < len(self.civs):
                self.civs[int(k)].gov = g
        for k, parent in meta.get("parents", {}).items():
            if int(k) < len(self.civs) and int(parent) < len(self.civs):
                c = self.civs[int(k)]
                c.split_from, c.root, c.successor, c.founded = int(parent), self.civs[int(parent)].root, True, -10 ** 4
        self.ports = [(int(r), int(c), int(s)) for r, c, s in meta.get("ports", [])]
        self.alliance_of = {int(k): name for name, ids in meta.get("alliances", {}).items() for k in ids}
        self.rivals = {frozenset((int(a), int(b))) for a, b in meta.get("rivals", [])
                       if int(a) < len(self.civs) and int(b) < len(self.civs)}
        # the calendar: one tick is one day, starting today (or meta "start_date": "YYYY-MM-DD")
        sd = meta.get("start_date")
        self.start_date = datetime.date.fromisoformat(sd) if sd else datetime.date.today()
        self.resist = None
        self.line_prot = None
        self.front = None
        # how many people lived on each tile before the outbreak: where survivors rebuild to (restart.py)
        self.H0 = self.H.copy()
        # what one "person" on the map stands for when numbers are shown (meta "real_population": the people the map
        # stands for at the start - default: the world today); the simulation itself never uses this
        self.pop_scale = float(meta.get("real_population", 8.2e9)) / max(1.0, float(np.maximum(self.H, 0).sum()))
        # ... and per tile (meta "real_pops": each country's real population, spread over its people on the map -
        # a crowded country isn't shown with the head count of an empty one the same size)
        scale = np.full(len(self.civs) + 1, self.pop_scale)
        real = meta.get("real_pops")
        if real:
            on_map = np.bincount(self.O.ravel(), weights=np.maximum(self.H, 0).ravel(), minlength=len(scale))
            for k, p in real.items():
                k = int(k)
                if 0 < k < len(scale) and on_map[k] > 0 and p > 0:
                    scale[k] = float(p) / on_map[k]
        self.scale_map = scale[np.clip(self.O, 0, len(scale) - 1)].astype(np.float32)
        self.wild = self.H0 <= 10                         # land nobody lived on: no garrison needed to hold it
        self._guarded = None
        self.O0 = self.O.copy()
        self._near0 = None
        n0 = max(1, len(self.civs) - 1)
        self.pop_ref = max(1.0, float(np.maximum(self.H, 0).sum()) / n0)   # an average government's people (sizes are
                                                                           # judged against this, civilization.size)
        # standing garrisons at the start (meta "sites": civ, row, col, level, radius): fortresses like Minas Tirith
        for st in meta.get("sites", []):
            k, r, c = int(st["civ"]), int(st["row"]), int(st["col"])
            if not (0 < k < len(self.civs)):
                continue
            rad, lvl = int(st.get("radius", 1)), int(st.get("level", 7))
            if "tiles" in st:                                    # (a line of defences: Melian's Girdle ...)
                tiles = [(r, c)] + [(int(a), int(b)) for a, b in st["tiles"] if (int(a), int(b)) != (r, c)]
            else:
                tiles = [(rr, cc) for rr in range(max(r - rad, 0), min(self.rows, r + rad + 1))
                         for cc in range(max(c - rad, 0), min(self.cols, c + rad + 1))
                         if self.O[rr, cc] == k and self.H[rr, cc] > 10] or [(r, c)]
            for rc in tiles:
                self.D[rc] = max(self.D[rc], lvl)
            self.civs[k].sites.append(dict(center=(r, c), tiles=tiles, level=lvl, target=lvl, standing=True))
        if ai:
            self._settle_capitals()
            for c in self.civs[1:]:
                c.peace, c.emergencies = True, 0  # peacetime until the zombies show up (peace.py)
        self.alarm = 0.0                 # how alarmed the whole world is (0..1): everyone mobilizes a little,
        self.fallen_seen = 0             # flights between countries stop (front.py, engine._airports)

    @classmethod
    def from_folder(cls, folder, **kw):
        kw.setdefault("meta", mapio.load_meta(folder))
        w = cls(*mapio.load_map(folder), **kw)
        path = os.path.join(folder, "wars.json")          # optional: [[1, 2], ...] nations already at war
        wars = list(w.meta.get("wars", []))
        if os.path.exists(path):
            with open(path) as f:
                wars += json.load(f)
        if w.ai:
            for a, b in wars:
                if a < len(w.civs) and b < len(w.civs):
                    civil = w.civs[b].split_from == a or w.civs[a].split_from == b
                    war.declare(w, a, b, "civil war" if civil else "already at war", quiet=True, civil=civil)
        return w

    @property
    def date(self):
        """Today's date in the simulation (one tick = one day)."""
        return self.start_date + datetime.timedelta(days=self.ticks)

    def people(self, n):
        """A head count as shown on screen: scaled to the real population, 950, 12.3k, 4.5m, 1.2b."""
        return fmt_people(n * self.pop_scale)

    def shown(self, a, mask=None):
        """Real-world head count of map counts `a` (people or zombies) - each tile at its own country's scale."""
        s = getattr(self, "scale_map", None)
        if s is None:
            return float(np.sum(a if mask is None else a[mask])) * self.pop_scale
        return float(np.sum((a * s) if mask is None else (a * s)[mask]))

    def datestr(self, tick=None):
        d = self.start_date + datetime.timedelta(days=self.ticks if tick is None else tick)
        return f"{d.month:02d}/{d.day:02d}/{d.year}"

    # ------------------------------------------------------------ randomness helpers
    def _traits(self):
        if not self.stochastic:
            return {"caution": 1.0, "aggression": 1.0}
        return {"caution": self.pyrng.uniform(0.75, 1.25), "aggression": self.pyrng.uniform(0.7, 1.3)}

    def jitter(self, scale):
        """1 +- scale (uniform) in stochastic mode, exactly 1 otherwise."""
        return 1.0 + scale * (2.0 * self.pyrng.random() - 1.0) if self.stochastic else 1.0

    def noise(self, sigma):
        return self.pyrng.gauss(0.0, sigma) if self.stochastic else 0.0

    def note(self, text):
        self.events.append((self.ticks, text))

    def add_civ(self, morale=8, name=None):
        if len(self.civs) >= MAX_CIVS:
            return None
        civ = Civilization(len(self.civs), morale=morale, name=name, ai=self.ai, traits=self._traits())
        self.civs.append(civ)
        return civ

    def save(self, folder):
        mapio.save_map(folder, self.H, self.Z, self.D, self.T, self.O, self.airports)

    @property
    def statics(self):
        """Terrain-only facts (land mask, distance to land at sea, ...), worked out once (engine.Statics)."""
        if self._statics is None:
            self._statics = engine.Statics(self)
        return self._statics

    @property
    def land(self):
        return self.statics.land

    @property
    def rows(self):
        return self.H.shape[0]

    @property
    def cols(self):
        return self.H.shape[1]

    def fort_mask(self):
        """Tiles that belong to a standing fortification site."""
        mask = np.zeros(self.H.shape, dtype=bool)
        tiles = [rc for civ in self.civs for s in civ.sites for rc in s["tiles"]]
        if tiles:
            rr, cc = zip(*tiles)
            mask[list(rr), list(cc)] = True
        return mask

    def zombie_near(self, radius):
        """Zombies within `radius` tiles of every tile (cached for the current tick)."""
        if self._near_tick != self.ticks:
            self._near_cache, self._near_tick = {}, self.ticks
        if radius not in self._near_cache:
            self._near_cache[radius] = round_sum(self.Z, radius)       # (round: no square-cornered decisions)
        return self._near_cache[radius]

    # ---------------------------------------------------------------------- tick
    def tick(self):
        H, Z, D, T, O = self.H, self.Z, self.D, self.T, self.O
        civs = self.civs
        airports = self.airports

        self.knowledge_past = self.knowledge_current

        # The original's draw() clamped populations to 0..255 every frame.
        np.clip(H, 0, 255, out=H)
        np.clip(Z, 0, 255, out=Z)

        # Count tiles per civilization; tiles with <=10 humans become unowned.
        for civ in civs:
            civ.tiles = 0
        counted = (O > 0) & (H > 10)
        for civ_id, count in zip(*np.unique(O[counted], return_counts=True)):
            civs[int(civ_id)].tiles = int(count)
        low = H <= 10
        if self.ai:
            # A country's territory doesn't vanish because few people live there (mountains, deserts, emptied
            # districts stay its land): an empty tile is lost when zombies hold it, or when it's a stray speck
            # with none of its own government's land around it.
            O[low & ((Z > np.maximum(H, 2)) | ~self._same_owner_nearby())] = 0     # (one stray zombie isn't enough)
            if self.ticks % GUARD_EVERY == 0:
                # land with nobody on it is only held where the government's people are close enough to guard it
                guarded = self.guarded(refresh=True)
                O[low & (O > 0) & ~guarded & ~self.wild & ~self.fort_mask()] = 0
        else:
            O[low] = 0
        D[low] = 1
        owned_now = O > 0
        self.last_owner[owned_now] = O[owned_now]

        if self.ai:
            self._update_alarm()
            economy.step(self)
            people.step(self)
            boats.step(self)
            nukes.step(self)
            restart.step(self)
            war.step(self)
            union.step(self)
            fracture.step(self)
            fracture.overextension(self)
            fracture.independence(self)
            holdouts.step(self)
            aid.step(self)
            expeditions.step(self)
            peace.step(self)
            resolve.step(self)
            settlers.step(self)
            self.last_hunt = zombies.hunt(self)
            # defenses nobody maintains fall apart (standing garrisons are the exception)
            if LAPSE and self.ticks % LAPSE_EVERY == 0:
                lapsing = (O == 0) & (D > LAPSE) & (H > 0) & ~self.fort_mask()
                D[lapsing] -= 1
        for civ in list(civs):
            civ.update_morale(self)
        for civ in list(civs):
            civ.act(self)
        if self.ai:
            quarantine.update(self)
            self.last_line = front.step(self)

        morale = [c.morale for c in civs]
        # the per-tile rules, all tiles at once (engine.py)
        self.knowledge_current = engine.step(
            self, morale, self.knowledge_current, self.knowledge_past, unorg=UNORG if self.ai else (1.0, 1.0),
            resist=self.resist, qfac=self.qfac, closed=self.closed or None)
        self.ticks += 1

    def bbox(self, civ_id, margin=0):
        """(row slice, col slice) around a government's land, plus `margin` tiles.  All governments' boxes are
        worked out together, once per tick (a government whose land changed during the tick may reach a little
        past its box until the next one - the margins cover that)."""
        if getattr(self, "_bbox_tick", None) != (self.ticks, len(self.civs)):
            n = len(self.civs)
            ids = self.O.ravel()
            rr, cc = np.divmod(np.arange(ids.size), self.cols)
            r0, c0 = np.full(n, BIG), np.full(n, BIG)
            r1, c1 = np.full(n, -1), np.full(n, -1)
            np.minimum.at(r0, ids, rr)
            np.minimum.at(c0, ids, cc)
            np.maximum.at(r1, ids, rr)
            np.maximum.at(c1, ids, cc)
            self._bbox_data, self._bbox_tick = (r0, r1, c0, c1), (self.ticks, len(self.civs))
        r0, r1, c0, c1 = (a[civ_id] for a in self._bbox_data)
        if r1 < 0:
            return slice(0, 0), slice(0, 0)
        return (slice(max(0, r0 - margin), min(self.rows, r1 + margin + 1)),
                slice(max(0, c0 - margin), min(self.cols, c1 + margin + 1)))

    def guarded(self, refresh=False):
        """Tiles within GUARD_REACH steps (through the same government's land) of a tile where its people live."""
        if self._guarded is None or refresh or self._guarded.shape != self.O.shape:
            O = self.O
            g = (O > 0) & (self.H > 10)
            for k in range(GUARD_REACH + 1):              # (side and diagonal steps alternate: round, not square)
                grow = g.copy()
                full_step = k % 2 == 1 or k == GUARD_REACH - 1    # (the step past the core reaches all 8 ways:
                for dr, dc in (DIRECTIONS if full_step else ((-1, 0), (1, 0), (0, -1), (0, 1))):   # what's annexed next to it stays)
                    grow |= engine.shift(g, dr, dc, self.wrap, False) & (engine.shift(O, dr, dc, self.wrap, -1) == O)
                g = grow & (O > 0)
                if k == GUARD_REACH - 2:
                    self._guard_core = g.copy()           # (land taken next to this is sure to stay guarded)
                if k == GUARD_REACH - 1:
                    inner = g.copy()
            from civilization import jag
            self._guarded = inner | (g & (jag(self) > 0))     # (the outermost ring only here and there: ragged)
        return self._guarded

    def _settle_capitals(self):
        """Every government sits in a city of its own: a capital on someone else's tile (a micro-state on a coarse map)
        moves to its most populous tile; a country with no people on this map at all isn't in the game."""
        n = len(self.civs)
        pop = np.bincount(self.O.ravel(), weights=np.where(self.H > 10, self.H, 0).ravel(), minlength=n)
        for c in self.civs[1:]:
            if pop[c.id] <= 0:
                c.collapsed, c.ai = True, False
                continue
            if c.capital is None or self.O[c.capital] != c.id or self.H[c.capital] <= 10:
                win = self.bbox(c.id)
                sub = np.where((self.O[win] == c.id), self.H[win], -1)
                r, cc = np.unravel_index(int(np.argmax(sub)), sub.shape)
                c.capital = (int(r) + (win[0].start or 0), int(cc) + (win[1].start or 0))

    def may_claim(self, claimant):
        """For each tile, may government `claimant` (an array of ids, or one id) take it?  Near the land it held at the
        start (OVERSEAS_REACH), or on the landmass of its seat of government within HOME_REACH degrees of it."""
        S = self.statics
        if self._near0 is None:
            near = np.where(S.land, self.O0, 0)
            for _ in range(OVERSEAS_REACH):
                grow = near.copy()
                for dr, dc in DIRECTIONS:
                    nb = engine.shift(near, dr, dc, self.wrap, 0)
                    grow = np.where((grow == 0) & (nb > 0), nb, grow)
                near = grow
            self._near0 = near
        n = len(self.civs)
        mass = np.zeros(n, dtype=np.int64)
        cr, cc = np.zeros(n), np.zeros(n)
        for c in self.civs:
            if c.capital is not None and c.id:
                mass[c.id] = S.landmass[c.capital]
                cr[c.id], cc[c.id] = c.capital
        claimant = np.asarray(claimant)
        home = mass[claimant]
        if getattr(self, "_grid_rc", None) is None:
            b = self.meta.get("bounds")              # (east-west degrees shrink away from the equator)
            lat = (b[3] - (np.arange(self.rows) + 0.5) * float(self.meta.get("res", 0.5))) if b else np.zeros(self.rows)
            rr, col = np.indices(self.O.shape)
            self._grid_rc = (rr.astype(np.float32), col.astype(np.float32),
                             np.cos(np.radians(lat)).astype(np.float32)[:, None])
        rr, col, coslat = self._grid_rc
        dr = np.abs(rr - cr[claimant].astype(np.float32))
        dc = np.abs(col - cc[claimant].astype(np.float32))
        if self.wrap:
            dc = np.minimum(dc, self.cols - dc)
        dc = dc * coslat
        reach = HOME_REACH / float(self.meta.get("res", 0.5))
        near_capital = (dr * dr + dc * dc) <= reach * reach
        ok = (home == 0) | ((S.landmass == home) & near_capital) | (self._near0 == claimant)
        beach = getattr(self, "beach_map", None)               # (land around an overseas landing: expeditions.py)
        return ok | (beach == claimant) if beach is not None else ok

    def _update_alarm(self):
        """The world finds out: once the outbreak is big (and no longer covered up) every government starts to mobilize
        and flights between countries stop - slowly, so the first months still catch everyone unprepared."""
        cover_up = max((c.traits.get("denial", 0) for c in self.civs if c.ai), default=0)
        fallen = sum(1 for c in self.civs if c.collapsed)
        z = int(self.Z.sum())
        if self.ticks >= cover_up and z >= ALARM_ZOMBIES:
            self.alarm = min(1.0, self.alarm + ALARM_RATE + ALARM_FALL * max(0, fallen - self.fallen_seen))
        elif z < ALARM_ZOMBIES / 3:
            self.alarm = max(0.0, self.alarm - ALARM_FADE)
        self.fallen_seen = fallen

    def _same_owner_nearby(self):
        O = self.O
        rows, cols = O.shape
        out = np.zeros(O.shape, dtype=bool)
        for dr, dc in DIRECTIONS:
            sr, tr = _slices(rows, dr)
            sc, tc = _slices(cols, dc)
            out[tr, tc] |= O[sr, sc] == O[tr, tc]
        return out

    def summary(self):
        """One row per civilization that still matters, for the HUD and tests."""
        rows = []
        n = len(self.civs)
        H = np.maximum(self.H, 0)
        pops = np.bincount(self.O.ravel(), weights=H.ravel(), minlength=n)
        s = getattr(self, "scale_map", None)
        shown = (np.bincount(self.O.ravel(), weights=(H * s).ravel(), minlength=n) if s is not None
                 else pops * self.pop_scale)
        tiles = np.bincount(self.O.ravel(), weights=(H > 0).ravel(), minlength=n)
        for c in self.civs[1:]:
            if c.collapsed and not c.sites:
                continue
            rows.append(dict(id=c.id, name=c.name, pop=int(pops[c.id]), shown=float(shown[c.id]), tiles=int(tiles[c.id]),
                             morale=c.morale, food=c.food, materials=c.materials, military=float(c.military),
                             action=c.label, collapsed=c.collapsed, sites=len(c.sites),
                             closed=c.closed, at_war=war.at_war(self, c.id), successor=c.successor,
                             gov=c.gov, peace=c.peace, capital=c.capital, ports=c.ports, nukes=c.nukes - c.nukes_used))
        return rows
