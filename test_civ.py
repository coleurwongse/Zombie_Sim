"""Civilization + individual-behaviour tests (headless). Run: python test_civ.py"""
import numpy as np
import civilization as C
import economy as E
import people
import sim
import war


def DW(*a, **k):
    k.setdefault('stochastic', False)
    return sim.World(*a, **k)


def blank(n=60, humans=100, owner=1):
    return (np.full((n, n), humans), np.zeros((n, n), int), np.full((n, n), 2),
            np.ones((n, n), int), np.full((n, n), owner), {})


def two_nations(zombies=True):
    """Two nations on either side of a mountain ridge, each with a city; an outbreak in the west one."""
    n, m = 80, 120
    H = np.full((n, m), 90); Z = np.zeros((n, m), int); D = np.full((n, m), 2); T = np.ones((n, m), int)
    O = np.ones((n, m), int); O[:, 62:] = 2
    T[:, 58:62] = 3; O[:, 58:62] = 0; H[:, 58:62] = 5; T[38:42, 58:62] = 1; H[38:42, 58:62] = 40   # a pass
    for r, c in ((30, 25), (50, 95)):
        T[r - 2:r + 3, c - 2:c + 3] = 6; H[r - 2:r + 3, c - 2:c + 3] = 220
    if zombies:
        Z[60:63, 10:13] = 40
    return H, Z, D, T, O, {(30, 25): [(50, 95)], (50, 95): [(30, 25)]}


def run(w, ticks):
    for _ in range(ticks):
        w.tick()


def log(civ):
    return [(t, a) for t, a, _ in civ.history]


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def main():
    # 1. Too few / too far: ignore.
    H, Z, D, T, O, A = blank(); Z[5, 5] = 4
    w = DW(H, Z, D, T, O, A); run(w, 9)
    assert log(w.civs[1]) == [(0, C.IGNORE)] and not w.civs[1].active, log(w.civs[1])
    print("1 tiny outbreak, first 9 ticks: ignored")

    # 2. Many zombies nearby, defenses strong, nothing overrun: ignore.
    H, Z, D, T, O, A = blank(); D[:] = 6; Z[28:32, 28:32] = 120
    w = DW(H, Z, D, T, O, A); w.tick()
    m = w.civs[1].m
    assert m["zone_z"] > C.CALM_ZOMBIES and m["armor"] >= C.STRONG_ARMOR and m["pop_overrun"] < C.STRONG_OVERRUN_POP, m
    assert w.civs[1].action == C.IGNORE
    print("2 strong defenses: ignore despite %d zombies in the region (armor=%.2f)" % (m["zone_z"], m["armor"]))

    # 3. Same idea, weak defenses, big infestation: reacts.
    H, Z, D, T, O, A = blank(); Z[10:50, 10:50] = 120
    w = DW(H, Z, D, T, O, A); w.tick()
    assert w.civs[1].action != C.IGNORE, w.civs[1].history
    print("3 weak defenses, big clump ->", w.civs[1].action)

    # 4. Decisions only on the interval; no flip-flopping.
    H, Z, D, T, O, A = blank(); Z[20:40, 20:40] = 200
    w = DW(H, Z, D, T, O, A); run(w, 100)
    acts = log(w.civs[1])
    assert all(t % C.DECISION_INTERVAL == 0 for t, _ in acts) and len(acts) <= 10, acts
    print("4 %d action changes in 100 ticks" % len(acts))

    # 5. Mechanics of purge / evacuate.
    H, Z, D, T, O, A = blank(); Z[20:30, 20:30] = 150
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.materials = 100.0
    z0 = int(w.Z.sum()); civ._purge(w); assert w.Z.sum() < z0 and civ.materials < 100.0
    H, Z, D, T, O, A = blank(humans=60); Z[25:35, 25:35] = 100
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.materials = 100.0; h0 = int(w.H.sum())
    before = int(w.H[25:35, 25:35].sum())
    for _ in range(10):
        civ._evacuate(w)
        assert w.H.sum() == h0 and w.H.min() >= 0 and w.H.max() <= 255
    assert w.H[25:35, 25:35].sum() < before
    print("5 purge kills zombies; evacuate conserves humans and empties the infested block")

    # 6. Morale: calm stays at 10; unprotected expanding front drops it; protected front does not.
    H, Z, D, T, O, A = blank(); w = DW(H, Z, D, T, O, A); run(w, 30)
    assert w.civs[1].morale == 10
    def outbreak(protect):
        H, Z, D, T, O, A = blank(); Z[28:32, 28:32] = 60
        if protect: D[:] = 5
        w = DW(H, Z, D, T, O, A); lo = 10
        for _ in range(40):
            w.tick(); lo = min(lo, w.civs[1].morale)
        return lo, w
    lo_un, wu = outbreak(False); lo_pr, wp = outbreak(True)
    assert lo_un < 7 and lo_pr > lo_un + 2, (lo_un, lo_pr)
    print("6 morale: calm=10; unprotected spreading outbreak -> %d; same outbreak vs defended land -> %d" % (lo_un, lo_pr))

    # 7. Fortify picks specific places (a city and a mountain near the zombies), not everything.
    H, Z, D, T, O, A = blank(); H[30, 30] = 220; T[30, 30] = 6; T[34, 33] = 3; Z[28:32, 40:44] = 20
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]
    civ.action = C.FORTIFY; civ.active = {C.FORTIFY}; civ.next_decision = 10**9
    for _ in range(12):
        civ.morale = 8                         # keep the government alive for this test
        w.tick()
    centers = [s["center"] for s in civ.sites]
    planned = centers + ([tuple(rc) for rc in np.argwhere(civ.lost_mask)] if civ.lost_mask is not None else [])
    assert 1 <= len(centers) <= C.FORT_SITES and ((30, 30) in planned or (34, 33) in planned), planned
    fortified = int((w.D >= 5).sum())
    assert 0 < fortified < 0.1 * w.D.size and civ.materials < E.MATERIALS_START, (fortified, civ.materials)
    print("7 fortify sites %s; %d of %d tiles fortified; materials left %.0f" %
          (centers, fortified, w.D.size, civ.materials))

    # 8. An overrun site is lost for good: no refund, nothing rebuilt on the new border.
    victim = civ.sites[0]["center"]
    w.Z[victim] = 255; w.H[victim] = 20
    mat_before = civ.materials
    civ.morale = 8; w.tick()
    assert civ.materials <= mat_before + civ.mat_income + 1e-6, 'a lost site must not refund materials'
    assert victim not in [s["center"] for s in civ.sites] and civ.sites_lost >= 1
    for _ in range(60):
        civ.morale = 8; w.tick()
    assert all(cheb(s["center"], victim) > C.FORT_LOST_RADIUS for s in civ.sites), (victim, civ.sites)
    print("8 site at %s overrun -> lost; no refund, nothing re-fortified within %d tiles" % (victim, C.FORT_LOST_RADIUS))

    # 9. A government that does nothing breaks quickly - but gradually: it loses its grip on the provinces (they go
    #    their own way, hopeless places fall into anarchy) instead of all its land turning into anarchy at once.
    H, Z, D, T, O, A = blank(); Z[28:32, 28:32] = 120
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.next_decision = 10**9
    t_fall = None
    for t in range(1, 60):
        w.tick()
        if civ.collapsed or any("grip" in e or "falls" in e for _, e in w.events):
            t_fall = t; break
    assert t_fall is not None and t_fall <= 30, t_fall
    ev = [e for _, e in w.events if "grip" in e or "falls" in e][0]
    kept = int(((w.O > 0) & (w.H > 10)).sum())
    assert kept > 0 and len(w.civs) > 2 or civ.collapsed, (ev, kept, len(w.civs))
    print("9 no response: after %d ticks '%s'; %d populated tiles still governed" % (t_fall, ev[:90], kept))

    # 10. Panic flight: people flee across borders even when the civilization does nothing.
    H, Z, D, T, O, A = blank(); O[:, 30:] = 0; Z[:, :12] = 120
    w = DW(H, Z, D, T, O, A); w.civs[1].next_decision = 10**9
    unowned_before = int(w.H[:, 30:].sum())
    for _ in range(8):
        w.tick()
    assert w.last_panic > 0
    print("10 panic flight with the civ doing nothing: %d people fleeing on the last tick" % w.last_panic)
    H, Z, D, T, O, A = blank(); Z[:, :20] = 120
    w = DW(H, Z, D, T, O, A)
    w.zombie_near(C.NEAR_RADIUS)
    h0, z0 = int(w.H.sum()), int(w.Z.sum()); people.step(w)
    turned = int(w.Z.sum()) - z0                               # (stragglers who were bitten turn on arrival)
    assert w.last_panic > 0 and int(w.H.sum()) + turned == h0 and w.H.max() <= 255
    print("   people.step alone moved %d people; nobody lost (%d stragglers turned)" % (w.last_panic, turned))

    # 11. Riots in a city, secession, and the morale hit.
    H, Z, D, T, O, A = blank(40, humans=100); H[15:25, 15:25] = 200; T[15:25, 15:25] = 6; Z[10:30, 26:34] = 120
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.next_decision = 10**9; civ.morale = 4
    riots = 0; seceded = False; d0 = int(w.D[15:25, 15:25].sum())
    for _ in range(25):
        civ.morale = 4 if not civ.collapsed else civ.morale
        w.tick(); riots += w.last_riots
        if (w.O[15:25, 15:25] == 0).any(): seceded = True
    assert riots > 0, "no riots"
    print("11 city under pressure: %d rioting tile-ticks; tiles seceded: %s" % (riots, seceded))

    # 14. Economy: balanced at the start; famine when the farmland is taken; no ammo, no purge.
    w = DW(*two_nations(zombies=False)); w.tick()
    for c in w.civs[1:]:
        assert 1.0 <= c.food_prod / c.food_use <= 1.5 and c.mat_income > 0, (c.food_prod, c.food_use)
    print("14 two_nations economy: food surplus %s, materials/tick %s" %
          ([round(c.food_prod / c.food_use, 2) for c in w.civs[1:]], [round(c.mat_income, 1) for c in w.civs[1:]]))
    H, Z, D, T, O, A = blank(); w = DW(H, Z, D, T, O, A); civ = w.civs[1]; w.tick()
    civ.food = 0.0; w.Z[:] = 40; w.H[:] = 30            # nothing productive any more
    for _ in range(12):
        civ.morale = max(civ.morale, 6); w.tick()
    assert civ.famine, "should be starving"
    civ2 = DW(*blank()).civs[1]; civ2.materials = 0.0
    wz = DW(*blank()); wz.Z[:] = 50; zb = int(wz.Z.sum()); wz.civs[1].materials = 0.0; wz.civs[1]._purge(wz)
    assert int(wz.Z.sum()) == zb
    print("   famine detected when production stops; a purge without materials does nothing")

    # 15. Food: empty farms grow nothing, storage shrinks with the people, unowned survivors starve.
    def farm_world(h):
        H, Z, D, T, O, A = blank(30, humans=h); return DW(H, Z, D, T, O, A)
    full, thin = farm_world(50), farm_world(14)
    full.tick(); thin.tick()
    ratio = thin.civs[1].food_prod / full.civs[1].food_prod
    assert ratio < 0.5, ratio
    w = farm_world(50); w.tick(); civ = w.civs[1]; stock0 = civ.food
    w.H[:] = 5                                          # 90% of the people gone
    for _ in range(3): w.tick()
    assert civ.food < 0.5 * stock0, (civ.food, stock0)
    H, Z, D, T, O, A = blank(30, humans=8, owner=0); T[:] = 3                  # survivors in unowned mountains
    w = DW(H, Z, D, T, O, A); w.civs[1].next_decision = 10**9
    for _ in range(40): w.tick()
    assert w.H.max() <= 3 and w.H.sum() < 0.4 * 8 * 900, (w.H.max(), w.H.sum())
    print("15 food: thin farms produce %.0f%% of full ones; storage fell %d -> %d with the people; unowned mountain survivors starved %d -> %d" %
          (ratio * 100, stock0, civ.food, 8 * 900, w.H.sum()))

    # 16. Survivors in an infested tile walk out of it.
    H, Z, D, T, O, A = blank(40, humans=0, owner=0); D[:] = 1
    Z[15:26, 15:26] = 12; H[20, 20] = 1
    w = DW(H, Z, D, T, O, A)
    for _ in range(12): w.tick()
    ys, xs = np.nonzero(w.H)
    assert w.H.sum() == 1 and max(abs(ys[0] - 20), abs(xs[0] - 20)) >= 6, (w.H.sum(), ys, xs)
    print("16 lone survivor (1 human, 12 zombies/tile) escaped %d tiles from the infested block" % max(abs(ys[0] - 20), abs(xs[0] - 20)))

    # 17. Purge reaches infested ground around the civilization, owned or not - and no further.
    H, Z, D, T, O, A = blank(60, humans=100, owner=1)
    H[:, 30:] = 0; O[:, 30:] = 0; Z[:, 30:] = 100
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.materials = 300.0
    civ._purge(w)
    reach = 29 + C.REGION_REACH
    assert (w.Z[:, 30:reach + 1] < 100).any() and (w.Z[:, reach + 1:] == 100).all()
    assert civ.last_strike > 0 and civ.materials < 300.0
    print("17 purge struck %d tiles of unowned infested ground next to the civilization" % civ.last_strike)

    # 18. It recognises a threat that isn't heading its way: zombies multiplying behind strong defenses,
    #     or a city already lost, are not ignored; a stable, defended situation is.
    civ = DW(*blank()).civs[1]; civ.materials = 100.0
    base = dict(n=100, armor=0.8, growth=0.0, damage=0.0, pop_exposure=0.05, pop_overrun=0.0, zone_z=5000,
                strikes=20, fort_ok=True)
    calm_scores = civ.score(dict(base))
    grow_scores = civ.score(dict(base, growth=0.6))
    lost_scores = civ.score(dict(base, damage=0.2, pop_overrun=0.04))
    assert max(calm_scores.values()) < C.ACTIVATE
    assert max(grow_scores.values()) >= C.ACTIVATE and max(lost_scores.values()) >= C.ACTIVATE
    print("18 defended+stable -> ignore; zombies growing behind defenses -> %s; city lost -> %s" %
          (max(grow_scores, key=grow_scores.get), max(lost_scores, key=lost_scores.get)))

    # 19. Fortification sites are spread out: several distinct places, never a cluster.
    H, Z, D, T, O, A = two_nations(); Z[:, 64:66] = 30
    w = DW(H, Z, D, T, O, A)
    for _ in range(12): w.tick()
    civ = w.civs[2]; civ.sites = []; civ.lost_mask = None; civ._plan_sites(w)
    cs = [s["center"] for s in civ.sites]
    gaps = [cheb(a, b) for i, a in enumerate(cs) for b in cs[i + 1:]]
    assert len(cs) >= 4 and min(gaps) >= C.FORT_SPACING and max(gaps) >= 30, (cs, gaps)
    print("19 %d sites spread over %d tiles (closest pair %d apart): %s" % (len(cs), max(gaps), min(gaps), cs))

    # 12. Non-square map + wrap.
    H, Z, D, T, O, A = blank(); H, Z, D, T, O = H[:20, :45], Z[:20, :45], D[:20, :45], T[:20, :45], O[:20, :45]
    Z[10, 44] = 60
    w = DW(H, Z, D, T, O, A); run(w, 30)
    assert w.Z[5:16, :3].sum() > 0
    print("12 non-square map runs; zombies wrap across the edge")


    # 20. Anarchy doesn't dissolve the army: garrisons stay, keep their defense and keep killing zombies nearby.
    H, Z, D, T, O, A = blank(40, humans=120); w = DW(H, Z, D, T, O, A); civ = w.civs[1]
    civ.sites = [dict(center=(20, 20), tiles=[(20, 20), (20, 21)], level=7, target=7)]
    w.tick(); civ.collapse(w, fracture=False)                # the old all-at-once collapse (garrisons hold either way)
    assert civ.collapsed and len(civ.sites) == 1 and (w.O == 1).sum() == 0
    w.Z[20, 22] = 40
    run(w, 6)
    assert len(civ.sites) == 1 and w.D[20, 20] >= 7 and w.Z[20, 20] == 0
    print("20 collapsed civ keeps its garrison (defense %d) that keeps its centre clear of zombies" % w.D[20, 20])

    # 21. Survivors in a safe corner restart civilization: found a colony, adopt the fallen government's garrison,
    #     then grow slowly.
    H, Z, D, T, O, A = blank(60, humans=0, owner=0)
    H[30:40, 30:40] = 60
    w = DW(H, Z, D, T, O, A); old = w.add_civ(name="Old"); old.collapsed = True; old.remnant = True
    w.H0[30:40, 30:40] = 110                                 # (before the outbreak more people lived here: room to grow)
    old.sites = [dict(center=(33, 33), tiles=[(33, 33)], level=7, target=7)]
    n0 = len(w.civs); run(w, 15); assert len(w.civs) == n0          # not instantly: a place has to stay settled and safe for a while
    run(w, 40)
    new = w.civs[-1]
    assert len(w.civs) == n0 + 1 and new.successor and (w.O[30:40, 30:40] == new.id).all() and len(new.sites) == 1
    p0 = int(w.H.sum()); run(w, 100); p1 = int(w.H.sum())
    assert p0 < p1 < p0 * 1.6, (p0, p1)
    print("21 survivors founded %s with a garrison; population %d -> %d in 100 ticks (slow growth)" % (new.name, p0, p1))

    # 22. A trained army sweeps zombies away from its borders (compared with doing nothing); an untrained one
    #     doesn't start a campaign.
    def campaign(reclaim):
        H, Z, D, T, O, A = blank(50, humans=100); H[:, 30:] = 0; O[:, 30:] = 0; Z[:, 30:36] = 12; D[:] = 6
        w = DW(H, Z, D, T, O, A); civ = w.civs[1]; w.tick(); civ.materials = 300.0; civ.military = 0.8
        civ.m = civ.observe(w); civ.next_decision = 10 ** 9; civ.active = {C.RECLAIM} if reclaim else set()
        if reclaim:
            assert civ.score(civ.m)[C.RECLAIM] >= C.ACTIVATE
            civ.military = 0.1; assert civ.score(civ.m)[C.RECLAIM] < 0; civ.military = 0.8
        for _ in range(30):
            civ.morale = 9; w.tick()
        return int(w.Z.sum()), civ
    every = people.STRAY_EVERY; people.STRAY_EVERY = 10 ** 9      # (stragglers off: this is about the army - on a
    z_idle, _ = campaign(False); z_war, civ = campaign(True)        #  map this small where they land swings it)
    people.STRAY_EVERY = every
    assert z_war < z_idle * 0.85 and civ.kills > 0, (z_idle, z_war)
    print("22 reclaim: zombies %d without a campaign vs %d with one (%d killed, army 0.80 -> %.2f after training back up)" %
          (z_idle, z_war, civ.kills, civ.military))

    # 23. Stochastic runs vary with the seed, repeat for the same seed, and stochastic=False is exact.
    def final(seed, stoch):
        w = sim.World(*two_nations(), seed=seed, stochastic=stoch)
        run(w, 25); return int(w.H.sum()), int(w.Z.sum())
    a, b, a2 = final(1, True), final(2, True), final(1, True)
    d1, d2 = final(1, False), final(2, False)
    assert a == a2 and a != b and d1 == d2
    print("23 seed 1 -> %s (again %s), seed 2 -> %s; deterministic mode ignores the seed %s" % (a, a2, b, d1))

    # 24. Quarantine: shut borders stop outsiders walking in, slow heavy hordes entering secure land,
    #     and the border patrols kill some.
    H, Z, D, T, O, A = blank(40, humans=100); H[:, :20] = 0; O[:, :20] = 0; Z[:, :20] = 150
    H[:, 20] = 100; Z[:, 5] = 0
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.materials = 200.0; civ.active = {C.QUARANTINE}; civ.next_decision = 10 ** 9
    w.tick(); assert w.closed == {1} and w.qfac is not None and w.qfac[20, 25] < 1.0; qf = w.qfac[20, 25]
    z0 = int(w.Z[:, 20:].sum()); run(w, 10)
    assert civ.kills > 0 and civ.materials < 200.0; kills = civ.kills
    def refugees_east(closed):
        H, Z, D, T, O, A = blank(40, humans=100); H[:, :20] = 80; O[:, :20] = 0; Z[:, :14] = 120; Z[:, 10:20] = 30
        w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.materials = 200.0; civ.next_decision = 10 ** 9
        w.closed = {1} if closed else set()
        before = int(w.H[:, 20:].sum()); people.step(w)
        return int(w.H[:, 20:].sum()) - before
    shut, open_ = refugees_east(True), refugees_east(False)
    assert shut < open_, (shut, open_)
    print("24 quarantine: borders shut, zombies slowed to %.2f of normal, patrols killed %d; refugees entering: %d with shut borders vs %d open" % (qf, kills, shut, open_))

    # 25. Wars: a nation short of food attacks a better-off neighbour; both lose people; zombies force a truce.
    def two():
        H, Z, D, T, O, A = blank(40, humans=100); O[:, 20:] = 2; w = DW(H, Z, D, T, O, A)
        for c in w.civs[1:]: c.next_decision = 10 ** 9
        return w
    w = two(); w.tick(); w.civs[1].food = 0.0; w.civs[1].famine = True; w.civs[1].materials = 0.0
    w.civs[1].traits["aggression"] = 100.0
    for _ in range(200):
        w.tick()
        if w.wars: break
    assert w.wars and "WAR" in " ".join(t for _, t in w.events)
    h0 = int(w.H.sum()); run(w, 20)
    assert int(w.H.sum()) < h0 - 50, (h0, int(w.H.sum()))
    w2 = two(); w2.tick(); war.declare(w2, 1, 2); w2.Z[:, :3] = 200; w2.civs[1].m["pop_overrun"] = 0.9
    w2.civs[1].m["damage"] = 0.9; w2.civs[1].m["pop_exposure"] = 0.9
    w2.civs[1].m["n"] = 5; w2.civs[2].m = dict(w2.civs[1].m)
    war.step(w2); assert not w2.wars
    print("25 scarcity -> war (%s); fighting cost %d people in 20 ticks; zombie crisis -> truce" %
          ([t for _, t in w.events if "WAR" in t][0], h0 - int(w.H.sum())))

    # 26. Mass evacuation: a city sees a horde growing nearby and empties toward safer land, civ or no civ.
    H, Z, D, T, O, A = blank(60, humans=0, owner=0)
    H[28:33, 28:33] = 150; H[28:33, 50:55] = 5
    w = DW(H, Z, D, T, O, A); w.ai = True
    before = int(w.H[28:33, 28:33].sum()); east0 = int(w.H[:, 33:].sum())
    for k in range(25):
        edge = 10 + k // 2                               # a horde creeps in from the west
        w.Z[:] = 0; w.Z[26:36, edge:edge + 6] = 40
        people.step(w); w.ticks += 1
    after = int(w.H[28:33, 28:33].sum()); east1 = int(w.H[:, 33:].sum())
    assert after < before * 0.8 and east1 > east0 and w.H.sum() >= 0.95 * (25 * 150 + 25 * 5)
    print("26 city %d -> %d people as the horde approached; %d more people now live east of it" % (before, after, east1 - east0))

    # 27. Unorganized land is easy prey: with the same zombies and the same people, the tiles nobody governs are
    #     overrun faster (and have no defense of their own; standing garrisons are the exception).
    def prey(owned):
        H, Z, D, T, O, A = blank(40, humans=0, owner=0)
        H[:, 20:] = 90; Z[:, :20] = 60; D[:, 20:] = 4
        if owned: O[:, 20:] = 1
        w = DW(H, Z, D, T, O, A); w.civs[1].next_decision = 10 ** 9
        for _ in range(12):
            w.civs[1].morale = 9; w.tick()
        return int(np.clip(w.H[:, 20:], 0, None).sum()), int(w.Z[:, 20:].sum()), int(w.D[:, 25:].max())
    h_own, z_own, _ = prey(True); h_un, z_un, d_un = prey(False)
    assert h_un < 0.5 * h_own and z_un > 0.9 * z_own, (h_own, z_own, h_un, z_un, d_un)   # (marching hordes fill both)
    print("27 same horde: governed land keeps %d people (%d zombies in), unorganized land %d (%d zombies in)" %
          (h_own, z_own, h_un, z_un))

    # 28. Governments merge: fragments of one former country (shared root) join up, the smaller into the larger,
    #     not while at war, and never two separate original nations.
    def pair(root_same, successors=True, at_war=False):
        H, Z, D, T, O, A = blank(40, humans=90, owner=1); O[:, 20:] = 2
        w = DW(H, Z, D, T, O, A); c1, c2 = w.civs[1], w.civs[2]
        for c in (c1, c2):
            c.successor = successors; c.next_decision = 10 ** 9
        c2.root = c1.root if root_same else 2
        if root_same:
            w.O0[:] = 1                                     # (fragments of one country: all its land was country 1's)
        w.ticks = 1; w.tick(); c1.materials, c2.materials = 100.0, 50.0
        if at_war: war.declare(w, 1, 2)
        import union
        keep = union.KIN_CHANCE, union.STRANGER_CHANCE
        union.KIN_CHANCE = union.STRANGER_CHANCE = 10.0
        try:
            for _ in range(80):
                for c in (c1, c2): c.morale = 9
                w.tick()
        finally:
            union.KIN_CHANCE, union.STRANGER_CHANCE = keep
        return w
    w = pair(True)
    gone = [c for c in w.civs[1:3] if c.collapsed]; kept = [c for c in w.civs[1:3] if not c.collapsed]
    assert len(gone) == 1 and gone[0].merged_into == kept[0].id and not (w.O == gone[0].id).any()
    assert kept[0].materials >= 100.0 + 50.0 - 10           # stores pooled
    assert not any(c.collapsed for c in pair(True, at_war=True).civs[1:3])
    assert not any(c.collapsed for c in pair(False, successors=False).civs[1:3])
    print("28 fragments of one country merged (%s); no merge while at war, or between separate nations" %
          [t for _, t in w.events if "merges" in t][0])

    # 29. Staged offensive: a stalled, well-armed nation plants a base in infested land, eradicates zombies around it,
    #     settles the cleared ground, and finishes the advance (then looks for the next base).
    H, Z, D, T, O, A = blank(60, humans=0, owner=0)
    H[:, :25] = 100; O[:, :25] = 1; Z[:, 33:50] = 15; D[:, :25] = 7; D[:, 25:] = 1
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; w.tick()
    civ.materials = 400.0; civ.military = 0.9; civ.tile_hist.extend([1500] * 8)
    z0, own0 = int(w.Z.sum()), int((w.O == 1).sum())
    import fracture                                       # (this is about the offensive, not about the realm splitting)
    keep = fracture.OVEREXTEND_CHANCE
    fracture.OVEREXTEND_CHANCE = 0.0
    try:
        for _ in range(220):
            civ.morale = 10; w.D[:, :24] = 7; w.tick(); civ.materials = min(400.0, civ.materials + 1.5)
    finally:
        fracture.OVEREXTEND_CHANCE = keep
    ev = " ".join(t for _, t in w.events)
    assert "plants a fortified base" in ev and civ.advances >= 1 and int(w.Z.sum()) < 0.8 * z0 and int((w.O == 1).sum()) > own0 + 60, \
        (ev, civ.advances, z0, int(w.Z.sum()), own0, int((w.O == 1).sum()))
    # ... and a nation that is still growing, or has no army, does not start one
    civ2 = DW(*blank()).civs[1]; civ2.military = 0.9; civ2.materials = 300.0
    civ2.tile_hist.extend([100, 150, 200, 260, 330, 400, 480, 560]); civ2.m = dict(pop=5000, hordes=9)
    import offensive
    assert not offensive.ready(civ2, DW(*blank()), 0.0)
    print("29 offensive: %d advance(s), zombies %d -> %d, territory %d -> %d tiles" %
          (civ.advances, z0, int(w.Z.sum()), own0, int((w.O == 1).sum())))

    import fracture, front, peace, offensive as off, mapio
    # 30. Losing the capital moves the government; it doesn't end it.
    H, Z, D, T, O, A = blank(60, humans=100)
    T[10:13, 10:13] = 6; H[10:13, 10:13] = 220; T[45:48, 45:48] = 6; H[45:48, 45:48] = 200
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.next_decision = 10 ** 9; w.tick()
    civ.capital = (11, 11); w.Z[8:15, 8:15] = 250; w.H[8:15, 8:15] = 5
    for _ in range(12):
        civ.morale = 9; w.tick()
    assert not civ.collapsed and civ.capital is not None and abs(civ.capital[0] - 11) > 10, civ.capital
    print("30 capital overrun: the government moved to %s and carries on" % (civ.capital,))

    # 31. A region cut off from the capital goes its own way (a new state with its own form of government); a tiny
    #     cut-off scrap is lost; a garrison holds out loyally.
    H, Z, D, T, O, A = blank(60, humans=100); w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.next_decision = 10 ** 9
    w.tick(); civ.capital = (10, 10)
    w.Z[:, 28:31] = 200; w.H[:, 28:31] = 0; w.O[:, 28:31] = 0  # a band of zombies cuts the country in two
    w.Z[2, 55] = 200; w.H[2, 55] = 0                            # ... and a scrap in the far corner is cut off too
    for _ in range(fracture.CUTOFF_TICKS // fracture.FRACTURE_EVERY + 2):
        w.ticks += fracture.FRACTURE_EVERY - w.ticks % fracture.FRACTURE_EVERY
        fracture.step(w)                                       # (only the contact rules; nothing else moves)
    east = w.O[:, 35:]
    new = [c for c in w.civs[2:] if c.split_from == 1]
    assert new and (east == new[0].id).mean() > 0.8 and (w.O[:, :25] == 1).mean() > 0.8, (len(new), np.unique(east))
    print("31 cut off from the capital: the east became %s (%s)" % (new[0].name, new[0].gov))

    # 32. Morale breaks: the government keeps its heartland, the provinces become states, a crowded city with a horde
    #     at the gates falls into anarchy.
    H, Z, D, T, O, A = blank(80, humans=100)
    T[60:63, 60:63] = 6; H[60:63, 60:63] = 230; Z[56:58, 56:66] = 120          # the doomed city
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.next_decision = 10 ** 9; w.tick(); civ.capital = (10, 10)
    civ.collapse(w, "test")
    states = [c for c in w.civs[2:] if c.split_from == 1]
    assert not civ.collapsed and civ.morale >= fracture.RALLY_MORALE and w.O[10, 10] == 1
    assert len(states) >= 1 and (w.O[60:63, 60:63] == 0).any(), (len(states), w.O[60:63, 60:63])
    print("32 morale broke: kept its heartland; %s broke away; the besieged city fell into anarchy" %
          ", ".join(f"{c.name} ({c.gov})" for c in states))

    # 33. Hunger riots hurt but don't break a country up; hunger alone doesn't topple a government.
    H, Z, D, T, O, A = blank(40, humans=180); T[:] = 6
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.next_decision = 10 ** 9; w.tick()
    civ.import_share = 0.0                                 # (a blockade: no food comes in from abroad either)
    for _ in range(80):
        civ.food = 0.0; w.tick()
    assert civ.famine and not civ.collapsed and civ.morale >= C.FAMINE_MORALE_FLOOR - 1 and (w.O == 1).mean() > 0.95
    print("33 80 ticks of famine: morale %d, %d riots, still governs %.0f%% of its land" %
          (civ.morale, int(w.R.sum()), 100 * (w.O == 1).mean()))

    # 34. Shut borders don't flicker: once closed they stay closed until the outside has been quiet for a while.
    H, Z, D, T, O, A = blank(40, humans=100); H[:, :15] = 0; O[:, :15] = 0; Z[:, :12] = 150
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.materials = 300.0
    flips, prev, closed_at = 0, False, None
    for t in range(140):
        if t == 40:
            w.Z[:, :15] = 0                                    # the horde vanishes
        civ.morale = 9; w.tick()
        if civ.closed != prev:
            flips += 1; prev = civ.closed
            closed_at = t if civ.closed else closed_at
    assert flips == 2 and civ.quar_low >= 0, flips
    print("34 quarantine: closed at tick %d, reopened only once the outside stayed quiet (%d changes in 140 ticks)" %
          (closed_at, flips))

    # 35. A manned front line holds the actual border: zombies pressing on it are slowed and shot, and the people
    #     behind it stay put.
    def border(army):
        H, Z, D, T, O, A = blank(40, humans=100); H[:, :15] = 0; O[:, :15] = 0; Z[:, :14] = 30
        w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.next_decision = 10 ** 9; w.tick()
        w.pop_ref /= 4                                     # (a big country: troops enough for the whole border)
        civ.military, civ.materials, civ.alert = army, 300.0, 1.0 if army else 0.0
        for _ in range(12):
            civ.morale = 9; civ.alert = 1.0 if army else 0.0; w.tick()
        return int(w.Z[:, 15:].sum()), int(np.clip(w.H[:, 15:], 0, None).sum()), civ.kills
    z_line, h_line, kills = border(0.9); z_open, h_open, _ = border(0.0)
    assert z_line < z_open and h_line > h_open + 20 and kills > 0, (z_line, z_open, h_line, h_open)
    print("35 front line: %d zombies got in (vs %d with no army), %d people still behind the line (vs %d), %d shot" %
          (z_line, z_open, h_line, h_open, kills))

    # 36. Forts cost upkeep, and a government can't keep more than its people can man: it gives the least needed up.
    H, Z, D, T, O, A = blank(40, humans=60); w = DW(H, Z, D, T, O, A); civ = w.civs[1]; civ.next_decision = 10 ** 9
    w.tick(); civ.materials = 1.0
    civ.sites = [dict(center=(r, c), tiles=[(r, c)], level=7, target=7) for r in (5, 15, 25, 35) for c in (5, 15, 25, 35)]
    w.tick()
    assert len(civ.sites) <= civ.max_sites() and civ.materials >= 0, (len(civ.sites), civ.max_sites())
    print("36 16 forts, %d people, no money: kept %d (max %d), upkeep %.2f/tick" %
          (civ.m["pop"], len(civ.sites), civ.max_sites(), civ.upkeep))

    # 37. When the zombies are gone the emergency ends: forts are dismantled, the army stands down, people go back to town.
    n = 50
    H = np.full((n, n), 90); Z = np.zeros((n, n), int); D = np.full((n, n), 2); T = np.ones((n, n), int)
    O = np.ones((n, n), int); T[20:25, 20:25] = 6; H[20:25, 20:25] = 60; H[5:8, 40:43] = 200; D[5:8, 40:43] = 7
    w = DW(H, Z, D, T, O, {}); civ = w.civs[1]; civ.capital = (22, 22); civ.military = 0.9
    civ.emergencies = 1                                    # (the emergency it is standing down from)
    w.H0[:] = 60; w.H0[20:25, 20:25] = 200                 # refugees crowd the countryside; the city used to hold more
    civ.sites = [dict(center=(6, 41), tiles=[(6, 41)], level=7, target=7), dict(center=(22, 22), tiles=[(22, 22)], level=7, target=7)]
    city0 = int(w.H[20:25, 20:25].sum())
    run(w, peace.PEACE_AFTER + 1); army0 = civ.military
    run(w, peace.FORT_QUIET + 60)
    assert civ.peace and [s["center"] for s in civ.sites] == [(22, 22)] and w.H[20:25, 20:25].sum() > city0 * 1.3
    assert civ.military < army0 and w.D[6, 41] <= peace.DEMOB_FLOOR
    print("37 peace: fort at (6,41) dismantled, army %.2f, city %d -> %d people" %
          (civ.military, city0, int(w.H[20:25, 20:25].sum())))

    # 38. An offensive base's zone is a ragged circle shaped by the terrain, not a square.
    H, Z, D, T, O, A = blank(60); T[40:60, 20:40] = 3
    w = sim.World(H, Z, D, T, O, A, seed=3, stochastic=True)
    zone = off._zone_mask(w, 40, 30)
    side = 2 * off.BASE_RADIUS + 1
    corners = zone[0, 0] or zone[0, -1] or zone[-1, 0] or zone[-1, -1]
    north, south = zone[:off.BASE_RADIUS].sum(), zone[off.BASE_RADIUS + 1:].sum()
    assert not corners and zone.sum() < 0.85 * side * side and north > south, (zone.sum(), north, south)
    print("38 base zone: %d of %d tiles of the square, none in the corners, %d on the plain vs %d in the mountains" %
          (zone.sum(), side * side, north, south))

    # 39. The Middle-earth map: realms, alliances that keep allies from fighting, standing fortresses, the outbreak
    #     at Bree, the wars of 3018 - and no airports or warheads.
    import json
    w = sim.World.from_folder("maps/middle_earth", stochastic=False)
    meta = json.load(open("maps/middle_earth/meta.json", encoding="utf-8"))
    ids = {c.name: c.id for c in w.civs}
    r, c = meta["patient_zero"]
    assert not w.wrap and w.civs[int(w.O[r, c])].name == "Bree-land" and w.Z.sum() > 0 and not w.airports
    assert war.key(ids["Mordor"], ids["Gondor"]) in w.wars and war.key(ids["Isengard"], ids["Rohan"]) in w.wars
    assert war.allied(w, ids["Gondor"], ids["Rohan"]) and war.allied(w, ids["Mordor"], ids["Harad"])
    assert not war.allied(w, ids["Gondor"], ids["Mordor"])
    war.declare(w, ids["Gondor"], ids["Rohan"], "test")
    assert war.key(ids["Gondor"], ids["Rohan"]) not in w.wars                  # allies don't fight
    mt = next(ct for ct in w.cities if ct[0] == "Minas Tirith")
    assert w.D[mt[1], mt[2]] >= 7 and any(st.get("standing") for st in w.civs[ids["Gondor"]].sites)
    assert all(cv.nukes == 0 for cv in w.civs) and w.datestr() == "09/23/3018"
    print("39 Middle-earth: %d realms, %d places, outbreak at Bree on %s, %d wars; Gondor and Rohan won't fight"
          % (len(w.civs) - 1, len(w.cities), w.datestr(), len(w.wars)))

    import boats, nukes, render, terrain
    # 40. Water is water: nobody lives at sea; a horde adrift swims for the nearest land; stragglers don't fill the sea.
    n = 60
    H = np.zeros((n, n), int); Z = np.zeros((n, n), int); D = np.full((n, n), 2); T = np.zeros((n, n), int)
    O = np.zeros((n, n), int); T[:, 45:] = 1; T[:, 43:45] = terrain.SHALLOW; H[:, 46:] = 80; O[:, 46:] = 1
    Z[28:32, 10:14] = 120                                        # a horde in the open sea, 30 tiles out
    w = sim.World(H, Z, D, T, O, {}, seed=2, stochastic=True, meta={"wrap": False}); w.civs[1].next_decision = 10 ** 9
    z0 = int(w.Z.sum())
    for _ in range(40):
        w.civs[1].morale = 9; w.tick()
    sea = ~w.land
    assert int(w.H[sea].sum()) == 0
    landed = int(w.Z[:, 43:].sum()) + int(z0 - w.Z.sum())
    cols_with = np.nonzero(w.Z.sum(axis=0))[0]
    assert landed > 0.3 * z0 and (cols_with.size == 0 or cols_with.min() >= 8), (landed, z0, cols_with[:5])
    print("40 a horde adrift 30 tiles out swam for the coast: %d of %d reached it (or were lost at sea); "
          "nobody lives in the water" % (landed, z0))

    # 41. Refugee boats: a frightened coast puts to sea, toward a safe coast across the same water; some of those on
    #     board were bitten.
    H = np.zeros((n, n), int); Z = np.zeros((n, n), int); D = np.full((n, n), 2); T = np.zeros((n, n), int)
    O = np.zeros((n, n), int)
    T[:, :20] = 1; T[:, 40:] = 1; H[:, :20] = 120; H[:, 40:] = 60; O[:, :20] = 1; O[:, 40:] = 2
    Z[:, :17] = 60                                               # the west is being overrun
    w = sim.World(H, Z, D, T, O, {}, seed=3, stochastic=True)
    w.ticks = 0
    east0, ez0 = int(w.H[:, 40:].sum()), int(w.Z[:, 40:].sum())
    moved = boats.refugee_boats(w)
    assert moved > 0 and int(w.H[:, 40:].sum()) > east0 and int(w.Z[:, 40:].sum()) >= ez0
    print("41 boats: %d refugees crossed the strait (%d arrived infected)" % (moved, int(w.Z[:, 40:].sum()) - ez0))

    # 42. Ports earn trade; food is shipped from full granaries to empty ones.
    w = sim.World(H, np.zeros((n, n), int), D, T, O, {}, seed=3, stochastic=False,
                  meta={"ports": [[30, 19, 5], [30, 40, 5]]})
    w.tick()
    a, b = w.civs[1], w.civs[2]
    a.food, b.food, b.materials = 100 * a.food_use, 5 * b.food_use, 50.0
    m0, fb0 = a.materials, b.food
    boats.shipping(w)
    assert a.ports > 0 and a.materials > m0 and b.food > fb0, (a.ports, a.materials, m0, b.food, fb0)
    print("42 shipping: %s earns trade at its ports; %.2f food shipped to %s" % (a.name, b.food - fb0, b.name))

    # 43. Nuclear weapons: a desperate nuclear power hits a giant horde (not its own people), with fallout.
    H = np.zeros((n, n), int); Z = np.zeros((n, n), int); D = np.full((n, n), 2); T = np.ones((n, n), int)
    O = np.zeros((n, n), int); H[:, :25] = 150; O[:, :25] = 1; Z[25:35, 30:40] = 250
    w = sim.World(H, Z, D, T, O, {}, seed=1, stochastic=True); civ = w.civs[1]; w.tick()
    civ.nukes = 10
    civ.m = dict(civ.m, pop_exposure=1.0, pop_overrun=0.5, damage=0.5)
    target = nukes._horde_target(w, civ, w.zombie_near(4))
    z0 = int(w.Z.sum())
    nukes.detonate(w, civ, target, "the horde")
    assert target is not None and target[1] >= 25 and int(w.Z.sum()) < 0.75 * z0 and nukes.poisoned(w).any()
    assert "NUCLEAR STRIKE" in w.events[-1][1]
    print("43 nukes: %s" % w.events[-1][1])

    # 44. Civil war: a region that breaks away can be fought for; the stronger side takes ground.
    H, Z, D, T, O, A = blank(60, humans=100); O[:, 35:] = 2
    w = DW(H, Z, D, T, O, A); w.civs[2].split_from = 1; w.civs[2].root = 1; w.tick()
    for c in w.civs[1:]:
        c.next_decision = 10 ** 9
    w.civs[1].military, w.civs[2].military = 0.9, 0.2
    war.declare(w, 1, 2, "test", civil=True)
    t1 = int((w.O == 1).sum())
    for _ in range(60):
        for c in w.civs[1:3]:
            c.morale = 9
        w.tick()
    ev = " ".join(e for _, e in w.events)
    assert "CIVIL WAR" in ev and (int((w.O == 1).sum()) > t1 or "won the civil war" in ev), ev[-300:]
    print("44 civil war: the old government took %d tiles back%s" %
          (int((w.O == 1).sum()) - t1, " and reunited the country" if "won the civil war" in ev else ""))

    # 45. A war between nations that don't touch is fought with strikes on cities (within reach).
    H, Z, D, T, O, A = blank(60, humans=120); O[:, 40:] = 2; O[:, 20:40] = 0; H[:, 20:40] = 0
    w = DW(H, Z, D, T, O, A); w.tick()
    for c in w.civs[1:]:
        c.next_decision = 10 ** 9
        c.military, c.materials = 0.8, 100.0
    war.declare(w, 1, 2)
    h0 = int(w.H[:, 40:].sum())
    for _ in range(30):
        for c in w.civs[1:3]:
            c.morale = 9
        w.tick()
    assert "strikes" in " ".join(e for _, e in w.events) and int(w.H[:, 40:].sum()) < h0
    print("45 distant war: %s" % [e for _, e in w.events if "strikes" in e][0])

    # 46. The calendar: one tick is one day from the start date; a fallen government's garrison says whose it is.
    w = DW(*blank(), meta={"start_date": "2026-10-09"})
    run(w, 85)
    assert w.datestr() == "01/02/2027", w.datestr()
    civ = w.civs[1]; civ.sites = [dict(center=(5, 5), tiles=[(5, 5)], level=7, target=7)]
    civ.collapse(w, fracture=False)
    assert "garrison of Civ 1 (its government fell)" in render.describe(w, 5, 5)
    print("46 day 85 is %s; hover over a fallen government's fort: '%s'" % (w.datestr(), render.describe(w, 5, 5)))
    # 47. Guarded land: emptied land far from the government's people falls away; land that was always empty stays.
    import engine, offensive as off2, restart, nukes as nk
    H, Z, D, T, O, A = blank(60, humans=0); H[:, :20] = 100
    w = DW(H, Z, D, T, O, A)
    w.H0[:, 20:40] = 80; w.wild = w.H0 <= 10                  # (cols 20-39 were farmland before; 40+ wilderness)
    w.tick()
    assert (w.O[:, 20:23] == 1).all() and (w.O[:, 26:38] == 0).all() and (w.O[:, 42:] == 1).all()
    print("47 guarded land: emptied farmland beyond 3 tiles of the people falls away (%d tiles); wilderness stays"
          % int((w.O[:, 20:40] == 0).sum()))

    # 48. Resettlement: a government moves people back into emptied land, which then grows back.
    H, Z, D, T, O, A = blank(40, humans=100); H[15:25, 15:25] = 0
    w = DW(H, Z, D, T, O, A); w.H0[:] = 100; w.wild = w.H0 <= 10
    run(w, 40)
    blk = w.H[15:25, 15:25]
    assert int(blk.sum()) > 1500 and (w.O[15:25, 15:25] == 1).mean() > 0.9, (int(blk.sum()), (w.O[15:25, 15:25] == 1).mean())
    print("48 resettled: the emptied district has %d people again on %d of 100 tiles after 40 ticks"
          % (int(blk.sum()), int((blk > 10).sum())))

    # 49. Offensive bases don't hop across the sea; overseas, a government only takes land near what it held.
    H, Z, D, T, O, A = blank(50, humans=0, owner=0)
    T[:, 20:25] = 0; H[:, :20] = 150; O[:, :20] = 1; Z[:, 25:] = 20
    w = DW(H, Z, D, T, O, A, meta={"wrap": False}); w.tick(); civ = w.civs[1]     # (two islands: no wrapping round)
    pick = off2._choose_base(civ, w)
    assert pick is None or pick[1] < 20, pick
    civ.capital = (25, 5)
    ok = w.may_claim(1)
    assert ok[25, 10] and not ok[25, 45]
    print("49 no base across the strait (%s); overseas land is out of reach" % (pick,))

    # 50. Size matters: a big country strikes and sweeps more ground than a small one, and stockpiles more.
    H, Z, D, T, O, A = blank(60, humans=0, owner=0)
    H[:, :24] = 150; O[:, :24] = 1; H[:4, 52:] = 150; O[:4, 52:] = 2; Z[:, 26:50] = 40
    w = DW(H, Z, D, T, O, A); w.tick()
    big, small = w.civs[1], w.civs[2]
    for c in (big, small):
        c.materials = 300.0; c.alert = 1.0; c._purge(w)
    assert big.size(w) > 2 * small.size(w) and big.last_strike > small.last_strike, (big.last_strike, small.last_strike)
    print("50 size: %.2f vs %.2f -> strikes on %d vs %d tiles" % (big.size(w), small.size(w), big.last_strike, small.last_strike))

    # 51. Flights: a country in a zombie emergency grounds most flights from its infected airports.
    def flights(emergency):
        H, Z, D, T, O, A = blank(30, humans=100)
        A = {(5, 5): [(25, 25)], (25, 25): [(5, 5)]}
        w = sim.World(H, Z, D, T, O, A, seed=2, stochastic=True); w.civs[1].peace = not emergency
        n = 0
        for _ in range(300):
            w.Z[5, 5] = 20; w.Z[25, 25] = 0
            engine._airports(w, w.H, w.Z, None)
            n += int(w.Z[25, 25] > 0)
        return n
    f_open, f_grounded = flights(False), flights(True)
    assert f_grounded < 0.7 * f_open, (f_open, f_grounded)
    print("51 flights out of an infected airport: %d of 300 days carried it, %d once the emergency grounds them"
          % (f_open, f_grounded))

    # 52. Nuclear war between countries: a nuclear power that is hit strikes back.
    H, Z, D, T, O, A = blank(60, humans=120); O[:, 30:] = 2
    w = DW(H, Z, D, T, O, A); w.tick()
    for c in w.civs[1:]:
        c.nukes, c.next_decision = 100, 10 ** 9
    keep = nk.RETALIATE
    nk.RETALIATE = 100.0
    try:
        nk.detonate(w, w.civs[1], nk._city_target(w, w.civs[2]), w.civs[2].name)
        run(w, 6)
    finally:
        nk.RETALIATE = keep
    ev = " ".join(e for _, e in w.events)
    assert "IN RETALIATION: Civ 2 hits Civ 1" in ev and war.at_war(w, 1), ev[-400:]
    print("52 nuclear exchange: %s" % [e for _, e in w.events if "RETALIATION" in e][0])

    # 53. Wetlands and rainforest slow zombies down.
    def spread(t):
        H, Z, D, T, O, A = blank(30, humans=0, owner=0); T[:, 10:] = t; Z[:, :10] = 100
        w = DW(H, Z, D, T, O, A)
        run(w, 8)
        return int(w.Z[:, 14:].sum())
    g, rf, wet = spread(1), spread(12), spread(11)
    assert wet < rf < g, (g, rf, wet)
    print("53 zombies 4+ tiles in after 8 ticks: %d on grass, %d in rainforest, %d in wetlands" % (g, rf, wet))

    # 54. Countries that import food keep eating while world shipping runs.
    H, Z, D, T, O, A = blank(30, humans=150); T[:] = 6
    w = DW(H, Z, D, T, O, A); civ = w.civs[1]
    run(w, 80)
    assert civ.import_share > 0.5 and not civ.famine and civ.food > 0
    print("54 a city state imports %.0f%% of its food: %d ticks of food in store after 80 ticks"
          % (100 * civ.import_share, civ.food / civ.food_use))

    # 55. A long war wears a country down, but war weariness alone doesn't topple it.
    H, Z, D, T, O, A = blank(40, humans=100); O[:, 20:] = 2
    w = DW(H, Z, D, T, O, A); w.tick()
    keep = war.PEACE_CHANCE, war.CRISIS
    war.PEACE_CHANCE, war.CRISIS = -1.0, 2.0
    try:
        war.declare(w, 1, 2)
        run(w, 150)
    finally:
        war.PEACE_CHANCE, war.CRISIS = keep
    assert not w.civs[1].collapsed and not w.civs[2].collapsed and min(w.civs[1].morale, w.civs[2].morale) >= 3
    print("55 150 ticks of war: morale %d and %d, both governments stand" % (w.civs[1].morale, w.civs[2].morale))
    # 56. Holdouts: a city about to be overrun sometimes barricades itself - a fort of its government, or a free city.
    import holdouts, fracture as fr
    keep = holdouts.HOLDOUT_CHANCE
    holdouts.HOLDOUT_CHANCE = 1.0
    try:
        for owner in (1, 0):
            H, Z, D, T, O, A = blank(40, humans=150, owner=owner); Z[14:27, 14:27] = 60; Z[19:22, 19:22] = 0
            w = DW(H, Z, D, T, O, A, meta={"cities": [{"name": "Testburg", "row": 20, "col": 20, "pop": 1.0}]})
            w.ticks = 0
            holdouts.step(w)
            held = w.civs[int(w.O[20, 20])]
            assert w.D[20, 20] >= 7 and any(st.get("holdout") for st in held.sites), (owner, w.D[20, 20])
            assert (owner == 1 and held.id == 1) or (owner == 0 and held.name == "Free City of Testburg")
    finally:
        holdouts.HOLDOUT_CHANCE = keep
    print("56 holdouts: a besieged city barricades itself (for its government; or as the %s)" % held.name)

    # 57. Overextension: a big country that has grown fast onto another country's land may split in two.  (Regrowing
    #     over its own land is no reason to fall apart.)
    H, Z, D, T, O, A = blank(60, humans=100); O[:, 30:] = 2
    w = DW(H, Z, D, T, O, A); w.tick(); civ = w.civs[1]; civ.capital = (5, 5)
    w.civs[2].collapsed = True; w.O[:, 30:] = 1; civ.m = civ.observe(w)
    from collections import deque
    civ.long_hist = deque([400] * 12)
    keep = fr.OVEREXTEND_CHANCE
    fr.OVEREXTEND_CHANCE = 100.0
    try:
        w.ticks = fr.OVEREXTEND_EVERY
        fr.overextension(w)
    finally:
        fr.OVEREXTEND_CHANCE = keep
    new = [c for c in w.civs if c.split_from == 1]
    assert new and (w.O == new[0].id).sum() > 300 and w.O[5, 5] == 1
    msg = [e for _, e in w.events if "breaks away" in e][-1]
    # (all of it - capital included - on land that was never its own, in one piece: nothing can break away, and
    #  above all nobody else's land may be touched)
    H, Z, D, T, O, A = blank(60, humans=100); O[:, 40:] = 2
    w = DW(H, Z, D, T, O, A); w.tick(); civ = w.civs[1]; civ.capital = (5, 5); w.O0[:, :40] = 7
    civ.long_hist = deque([300] * 12)
    fr.OVEREXTEND_CHANCE = 100.0
    try:
        w.ticks = fr.OVEREXTEND_EVERY
        fr.overextension(w)
    finally:
        fr.OVEREXTEND_CHANCE = keep
    assert (w.O[:, 40:] == 2).all() and len(w.civs) == 3
    print("57 overextension: %s; a realm in one piece around its capital stays whole" % msg)

    # 58. Stragglers: people slip away from threatened places to far, quiet ones - some of them bitten.
    H, Z, D, T, O, A = blank(80, humans=100); Z[30:50, 0:6] = 80
    w = sim.World(H, Z, D, T, O, A, seed=4, stochastic=True, meta={"wrap": False})
    moved = sum(people.stragglers(w) for _ in range(30))
    far = int(w.Z[:, 14:].sum())
    assert moved > 0 and far > 0, (moved, far)
    print("58 stragglers: %d people struck out on their own; %d of them turned far from the outbreak" % (moved, far))

    # 59. Pioneers: a government settles clean empty land a few tiles beyond its border.
    H, Z, D, T, O, A = blank(60, humans=0, owner=0); H[:, :20] = 100; O[:, :20] = 1
    w = DW(H, Z, D, T, O, A); w.H0[:] = 100; w.wild = w.H0 <= 10
    run(w, 30)
    assert (w.O[:, 24:] == 1).sum() > 50 and int(w.H[:, 20:].sum()) > 1000
    print("59 pioneers: %d tiles settled beyond the old border in 30 ticks" % int((w.O[:, 20:] == 1).sum()))
    # 60. Mountains are a barrier: a horde gets across a range far more slowly than across open country.
    def crossing(t):
        H, Z, D, T, O, A = blank(40, humans=0, owner=0); H[:, 30:] = 100; O[:, 30:] = 0
        T[:, 15:25] = t; Z[:, :8] = 120
        w = DW(H, Z, D, T, O, A, meta={"wrap": False})
        run(w, 25)
        return int(w.Z[:, 25:].sum())
    open_, ridge = crossing(1), crossing(3)
    assert ridge < 0.3 * open_, (open_, ridge)
    print("60 zombies past a 10-tile strip after 25 ticks: %d over open country, %d over mountains" % (open_, ridge))

    # 61. International aid: a safe, strong neighbour sends food and peacekeepers to a country in trouble.
    import aid
    H, Z, D, T, O, A = blank(60, humans=120); O[:, 30:] = 2; Z[:, 50:] = 60
    w = DW(H, Z, D, T, O, A); w.tick()
    a, b = w.civs[1], w.civs[2]
    for c in (a, b):
        c.next_decision = 10 ** 9
    a.military, a.materials, a.strength, a.food = 0.8, 300.0, 0.9, 200 * a.food_use
    b.food = 0.0
    keep = aid.MISSION_CHANCE
    aid.MISSION_CHANCE = 10.0
    try:
        w.ticks = aid.AID_EVERY
        z0 = int(w.Z.sum()); aid.step(w); f1 = b.food
        for _ in range(6):
            w.ticks += aid.SWEEP_EVERY; aid._run_missions(w)
    finally:
        aid.MISSION_CHANCE = keep
    assert w.missions and w.missions[0]["donor"] == 1 and f1 > 0 and a.kills > 0, (w.missions, f1, a.kills)
    print("61 aid: %s; %d zombies killed by the peacekeepers" % ([e for _, e in w.events if "UN" in e][:2], a.kills))

    # 62. Overseas expedition: a big, strong, safe country lands on a lost coast across the sea and may take it back;
    #     land it never had - overseas - may declare independence.
    import expeditions
    n = 60
    H = np.zeros((n, n), int); Z = np.zeros((n, n), int); D = np.full((n, n), 2); T = np.zeros((n, n), int)
    O = np.zeros((n, n), int)
    T[:, :25] = 1; T[:, 40:] = 1; H[:, :25] = 150; O[:, :25] = 1; H[:, 40:] = 30; Z[:, 48:] = 20
    w = sim.World(H, Z, D, T, O, {}, seed=2, stochastic=False, meta={"wrap": False, "ports": [[30, 24, 5]]})
    w.tick(); civ = w.civs[1]; civ.capital = (30, 5); w.pop_ref = 2000.0
    civ.military, civ.strength, civ.materials, civ.alert = 0.8, 0.9, 400.0, 1.0
    assert expeditions.able(w, civ), (civ.ports, civ.size(w), civ.danger(civ.m)[0])
    tgt = expeditions._target(w, civ)
    assert tgt is not None and tgt[1] >= 40
    expeditions.launch(w, civ, *tgt)
    assert w.O[tgt] == 1 and any(b.get("overseas") for b in civ.bases) and w.may_claim(1)[tgt[0], 50]
    run(w, 12)
    held = int(((w.O == 1) & (np.arange(n)[None, :] >= 40)).sum())
    w.Z[:] = 0                                             # (independence is judged on a quiet board)
    keep = fr.INDEPENDENCE_CHANCE
    fr.INDEPENDENCE_CHANCE = 100.0
    try:
        civ.bases = []
        w.O[20:40, 42:48] = 1; w.H[20:40, 42:48] = 80
        w.ticks = fr.INDEPENDENCE_EVERY * 10
        fr.independence(w)
    finally:
        fr.INDEPENDENCE_CHANCE = keep
    ev = " ".join(e for _, e in w.events)
    assert "EXPEDITION" in ev and "declares independence" in ev, ev[-300:]
    print("62 expedition: %s; %d tiles held across the strait; then it declared independence"
          % ([e for _, e in w.events if "EXPEDITION" in e][0], held))

    # 63. The Beleriand map: Angband's outbreak, the alliances as they were (Feanor's sons and Doriath are no allies),
    #     Melian's Girdle round Doriath, the Siege's wars, the calendar of the First Age.
    w = sim.World.from_folder("maps/beleriand", stochastic=False)
    ids = {c.name: c.id for c in w.civs}
    meta = json.load(open("maps/beleriand/meta.json", encoding="utf-8"))
    r, c = meta["patient_zero"]
    assert w.civs[int(w.O[r, c])].name == "Angband" and w.Z.sum() > 0 and not w.airports
    hith, narg, dor, himr = (ids["Hithlum (Fingolfin)"], ids["Nargothrond (Finrod)"], ids["Doriath (Thingol)"],
                             ids["Himring (Maedhros)"])
    assert war.allied(w, hith, narg) and war.allied(w, himr, ids["Thargelion (Caranthir)"])
    assert not war.allied(w, dor, himr) and war.key(dor, himr) in w.rivals
    assert not war.allied(w, ids["Gondolin"], hith) and war.key(ids["Angband"], hith) in w.wars
    girdle = max(w.civs[dor].sites, key=lambda s: len(s["tiles"]))
    assert len(girdle["tiles"]) > 60 and girdle["level"] == 6 and girdle.get("standing")
    assert w.datestr() == "12/21/455"
    sizes = {nm: int((w.O == k).sum()) for nm, k in ids.items() if k}
    assert min(sizes.values()) > 20 and sizes["Angband"] > 1000
    print("63 Beleriand: %d realms, outbreak in %s on %s; Girdle of %d tiles; Doriath and Himring are rivals"
          % (len(w.civs) - 1, meta["outbreak"], w.datestr(), len(girdle["tiles"])))

    # 64. Middle-earth's towns and fiefs are realms of their own, allied with their overlords; realms aren't boxes.
    w = sim.World.from_folder("maps/middle_earth", stochastic=False)
    ids = {c.name: c.id for c in w.civs}
    for fief, lord in (("Dol Amroth", "Gondor"), ("Westfold", "Rohan"), ("Esgaroth", "Dale"), ("Buckland", "The Shire"),
                       ("Harondor", "Harad")):
        assert (w.O == ids[fief]).sum() > 10 and war.allied(w, ids[fief], ids[lord]), fief
    fill = {}
    for name in ("Lothlorien", "Moria", "Rivendell", "Gondor"):
        rr, cc = np.nonzero(w.O == ids[name])
        box = (rr.max() - rr.min() + 1) * (cc.max() - cc.min() + 1)
        fill[name] = rr.size / box
        assert fill[name] < 0.8, (name, rr.size, box)
    print("64 Middle-earth: %d realms; Dol Amroth, the Westfold, Lake-town ... allied with their lords; Lothlorien fills"
          " %d%% of its bounding box, Moria %d%%" % (len(w.civs) - 1, 100 * fill["Lothlorien"], 100 * fill["Moria"]))

    # 65. Numbers on screen stand for the real population: k, m, b with one decimal.
    assert [sim.fmt_people(v) for v in (950, 12345, 4.5e6, 1.234e9)] == ["950", "12.3k", "4.5m", "1.2b"]
    w = sim.World.from_folder("maps/world_lite", stochastic=False)
    shown = {r["name"]: r["shown"] for r in w.summary()}
    assert 7.0e9 < w.shown(w.H) < 8.5e9 and shown["India"] > 1e9 and 1e8 < shown["Russia"] < 2e8
    print("65 display: the world's %d map people shown as %s; India %s, Russia %s" % (
        int(w.H.sum()), sim.fmt_people(w.shown(w.H)), sim.fmt_people(shown["India"]), sim.fmt_people(shown["Russia"])))

    # 66. Refugees who go far head for cities: arrivals 30+ tiles away are at (or right next to) a city.
    H, Z, D, T, O, A = blank(150, humans=60); Z[70:80, 0:6] = 120
    w = sim.World(H, Z, D, T, O, A, seed=5, stochastic=True, meta={"wrap": False})
    w.cities = [("Far City", 75, 45, 2.0), ("Other", 40, 50, 0.5)]
    h0 = w.H.copy()
    for _ in range(60):
        people.stragglers(w)
    gained = np.argwhere((w.H + w.Z > h0) & (np.arange(150)[None, :] >= 30))
    near_city = [abs(r - cr) <= 1 and abs(c - cc) <= 1 for r, c in gained for _, cr, cc, _ in w.cities]
    assert len(gained) > 0 and sum(near_city) == len(gained), gained[:10]
    print("66 long-distance stragglers: %d places 30+ tiles from the outbreak took some in - all at cities"
          % len(gained))

    # 67. The turning point: a government that keeps fighting adapts; zombies far from people waste away.
    import resolve
    H, Z, D, T, O, A = blank(30, humans=100)
    w = DW(H, Z, D, T, O, A); w.tick()
    civ = w.civs[1]
    civ.m = dict(zone_z=500, pop=1000, growth=-0.05); civ.peak_pop = 1000; civ.morale = 5
    for _ in range(30):                                   # (nobody adapts in the first weeks of the outbreak)
        resolve.step(w)
    assert getattr(civ, "resolve", 0.0) == 0.0
    w.ticks = resolve.ADAPT_START
    for _ in range(70):
        resolve.step(w)
    assert civ.resolve > 0.6 and civ.turned and civ.morale == 5 + resolve.TURN_MORALE and any("TURNING POINT" in e for _, e in w.events)
    r_top = civ.resolve
    civ.m = dict(zone_z=0, pop=1000, growth=0.0)
    for _ in range(50):
        resolve.step(w)
    assert civ.resolve < r_top - 0.1
    H2, Z2, D2, T2, O2, A2 = blank(40, humans=0, owner=0); Z2[:] = 50
    w2 = DW(H2, Z2, D2, T2, O2, A2); w2.ticks = resolve.ADAPT_START
    z0 = int(w2.Z.sum()); run(w2, 50)
    assert int(w2.Z.sum()) < 0.9 * z0, (z0, int(w2.Z.sum()))
    print("67 turning point reached after ~60 days of fighting (resolve fades to %.2f in peace); starving horde %d -> %d in 50 days"
          % (civ.resolve, z0, int(w2.Z.sum())))
    # 68. A country holding a big conquest (twice its own land, of a fallen neighbour) may lose it: the conquered
    #     country rises up along its old borders.
    import fracture
    H, Z, D, T, O, A = blank(60, humans=100)
    O[:, 20:] = 2
    w = DW(H, Z, D, T, O, A); w.tick()
    a, b = w.civs[1], w.civs[2]
    b.collapsed = True; w.O[:, 20:] = 1; w.ticks = 30
    a.m = a.observe(w); a.long_hist.extend([1200] * 10)
    keep = fracture.OVEREXTEND_CHANCE; fracture.OVEREXTEND_CHANCE = 10.0
    try:
        fracture.overextension(w)
    finally:
        fracture.OVEREXTEND_CHANCE = keep
    new = w.civs[-1]
    assert len(w.civs) == 4 and (w.O[:, :20] == 1).all() and (w.O[:, 20:] == new.id).sum() > 1000
    print("68 conquest: %s" % [e for _, e in w.events if "breaks away" in e][0])

    # 69. Reaches are round and ragged, not boxes: what's within 6 steps of one tile.
    H, Z, D, T, O, A = blank(40, humans=100)
    w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True)
    one = np.zeros((40, 40), dtype=bool); one[20, 20] = True
    m = C.within(w, one, 6)
    corners = m[14, 14] + m[14, 26] + m[26, 14] + m[26, 26]
    assert m[20, 14] or m[20, 15], "reach too short"
    assert corners <= 1 and m.sum() < 0.85 * 13 * 13, (int(corners), int(m.sum()))
    print("69 a reach of 6: %d tiles (a box would be 169), %d of 4 corners" % (int(m.sum()), int(corners)))
    # 70. Settlers: a country doing well sends a group to once-settled, empty, clean land far away; they found a state.
    import settlers
    H, Z, D, T, O, A = blank(80, humans=0, owner=0)
    H[:, :20] = 150; O[:, :20] = 1
    w = DW(H, Z, D, T, O, A); w.H0[:, 50:] = 120; w.tick()
    a = w.civs[1]; a.materials = 200.0; a.morale = 9; a.capital = (40, 5)
    a.m = a.observe(w)
    w.ticks = settlers.SETTLE_EVERY * 5
    keep = settlers.SETTLE_CHANCE; settlers.SETTLE_CHANCE = 10.0
    try:
        settlers.step(w)
    finally:
        settlers.SETTLE_CHANCE = keep
    new = w.civs[-1]
    assert new.id != 1 and new.split_from == 1 and new.root == new.id and (w.O == new.id).sum() >= 1
    r, c = new.capital
    assert c >= 50 and w.H[r, c] > 10, (r, c)
    print("70 settlers: %s" % [e for _, e in w.events if "settlers" in e][0])

    # 71. A quiet province of a falling country becomes a state of its own (not anarchy), named after its biggest city;
    #     two new states never share a city's name.
    H, Z, D, T, O, A = blank(60, humans=60)
    Z[:, :8] = 200
    w = DW(H, Z, D, T, O, A); w.tick()
    w.cities = [("Small Town", 50, 50, 0.1), ("Big City", 45, 40, 5.0), ("Bigtown North", 10, 40, 2.0)]
    civ = w.civs[1]
    region = np.zeros((60, 60), dtype=bool); region[40:60, 30:60] = True
    s1 = fracture._new_state(w, civ, region)
    region2 = np.zeros((60, 60), dtype=bool); region2[5:20, 30:60] = True
    s2 = fracture._new_state(w, civ, region2)
    assert "Big City" in s1.name and s1.capital == (45, 40) and "Bigtown North" in s2.name, (s1.name, s2.name)
    small = np.zeros((60, 60), dtype=bool); small[25:30, 50:56] = True
    assert fracture._viable(w, small) and not fracture._viable(w, small & False)
    print("71 new states: %s (capital at its biggest city), %s; a quiet 30-tile province can organize" % (s1.name, s2.name))

    # 72. A region with no town of its own is named after the land it belonged to, never after a city another living
    #     government holds; settlers' colonies keep their distance from each other.
    H, Z, D, T, O, A = blank(60, humans=60)
    O[:, 30:] = 2
    w = DW(H, Z, D, T, O, A); w.tick()
    w.civs[1].name, w.civs[2].name = "Rhun", "Mordor"
    w.cities = [("Barad-dur", 30, 35, 5.0)]
    east = np.zeros((60, 60), dtype=bool); east[20:40, 22:30] = True
    s3 = fracture._new_state(w, w.civs[1], east)
    assert "Barad-dur" not in s3.name and "East Rhun" in s3.name, s3.name
    H, Z, D, T, O, A = blank(120, humans=0, owner=0)
    H[:, :20] = 150; O[:, :20] = 1
    w = DW(H, Z, D, T, O, A); w.H0[:, 40:] = 120; w.tick()
    a = w.civs[1]; a.materials = 5000.0; a.morale = 9; a.capital = (60, 5)
    a.m = a.observe(w)
    keep = settlers.SETTLE_CHANCE, settlers.SETTLE_LAND_REACH; settlers.SETTLE_CHANCE = 10.0
    settlers.SETTLE_LAND_REACH = 1000.0
    try:
        for k in range(5, 10):
            w.ticks = settlers.SETTLE_EVERY * k
            a.m = a.observe(w); a.morale = 9; a.materials = 5000.0
            settlers.step(w)
    finally:
        settlers.SETTLE_CHANCE, settlers.SETTLE_LAND_REACH = keep
    caps = [c.capital for c in w.civs[2:] if c.capital is not None]
    gaps = [np.hypot(p[0] - q[0], p[1] - q[1]) for i, p in enumerate(caps) for q in caps[i + 1:]]
    assert len(caps) >= 2 and min(gaps) >= settlers.SETTLE_SPACING, (caps, gaps)
    print("72 %s (no town of its own; Barad-dur is Mordor's); %d settler colonies at least %.0f tiles apart"
          % (s3.name, len(caps), min(gaps)))
    # 73. A country split between two cities falls apart along the lie of the land: never a straight line, and along a
    #     mountain range where there is one.
    H, Z, D, T, O, A = blank(60, humans=100)
    w = DW(H, Z, D, T, O, A)
    part = np.ones((60, 60), dtype=bool)
    lab = fracture.split_by_ground(w, part, [(30, 12), (30, 48)])
    edge = [int(np.argmax(lab[r] == 1)) for r in range(60)]
    assert max(edge) - min(edge) >= 3 and len(set(edge)) >= 4, edge             # ragged, not a straight line
    H, Z, D, T, O, A = blank(60, humans=100); T[:, 38:41] = 3
    w = DW(H, Z, D, T, O, A)
    lab = fracture.split_by_ground(w, part, [(30, 12), (30, 52)])
    edge2 = [int(np.argmax(lab[r] == 1)) for r in range(60)]
    assert sum(36 <= e <= 42 for e in edge2) >= 50, edge2                      # along the ridge
    print("73 border between two cities: columns %d-%d on open ground; %d of 60 rows along a mountain ridge"
          % (min(edge), max(edge), sum(36 <= e <= 42 for e in edge2)))

    # 74. Wilderness nobody ever lived on (desert) is claimed by its neighbour without settlers; emptied farmland is
    #     only taken where the nation's people can guard it (its edge).
    import restart

    def claimed(h0_beyond, terrain):
        H, Z, D, T, O, A = blank(60, humans=0, owner=0)
        H[:, :20] = 120; O[:, :20] = 1; T[:, 20:] = terrain
        w = DW(H, Z, D, T, O, A); w.H0[:, 20:] = h0_beyond; w.refresh_wild(); w.tick()
        w.H[:, 20:] = 0; w.O[:, 20:] = 0
        for k in range(40):
            w.ticks = restart.EXPAND_EVERY * (k + 10)
            w.civs[1].morale = 9
            restart.expand(w)
        return int((w.O[:, 20:] == 1).sum())
    wild, farm = claimed(0, 4), claimed(80, 1)
    assert wild >= 200 and farm < wild, (wild, farm)
    print("74 in 160 days a nation claims %d tiles of desert nobody lived on, but only %d of emptied farmland"
          % (wild, farm))

    # 75. A horde far from anyone (70 tiles) tracks people from afar instead of milling about.
    import zombies as zb
    H, Z, D, T, O, A = blank(100, humans=0, owner=0)
    H[:, 92:] = 100; Z[45:55, 15:25] = 60
    w = DW(H, Z, D, T, O, A, meta={"wrap": False})
    c0 = float((np.arange(100)[None, :] * w.Z).sum() / w.Z.sum())
    for k in range(150):
        w.ticks = k
        zb.far_hunt(w)
    c1 = float((np.arange(100)[None, :] * w.Z).sum() / w.Z.sum())
    assert c1 > c0 + 10, (c0, c1)
    print("75 a horde 70 tiles from people moves toward them: centre column %.0f -> %.0f in 150 days" % (c0, c1))

    # 76. No supercountries by merger: two unrelated states too big together stay apart.
    import union
    H, Z, D, T, O, A = blank(60, humans=90); O[:, 30:] = 2
    w = DW(H, Z, D, T, O, A); w.tick()
    for c in w.civs[1:3]:
        c.successor = True; c.root = c.id; c.morale = 9; c.split_from = None
    w.O0[:] = 0
    keep = union.STRANGER_CHANCE, union.MERGE_MAX_TILES
    union.STRANGER_CHANCE = 10.0
    try:
        union.MERGE_MAX_TILES = 1000                       # (1800 + 1800 populated tiles: too big)
        w.ticks = union.MERGE_EVERY * 50; union.step(w)
        assert not any(c.collapsed for c in w.civs[1:3])
        union.MERGE_MAX_TILES = 5000
        union.step(w)
        assert sum(c.collapsed for c in w.civs[1:3]) == 1
    finally:
        union.STRANGER_CHANCE, union.MERGE_MAX_TILES = keep
    print("76 two unrelated states of 1800 populated tiles each: no merger above the cap, merged below it")
    # 77. Now and then a big horde on a coast sends a chunk of itself across the water to the next landmass - and
    #     you can see it swimming.
    import crossings
    H, Z, D, T, O, A = blank(40, humans=0, owner=0)
    T[:, 17:23] = 0                                       # a strait 6 tiles wide
    H[:, 23:] = 80; O[:, 23:] = 1
    Z[15:25, 10:17] = 120
    w = DW(H, Z, D, T, O, A, meta={"wrap": False})
    keep = crossings.CROSS_CHANCE, crossings.CROSS_EVERY
    crossings.CROSS_CHANCE, crossings.CROSS_EVERY = 10.0, 1
    seen_at_sea = 0
    try:
        for k in range(12):
            w.ticks = k
            crossings.step(w)
            seen_at_sea = max(seen_at_sea, len(crossings.at_sea(w)))
    finally:
        crossings.CROSS_CHANCE, crossings.CROSS_EVERY = keep
    landed = int(w.Z[:, 23:].sum())
    assert seen_at_sea >= 4 and landed > 0, (seen_at_sea, landed)
    print("77 a horde crossed a 6-tile strait: %d tiles of it seen at sea, %d zombies came ashore" % (seen_at_sea, landed))
    # 78. A settlers' colony on emptied land grows: its people have children and spread over the land around it.
    H, Z, D, T, O, A = blank(80, humans=0, owner=0)
    H[:, :12] = 150; O[:, :12] = 1
    w = DW(H, Z, D, T, O, A); w.H0[:, 40:] = 90; w.tick()
    a = w.civs[1]; a.materials = 200.0; a.morale = 9; a.capital = (40, 5); a.m = a.observe(w)
    colony = settlers.found(w, a, 40, 60)
    lived0 = int(((w.O == colony.id) & (w.H > 10)).sum())
    for _ in range(200):
        w.tick()
    lived1 = int(((w.O == colony.id) & (w.H > 10)).sum())
    assert not colony.collapsed and lived1 >= 3 * lived0, (lived0, lived1)
    print("78 a settlers' colony (%s) grew from %d to %d lived-on tiles in 200 days" % (colony.name, lived0, lived1))
    # 79. Hordes choose their prey: a big city 60 tiles off over a small village half as far - and march on it as
    #     one body (coordination 0.8); with coordination 0 they don't march at all.
    import hordes

    def horde_world(coord):
        H, Z, D, T, O, A = blank(120, humans=0, owner=0)
        H[55:65, 100:110] = 200; H[20:22, 30:32] = 40
        Z[50:70, 20:35] = 9; Z[55:65, 25:30] = 60
        w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
        w.coordination = coord
        for k in range(60):
            w.ticks = k
            hordes.step(w)
        Zf = w.Z.astype(float)
        return w, float((np.arange(120)[None, :] * Zf).sum() / Zf.sum())
    w, col = horde_world(0.8)
    _, col0 = horde_world(0.0)
    hp = w._horde_plan
    k, (gR, gC) = hp["k"], hp["shape"]
    rr, cc = np.nonzero(w.Z >= hordes.HORDE_Z)
    t = hp["prey"][np.minimum(rr // k, gR - 1), np.minimum(cc // k, gC - 1)]
    goal_col = (int(np.bincount(t[t >= 0]).argmax()) % gC + 0.5) * k
    assert goal_col > 90 and col > 38 and col0 < 30, (goal_col, col, col0)
    print("79 the horde went for the big city (target column %d): its centre moved from column 27 to %.0f in 60 days "
          "(%.0f with coordination 0)" % (goal_col, col, col0))

    # 80. A dense horde (255 a tile) moves as a body: room in a tile counts the zombies leaving it at the same time.
    import zombies as zb
    H, Z, D, T, O, A = blank(30, humans=0, owner=0)
    Z[10:20, 5:15] = 255
    w = DW(H, Z, D, T, O, A, meta={"wrap": False})
    rr, cc = np.nonzero(w.Z > 0)
    moved = zb.transport(w, rr, cc, rr, cc + 1, w.Z[rr, cc].astype(np.int64))
    assert moved == 255 * 100 and (w.Z[10:20, 6:16] == 255).all(), moved
    print("80 a block of 100 tiles at 255 zombies each moved one tile east as a whole (%d zombies)" % moved)
    # 81. An island eaten bare doesn't keep its zombies: they take to the sea and head for other land.
    H, Z, D, T, O, A = blank(60, humans=0, owner=0)
    T[:, :] = 0; T[10:20, 5:15] = 1; T[:, 25:] = 1
    H[:, 30:] = 80; O[:, 30:] = 1; Z[10:20, 5:15] = 30
    w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
    z0 = int(w.Z[10:20, 5:15].sum())
    for k in range(40):
        w.ticks = k
        crossings.step(w)
    left, landed = int(w.Z[10:20, 5:15].sum()), int(w.Z[:, 25:].sum())
    assert left < 0.4 * z0 and landed > 0, (z0, left, landed)
    print("81 an island nobody lives on any more: %d of its %d zombies left it by sea in 40 days, %d came ashore "
          "on the mainland so far" % (z0 - left, z0, landed))
    # 82. A horde crosses a strait to another country even when the two are one landmass (the Channel).
    H, Z, D, T, O, A = blank(60, humans=0, owner=0)
    T[0:40, 25:30] = 0
    O[:, :25] = 1; O[:, 30:] = 2; H[:, 32:] = 80; Z[10:25, 15:25] = 120
    w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
    keep = crossings.CROSS_CHANCE, crossings.CROSS_EVERY
    crossings.CROSS_CHANCE, crossings.CROSS_EVERY = 10.0, 1
    try:
        for k in range(20):
            w.ticks = k
            crossings.step(w)
    finally:
        crossings.CROSS_CHANCE, crossings.CROSS_EVERY = keep
    across = int(w.Z[:40, 30:].sum())
    assert across > 0, across
    print("82 hordes crossed a strait between two countries of one landmass: %d zombies came ashore" % across)
    # 83. Forms of government follow from where a state comes from: a democracy's safe, fed cities become a republic; a
    #     fragile state's starving region falls to warlords and its empty countryside to clans; an authoritarian
    #     state's garrisoned region in danger becomes a junta.
    import govern

    def new_gov(name, H_val, T_val, famine=False, sites=0, army=0.3, zombies=0):
        H, Z, D, T, O, A = blank(30, humans=H_val)
        T[:, :] = T_val
        Z[:, :] = zombies
        w = DW(H, Z, D, T, O, A, meta={"wrap": False, "real_pops": {"1": 1}})
        c = w.civs[1]
        c.name = c.name0 = name
        c.famine, c.military = famine, army
        c.food, c.food_use = (0.0, 1.0) if famine else (1000.0, 1.0)
        return govern.choose(w, np.ones((30, 30), dtype=bool), c, sites=sites)
    got = (new_gov("Germany", 150, 6), new_gov("Somalia", 40, 1, famine=True), new_gov("Somalia", 3, 4),
           new_gov("Russia", 120, 1, sites=3, army=0.9, zombies=40))
    assert got == ("democracy", "warlord", "tribal", "junta"), got
    print("83 new states: Germany's safe cities -> %s, Somalia's starving region -> %s, its empty desert -> %s, "
          "Russia's garrisoned region under attack -> %s" % got)
    # 84. Hordes don't swim across a lake (the Sea of Rhun) - not even to another country's shore: they walk round.
    H, Z, D, T, O, A = blank(60, humans=0, owner=0)
    T[10:40, 25:30] = 0; T[:, 55:] = 0                     # (a lake, and the ocean at the edge of the map)
    O[:, :25] = 1; O[:, 30:55] = 2; H[:, 32:55] = 80; Z[10:25, 15:25] = 120
    w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
    assert crossings.lakes(w)[20, 27] and not crossings.lakes(w)[20, 57]
    assert crossings._route(w, 20, 24) is None
    keep = crossings.CROSS_CHANCE, crossings.CROSS_EVERY
    crossings.CROSS_CHANCE, crossings.CROSS_EVERY = 10.0, 1
    try:
        for k in range(20):
            w.ticks = k
            crossings.step(w)
    finally:
        crossings.CROSS_CHANCE, crossings.CROSS_EVERY = keep
    assert not w.crossings and int(w.Z[:40, 30:55].sum()) == 0
    print("84 no horde swam across the lake to the other country's shore")
    # 85. A swimming horde doesn't land on a rock smaller than itself: only on land big enough (LANDING_MIN).
    def coast_world(island):
        H, Z, D, T, O, A = blank(60, humans=0, owner=0)
        T[:, :] = 0; T[:, :15] = 1
        T[28:28 + island, 25:25 + island] = 1
        Z[25:35, 10:15] = 120
        return sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
    assert crossings._route(coast_world(3), 30, 14) is None
    path = crossings._route(coast_world(8), 30, 14)
    assert path is not None and coast_world(8).statics.land[path[-1]]
    print("85 a 3x3 rock is no landing; an 8x8 island is (landing %s)" % (path[-1],))
    # 86. When a horde moves on to a bigger prize, part of it stays to finish off the village it was eating.
    def stay_world(share):
        keep_ = hordes.STAY_RATIO
        hordes.STAY_RATIO = share
        try:
            H, Z, D, T, O, A = blank(120, humans=0, owner=0)
            H[55:65, 100:110] = 220; H[56:60, 12:16] = 60
            Z[50:70, 20:35] = 40
            w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
            for k in range(30):
                w.ticks = k
                hordes.step(w)
        finally:
            hordes.STAY_RATIO = keep_
        return int(w.Z[45:70, 0:20].sum()), int(w.Z[:, 40:].sum())
    near0, far0 = stay_world(0.0)
    near1, far1 = stay_world(hordes.STAY_RATIO)
    assert near1 > 3 * max(near0, 1) and far1 > 0.3 * far0, (near0, near1, far0, far1)
    print("86 part of the horde stayed at the village (%d zombies there, %d if all moved on) while the rest marched "
          "on the city (%d)" % (near1, near0, far1))
    # 87. A horde swimming to a fortified shore doesn't just evaporate: it bites people as it comes ashore.
    H, Z, D, T, O, A = blank(60, humans=0, owner=0)
    T[:, 20:30] = 0
    O[:, :20] = 1; O[:, 30:] = 2; H[:, 30:] = 120; D[:, 30:] = 7; Z[20:35, 10:20] = 150
    w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
    h0 = int(w.H[:, 30:].sum())
    keep = crossings.CROSS_CHANCE, crossings.CROSS_EVERY
    crossings.CROSS_CHANCE, crossings.CROSS_EVERY = 10.0, 1
    try:
        for k in range(30):
            w.ticks = k
            crossings.step(w)
    finally:
        crossings.CROSS_CHANCE, crossings.CROSS_EVERY = keep
    bitten = h0 - int(w.H[:, 30:].sum())
    assert w._cross_log and bitten > 0, bitten
    print("87 hordes landing on a fortified shore bit %d people as they came ashore" % bitten)
    # 88. A fresh landing isn't shelled flat: for crossings.SURPRISE_DAYS the country's strikes can't find it.
    def strike(landed):
        H, Z, D, T, O, A = blank(40, humans=100)
        Z[18:22, 18:22] = 120
        w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
        w.tick()
        c = w.civs[1]; c.materials, c.alert = 500.0, 1.0
        if landed:
            w._cross_log = [(w.ticks, 20, 20)]
        z0 = int(w.Z[18:22, 18:22].sum()); c._purge(w)
        return z0 - int(w.Z[18:22, 18:22].sum())
    hit_open, hit_landed = strike(False), strike(True)
    assert hit_open > 0 and hit_landed == 0, (hit_open, hit_landed)
    print("88 strikes killed %d zombies of an old cluster, %d of a fresh landing (not found yet)" % (hit_open, hit_landed))
    # 89. Villages: people nobody governs go off in small groups and settle clean, empty land a few tiles away.
    import restart
    H, Z, D, T, O, A = blank(60, humans=0, owner=0)
    H[28:32, 5:9] = 80
    w = sim.World(H, Z, D, T, O, A, seed=3, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.H0[:, :] = 50                                         # (once-settled land all round)
    for k in range(60):
        w.ticks = k * restart.VILLAGE_EVERY + 2
        restart.villages(w)
    lived = np.argwhere(w.H > 0)
    far = [(int(r), int(c)) for r, c in lived if not (28 <= r < 32 and 5 <= c < 9)]
    assert len(far) >= 3 and w.villages_founded >= 3 and (w.O == 0).all(), (far, w.villages_founded)
    print("89 %d villages founded by people nobody governs, e.g. at %s" % (w.villages_founded, far[:3]))
    # 90. Land use: a country rebuilding in peace clears forest next to its fields and builds suburbs round its town;
    #     an empty city falls into ruin.
    import landuse
    from terrain import FOREST as TF, URBAN as TU, SUBURBAN as TS, GRASS as TG
    H, Z, D, T, O, A = blank(40, humans=110)
    T[:, 30:] = TF; H[:, 30:] = 20
    T[18:21, 10:13] = TU; H[18:21, 10:13] = 220
    T[2:5, 2:5] = TU; H[2:5, 2:5] = 0; O[2:5, 2:5] = 0          # (a dead city)
    w = sim.World(H, Z, D, T, O, A, seed=2, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.tick(); c = w.civs[1]; c._worst_damage = 0.5
    sub0, wood0 = int((w.T == TS).sum()), int((w.T == TF).sum())
    for k in range(40):
        w.ticks = (k + 1) * landuse.EVERY
        w.H[:, :30] = np.maximum(w.H[:, :30], 110)
        w.H[2:5, 2:5] = 0
        landuse.step(w)
    assert (w.T == TS).sum() > sub0 and (w.T == TF).sum() < wood0 and (w.T[2:5, 2:5] != TU).all(), (
        int((w.T == TS).sum()), int((w.T == TF).sum()))
    print("90 land use: %d suburbs built, %d forest tiles cleared, the dead city fell into ruin"
          % (int((w.T == TS).sum()) - sub0, wood0 - int((w.T == TF).sum())))
    # 91. An emptied continent fills fast: a government with no zombies about sends its pioneers far beyond its border.
    def pioneers(calm):
        H, Z, D, T, O, A = blank(60, humans=0, owner=0)
        H[:, :10] = 120; O[:, :10] = 1
        if not calm:
            Z[0, 59] = 200                                   # (a horde far off - but in its region)
        w = sim.World(H, Z, D, T, O, A, seed=4, stochastic=True, meta={"wrap": False, "res": 0.5})
        w.H0[:, :] = 60
        for _ in range(60):
            w.Z[0, 59] = 0 if calm else 200
            w.tick()
        cols = np.nonzero((w.H > 10).any(axis=0))[0]
        return int(cols.max())
    far_calm, far_busy = pioneers(True), pioneers(False)
    assert far_calm > far_busy, (far_calm, far_busy)
    print("91 settled out to column %d with no zombies about (%d with a horde in the region)" % (far_calm, far_busy))
    # 92. War beyond the border: raids on towns, partisans in taken rough country, a landing from the sea.
    import warfare
    H, Z, D, T, O, A = blank(40, humans=120); O[:, 20:] = 2
    T[:, 26:30] = 2                                          # (woods on 2's side)
    w = DW(H, Z, D, T, O, A); w.tick()
    for c in w.civs[1:]: c.next_decision = 10 ** 9
    war.declare(w, 1, 2); wr = next(iter(w.wars.values()))
    a, b_ = w.civs[1], w.civs[2]
    a.military, a.materials, b_.materials = 0.9, 50.0, 50.0
    a.traits["aggression"] = 100.0
    h0, m0 = int(w.H[:, 20:].sum()), a.materials
    keep = warfare.RAID_CHANCE
    warfare.RAID_CHANCE = 10.0                               # (the raid itself, not the dice)
    try:
        warfare._raid(w, wr, a, b_)
    finally:
        warfare.RAID_CHANCE = keep
    assert int(w.H[:, 20:].sum()) < h0 and a.materials > m0
    w.O[:, 26:30] = 1                                        # (1 has taken the woods)
    wr["taken"] = {1: list(np.flatnonzero((w.O == 1).ravel() & (w.T == 2).ravel()))}
    w.stochastic = True
    for _ in range(60):
        warfare._guerrillas(w, wr)
    back = int((w.O[:, 26:30] == 2).sum())
    assert back > 0, back
    H, Z, D, T, O, A = blank(40, humans=120); T[:, 15:25] = 0; O[:, 25:] = 2; H[:, 15:25] = 0; O[:, 15:25] = 0
    w = sim.World(H, Z, D, T, O, A, seed=5, stochastic=True, meta={"wrap": False, "res": 0.5, "ports": [[20, 14, 5]]})
    w.tick()
    for c in w.civs[1:]: c.next_decision = 10 ** 9
    war.declare(w, 1, 2); wr = next(iter(w.wars.values()))
    a = w.civs[1]; a.military, a.materials = 0.9, 100.0; a.traits["aggression"] = 100.0
    warfare._landing(w, wr, a, w.civs[2])
    head = int((w.O[:, 25:] == 1).sum())
    assert head > 0, head
    print("92 a raid on a town carried off stores; partisans took back %d wooded districts; a landing took a "
          "beachhead of %d districts" % (back, head))
    # 93. A state with no town of its own is named after a free town nearby, not "North Somewhere".
    import govern
    H, Z, D, T, O, A = blank(40, humans=100, owner=0)
    w = DW(H, Z, D, T, O, A, meta={"wrap": False})
    w.cities = [("Smallbridge", 20, 30, 0.1)]
    region = np.zeros((40, 40), dtype=bool); region[18:23, 18:23] = True
    nm = govern.state_name(w, "democracy", region, 1)
    assert nm == "Republic of Smallbridge", nm
    print("93 a townless state next to Smallbridge is the %s" % nm)
    # 94. Zombies hold land they have taken near people: thin groups there don't march off after a far prize.
    import hordes
    H, Z, D, T, O, A = blank(80, humans=0, owner=0)
    H[:, 70:] = 200; H[30:40, 5:10] = 60                    # (a far city; and a town nearby)
    w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.H0[25:45, 10:25] = 50                                 # (land lived on before, empty now)
    w.Z[30:40, 15:20] = 30
    z0 = int(w.Z[25:45, 10:25].sum())
    for k in range(30):
        w.ticks = k
        hordes.step(w)
    kept = int(w.Z[25:45, 10:25].sum())
    assert kept >= 0.8 * z0, (kept, z0)
    print("94 zombies holding taken land near a town: %d of %d stayed" % (kept, z0))
    # 95. Motives: a stable, secure country never has a revolution; one coming apart (riots, famine, morale broken)
    #     does - and a secure, ambitious one is the one that looks abroad.
    import motives, globalaffairs
    def revolts(unstable):
        H, Z, D, T, O, A = blank(40, humans=100)
        w = sim.World(H, Z, D, T, O, A, seed=7, stochastic=True, meta={"wrap": False, "res": 0.5})
        w.tick(); c = w.civs[1]
        for k in range(60):
            if unstable:
                c.morale, c.famine = 2, True
                w.U[:, :] = 1.5
            w.ticks = (k + 1) * globalaffairs.EVERY
            motives.update(w)
            globalaffairs._revolutions(w, [c])
        return sum(1 for _, e in w.war_log if "REVOLUTION" in e), motives.instability(c)
    (calm_n, calm_i), (bad_n, bad_i) = revolts(False), revolts(True)
    assert calm_n == 0 and bad_n >= 1 and bad_i > calm_i, (calm_n, calm_i, bad_n, bad_i)
    H, Z, D, T, O, A = blank(40, humans=100)
    w = DW(H, Z, D, T, O, A); w.tick(); c = w.civs[1]
    c.military, c.materials, c.morale = 0.9, 200.0, 9
    c.gov, c.traits["aggression"] = "junta", 1.3
    amb_junta = motives.ambition(w, c)
    c.gov, c.traits["aggression"], c.military = "democracy", 0.8, 0.4
    amb_rep = motives.ambition(w, c)
    assert amb_junta > amb_rep, (amb_junta, amb_rep)
    print("95 revolutions: %d in a stable country (instability %.2f), %d in one coming apart (%.2f); ambition: "
          "secure junta %.2f vs cautious republic %.2f" % (calm_n, calm_i, bad_n, bad_i, amb_junta, amb_rep))
    # 96. A peace holds: two countries that just made peace don't go to war again straight away.
    H, Z, D, T, O, A = blank(40, humans=100); O[:, 20:] = 2
    w = DW(H, Z, D, T, O, A); w.tick()
    war.declare(w, 1, 2, "test"); war.end(w, war.key(1, 2), "truce against the zombies")
    war.declare(w, 1, 2, "again")
    assert war.key(1, 2) not in w.wars
    w.ticks += war.TRUCE_HOLDS + 1
    war.declare(w, 1, 2, "later")
    assert war.key(1, 2) in w.wars
    print("96 no new war within %d days of a truce; war again after it" % war.TRUCE_HOLDS)
    # 97. Organized crime: pirates take root in coastal anarchy and raid a country's coast across the water;
    #     a strong, secure country cracks down.
    import crime
    H, Z, D, T, O, A = blank(60, humans=120, owner=0)
    T[:, 25:35] = 0; H[:, 25:35] = 0                        # (a strait)
    O[:, 35:] = 1
    w = sim.World(H, Z, D, T, O, A, seed=11, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.cities = [("Tortuga", 30, 23, 1.0), ("Port Royal", 30, 40, 1.0)]
    w.tick()
    for c in w.civs[1:]: c.next_decision = 10 ** 9
    crime.ROOT_CHANCE, keep = 1.0, crime.ROOT_CHANCE
    try:
        w.ticks = 40
        crime.step(w)
    finally:
        crime.ROOT_CHANCE = keep
    g = crime.active(w)
    assert g and g[0]["kind"] in ("pirates", "cartel", "paramilitary"), g
    g = g[0]; g["kind"], g["strength"] = "pirates", 0.8
    h0 = int(w.H[:, 35:].sum())
    crime._piracy(w, g)
    assert int(w.H[:, 35:].sum()) < h0 and any("PIRATES" in e for _, e in w.war_log)
    c = w.civs[1]; c.military, c.morale = 1.0, 10; c.strength = 1.0
    g["victims"] = {1: w.ticks}
    for _ in range(40):
        if not g["alive"]:
            break
        crime._crackdown(w, g)
    assert not g["alive"], g
    print("97 the %s took root in the anarchy, raided across the strait, and were crushed in a crackdown" % g["name"])
    # 98. Hidden survivors: once the hordes have long left, people come out of hiding on the emptied land - villages.
    H, Z, D, T, O, A = blank(60, humans=0, owner=0)
    w = sim.World(H, Z, D, T, O, A, seed=2, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.H0[:, :] = 80
    for k in range(30):
        w.ticks = restart.EMERGE_START + k * restart.EMERGE_EVERY
        restart.emerge(w)
    out = int((w.H > 0).sum())
    assert out >= 20 and getattr(w, "emerged", 0) > 0, out
    w2 = sim.World(*blank(60, humans=0, owner=0), seed=2, stochastic=True, meta={"wrap": False, "res": 0.5})
    w2.H0[:, :] = 80; w2.Z[30, 30] = 5
    for k in range(30):
        w2.ticks = restart.EMERGE_START + k * restart.EMERGE_EVERY
        restart.emerge(w2)
    near = int((w2.H[24:37, 24:37] > 0).sum())
    assert near == 0, near
    print("98 %d hiding places came out once the land was quiet (none within reach of a zombie)" % out)
    # 99. The recovery era: once the outbreak has burned out, a fresh outbreak in a town is hunted down.
    import recovery
    def late(era):
        H, Z, D, T, O, A = blank(40, humans=120)
        w = sim.World(H, Z, D, T, O, A, seed=3, stochastic=True, meta={"wrap": False, "res": 0.5})
        w.tick()
        for c in w.civs[1:]: c.next_decision = 10 ** 9
        w.Z[20, 20] = 40
        w.era = era
        for _ in range(30):
            w.era = era
            recovery._militia(w, era) if era else None
            w.tick()
            w.era = era
        return int(w.Z.sum())
    z_then, z_now = late(0.0), late(1.0)
    assert z_now < 0.5 * max(z_then, 1), (z_then, z_now)
    print("99 a fresh outbreak in a town: %d zombies after a month mid-outbreak, %d in the recovery era" % (z_then, z_now))
    # 100. New towns: on the best sites (the coast), irregular footprints - not a lattice of single tiles.
    H, Z, D, T, O, A = blank(60, humans=110)
    T[:, :3] = 0; H[:, :3] = 0; O[:, :3] = 0                 # (a coast on the west)
    w = sim.World(H, Z, D, T, O, A, seed=4, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.tick(); w.civs[1]._worst_damage = 0.5
    built0 = (w.T == TS) | (w.T == TU)
    keep = landuse.TOWN_CHANCE
    landuse.TOWN_CHANCE = 1.0
    try:
        towns = landuse._new_towns(w, (w.T == TG) & (w.O == 1), built0, np.array([False, True]), landuse.home(w))
    finally:
        landuse.TOWN_CHANCE = keep
    rr, cc = np.nonzero(towns)
    assert 1 <= rr.size <= landuse.TOWN_MAX * landuse.TOWN_TILES[1] and cc.min() <= 6, (rr, cc)
    print("100 new towns at %s (on the coast), %d tiles" % (sorted(set(zip(rr.tolist(), cc.tolist())))[:3], rr.size))
    # 101. Small states founded since the outbreak reach only their own region; big ones further.
    H, Z, D, T, O, A = blank(100, humans=0, owner=0)
    H[48:52, 48:52] = 100; O[48:52, 48:52] = 1
    w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.tick(); c = w.civs[1]; c.successor = True; c.capital = (50, 50)
    w.pop_ref = 100000.0
    small_reach = int(w.may_claim(np.full((100, 100), 1)).sum())
    w.pop_ref = 100.0
    big_reach = int(w.may_claim(np.full((100, 100), 1)).sum())
    assert small_reach < big_reach, (small_reach, big_reach)
    print("101 a small new state may claim %d tiles, a big one %d" % (small_reach, big_reach))
    # 102. Tribute: a strong junta makes its weak neighbour pay - not the other way round; a puppet follows its
    #      overlord into war and starts none of its own.
    H, Z, D, T, O, A = blank(60, humans=100); O[:, 40:] = 2; H[:, 40:] = 30
    w = sim.World(H, Z, D, T, O, A, seed=5, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.tick()
    for c in w.civs[1:]: c.next_decision = 10 ** 9
    big, small = w.civs[1], w.civs[2]
    big.gov, big.military, big.strength, big.morale = "junta", 1.0, 0.9, 10
    small.gov, small.military, small.strength = "democracy", 0.1, 0.2
    keep = globalaffairs.TRIBUTE_CHANCE
    globalaffairs.TRIBUTE_CHANCE = 10.0
    try:
        for k in range(10):
            w.ticks = (k + 1) * globalaffairs.TRIBUTE_EVERY
            globalaffairs._tribute(w, [big, small])
            if getattr(small, "overlord", None) is not None or war.at_war(w, 1):
                break
    finally:
        globalaffairs.TRIBUTE_CHANCE = keep
    assert getattr(big, "overlord", None) is None, "the weak one demanded tribute"
    assert getattr(small, "overlord", None) == 1 or war.key(1, 2) in w.wars, (small.__dict__.get("overlord"), w.wars)
    for k in list(w.wars):
        del w.wars[k]
    globalaffairs.make_tributary(w, big, small, "wins the war", puppet=True)
    third = w.add_civ(); third.capital = (5, 5)
    w.truces = {}
    war.declare(w, 1, third.id, "test")
    assert war.key(small.id, third.id) in w.wars, w.wars
    print("102 the junta made its weak neighbour pay tribute; its puppet followed it into war")
    # 103. Pirate havens: a coastal town in a country with hardly an army to patrol its coast.
    H, Z, D, T, O, A = blank(60, humans=120)
    T[:, 30:] = 0; H[:, 30:] = 0; O[:, 30:] = 0
    w = sim.World(H, Z, D, T, O, A, seed=12, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.cities = [("Smugglers' Cove", 30, 28, 1.0)]
    w.tick(); w.civs[1].military = 0.1
    keep = crime.PIRATE_HAVEN_CHANCE
    crime.PIRATE_HAVEN_CHANCE = 1.0
    try:
        w.ticks = crime.PIRATE_HAVEN_START
        crime.step(w)
    finally:
        crime.PIRATE_HAVEN_CHANCE = keep
    pir = [g for g in crime.active(w) if g["kind"] == "pirates"]
    assert pir, crime.active(w)
    print("103 the %s made the coast their haven (the country hardly patrols it)" % pir[0]["name"])
    # 104. Seasons: in the northern winter the dead freeze - they stay put, and the townsfolk smash a good part of
    #      them, never all; in summer they move again.
    import datetime
    import seasons
    import zombies
    def north(month):
        H, Z, D, T, O, A = blank(60, humans=0, owner=0)
        H[:, :] = 0
        meta = {"wrap": False, "res": 0.5, "bounds": [0.0, 30.0, 40.0, 70.0], "climate": "lat",
                "start_date": f"2030-{month:02d}-15"}
        w = sim.World(H, Z, D, T, O, A, seed=3, stochastic=True, meta=meta)
        w.H[8:12, 20:26] = 120; w.O[8:12, 20:26] = 0
        w.Z[10, 30] = 200
        return w
    w = north(1)
    f = seasons.frozen(w)
    assert f is not None and f[10, 30] > 0.9 and seasons.snow(w)[55, 30] < seasons.snow(w)[5, 30], f[10, 30]
    moved = zombies.transport(w, np.array([10]), np.array([30]), np.array([10]), np.array([31]), np.array([100]))
    assert moved <= 5, moved
    w.Z[10, 30] = 0; w.Z[10, 27] = 200
    for k in range(60):
        w.ticks = k
        seasons.step(w)
    left = int(w.Z[10, 27])
    assert 20 < left < 200, left
    w2 = north(7)
    assert seasons.frozen(w2) is None or seasons.frozen(w2)[10, 30] < 0.05
    print("104 January in the north: the dead frozen (%d of 200 moved), 2 months of the townsfolk: %d of 200 left; "
          "July: none frozen" % (moved, left))
    # 105. Harvests follow the season - nothing under the snow - and come to a year's eating over the year.
    w = north(1)
    yr = np.zeros(w.H.shape)
    eat = np.zeros(w.H.shape)
    for d in range(365):
        w.ticks = d
        yr += seasons.harvest(w)
        eat += 1 + seasons.WINTER_EAT * seasons.snow(w)
    w.ticks = 0
    jan = seasons.harvest(w)
    ratio = yr[5, 30] / eat[5, 30]
    assert jan[5, 30] < 0.05 and abs(ratio - 1) < 0.05 and abs(yr[55, 30] / eat[55, 30] - 1) < 0.05, (jan[5, 30], ratio)
    assert seasons.store_days(0.6) > E.FOOD_CAP_TICKS
    print("105 harvests: %.2f in a northern January, a year's crops / a year's eating = %.2f" % (jan[5, 30], ratio))
    # 106. Disease: a fever in a crowded town kills many more where medicine is gone; it burns out.
    import disease
    import tech
    def fever(level):
        H, Z, D, T, O, A = blank(40, humans=200)
        w = sim.World(H, Z, D, T, O, A, seed=7, stochastic=True, meta={"wrap": False, "res": 0.5})
        w.tick()
        tech.level(w)[:] = level
        w.civs[1].famine = False
        h0 = int(w.H.sum())
        disease.outbreak(w, 20, 20, virulence=1.0, name="typhus")
        for k in range(300):
            w.ticks = 1 + k
            disease.step(w)
        return h0 - int(w.H.sum()), float(w.sick.max()), w
    dead_med, left_med, _ = fever(1.0)
    dead_none, left_none, w = fever(0.0)
    assert dead_none > 2 * max(dead_med, 1) and left_none < 0.01, (dead_med, dead_none, left_none)
    assert any("typhus" in e for _, e in w.war_log)
    print("106 typhus in a crowded town: %d dead with medicine, %d without - then it burned out" % (dead_med, dead_none))
    # 107. Technology is local: an emptied district loses it, a lived-in one keeps it, and it comes back from neighbours.
    H, Z, D, T, O, A = blank(60, humans=100)
    w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.tick()
    w.civs[1].capital = (30, 10); w._supply_t = -10 ** 6      # (the capital in the lived-in half)
    w.H[:, 30:] = 0
    for k in range(80):
        w.ticks = (k + 1) * tech.TECH_EVERY
        tech.step(w)
    t = tech.level(w)
    assert t[30, 10] > 0.95 and t[30, 50] <= tech.TECH_SALVAGE + 0.01, (t[30, 10], t[30, 50])
    w.H[:, 30:] = 100
    lo, lo_far = float(t[30, 40]), float(t[30, 55])
    for k in range(40):
        w.ticks = (100 + k) * tech.TECH_EVERY
        tech.step(w)
    assert t[30, 40] > lo + 0.2 and t[30, 40] - lo > t[30, 55] - lo_far, (lo, t[30, 40], lo_far, t[30, 55])
    print("107 technology: %.2f where people stayed, %.2f in the emptied half; resettled, it came back to %.2f near "
          "the old towns (%.2f far from them)" % (t[30, 10], lo, t[30, 40], t[30, 55]))
    # 108. Supply lines: a far province gets less of its country's power - an overseas one is on its own (exempt).
    import trade
    H, Z, D, T, O, A = blank(100, humans=100)
    T[:, 60:64] = 0; H[:, 60:64] = 0
    w = sim.World(H, Z, D, T, O, A, seed=1, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.tick(); w.civs[1].capital = (50, 5)
    sup = trade._supply(w)
    assert sup[50, 8] == 1.0 and sup[50, 55] < 0.8 and sup[50, 90] == 1.0, (sup[50, 8], sup[50, 55], sup[50, 90])
    print("108 supply: %.2f near the capital, %.2f in the far province, %.2f across the sea" %
          (sup[50, 8], sup[50, 55], sup[50, 90]))
    # 109. A colony across the sea gets ships from home: new colonists and supplies.
    H, Z, D, T, O, A = blank(80, humans=100)
    T[:, 35:45] = 0; H[:, 35:] = 0; O[:, 35:] = 0
    w = sim.World(H, Z, D, T, O, A, seed=2, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.tick()
    home = w.civs[1]; home.capital = (40, 10); home.ports = 1; home.materials = 200.0
    col = w.add_civ(); col.capital = (40, 60); w.O[38:43, 58:63] = col.id; w.H[38:43, 58:63] = 40
    col.food = 10.0; col.food_use = 1.0
    w.tick()
    trade.register(w, home, 40, 60, colony=col.id)
    x = trade.outposts(w)[0]
    h_before = int(w.H[40, 60])
    for k in range(400):
        w.ticks = 1000 + k
        if w.ticks % trade.RESUPPLY_EVERY == 0:
            trade._resupply(w)
    assert x["ships"] >= 2 and int(w.H[40, 60]) > h_before, (x, h_before, int(w.H[40, 60]))
    print("109 %d supply ships reached %s across the sea (its town: %d -> %d people)" %
          (x["ships"], col.name, h_before, int(w.H[40, 60])))
    # 110. Diplomacy remembers: the attacked hold a grudge for the land they lost; old friends sign pacts.
    import diplomacy
    H, Z, D, T, O, A = blank(60, humans=100); O[:, 30:] = 2
    w = sim.World(H, Z, D, T, O, A, seed=5, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.tick()
    w.truces = {}
    war.declare(w, 1, 2, "test")
    assert diplomacy.opinion(w, 2, 1) < -0.3 and diplomacy.hostility(w, 1, 2) > 1.5
    w.wars[war.key(1, 2)]["captured"] = {1: 40}
    war.end(w, war.key(1, 2), "armistice")
    for k in range(100):
        w.ticks = (k + 1) * diplomacy.EVERY
        diplomacy.step(w)
    assert diplomacy.grudge(w, 2, 1) > 0.25 and abs(diplomacy._rel(w).get((1, 2), (0, 0))[0]) < 0.05
    third = w.add_civ()
    diplomacy.change(w, 1, third.id, mood=0.8)
    diplomacy.change(w, third.id, 1, mood=0.8)
    assert diplomacy.hostility(w, 1, third.id) < 0.3
    print("110 a thousand days on, the mood has passed but the grudge remains (%.2f); friends: hostility x%.2f"
          % (diplomacy.grudge(w, 2, 1), diplomacy.hostility(w, 1, third.id)))
    # 111. A cult in a desperate, unstable country grows and takes it over - a theocracy with a creed.
    import ideology
    import motives
    H, Z, D, T, O, A = blank(40, humans=120)
    w = sim.World(H, Z, D, T, O, A, seed=6, stochastic=True, meta={"wrap": False, "res": 0.5})
    w.tick()
    c = w.civs[1]; c.famine = True; c.instability = 0.8; c.military = 0.1; c.capital = (20, 20)
    g = dict(name="the Church of the Last Days", creed="faith", r=20, c=20, host=1, strength=0.5, born=0,
             alive=True, place="Testville")
    ideology.cults(w).append(g)
    for k in range(20):
        if not g["alive"]:
            break
        c.instability = 0.8
        ideology._grow(w, g)
    assert c.gov == "theocracy" and ideology.creed(c) == "faith", (c.gov, ideology.creed(c), g)
    other = w.add_civ()
    assert ideology.affinity(c, other) < 0 and motives.militarism(c) > 0
    print("111 %s took over: now %s (%s)" % (g["name"], c.name, ideology.LABEL[ideology.creed(c)]))
    print("all civ tests passed")


if __name__ == "__main__":
    main()
