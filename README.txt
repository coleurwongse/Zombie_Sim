Zombie Infection Simulator
==========================

Run       python main.py                         the world (maps/world), outbreak at the Three Gorges, today's date
          python main.py maps/middle_earth       Middle-earth, September 3018: outbreak at Bree
          python main.py maps/world_lite         the world at half the detail - about twice as fast
          options: --seed N (repeat a run)  --outbreak CITY (patient zero anywhere, e.g. "New York", Edoras)
                   --virulence X (default 1.4)  --no-nukes  --no-civil-war  --war  --deterministic
Keys      mouse wheel over the map: zoom; right-drag / arrows / WASD: pan; Home: whole map; +/-: speed;
          1/2/3/4: views (who holds a tile / terrain / governments / density); T: hover text; SPACE: pause; R: new run;
          mouse wheel over the panel or PgUp/PgDn: scroll the list of governments.
          Terrain view: cyan = working ports, pink = airports still flying.
Panel     date (one tick = one day), people, zombies, shipping still running, world alarm; then every government, most
          important first.  Letters: J junta, R republic, W warlords, C clans; W at war, Q borders shut, p at peace;
          actions Q quarantine, Rt retreat, F fortify, P purge, E evacuate, Rc reclaim, O offensive.
Tests     python test_civ.py      python test_render.py

Files
  main.py            the window (pygame)                      sim.py        the world and one tick of everything
  engine.py          per-tile rules: bites, zombie movement on land and at sea, people fleeing, airports
  zombies.py         hordes hunting people (scent over land)  people.py     panic, refugees, evacuation, stragglers, riots
  boats.py           refugee boats, ocean ships, ports and trade
  economy.py         food (farms, imports, famine), materials, fort upkeep
  civilization.py    governments: morale, decisions (fortify, purge, evacuate, quarantine, reclaim, retreat), armies
  front.py           the manned front line           offensive.py  bases pushed into infested land, land retaken
  fracture.py        governments breaking up: lost capitals, cut-off regions, overextension
  govern.py          forms of government              union.py      fragments of one country joining up again
  war.py             wars, civil wars, alliances      nukes.py      nuclear weapons
  peace.py           standing down after the emergency, people going back to town
  restart.py         rebuilding: births, resettlement, pioneers, annexing clean land, survivors founding states
  holdouts.py        besieged cities that barricade themselves       quarantine.py  shut borders
  aid.py             international aid - the UN (or allies): food and peacekeepers for countries in trouble
  expeditions.py     strong countries retaking lost coasts across the sea
  render.py          the map views and hover text  mapio.py  map folders (PNG layers)  labels.py  connected regions
  terrain.py         terrain types and what they mean
  make_world.py      builds world maps from Natural Earth (data/natural_earth), with world_data.py (armies, warheads,
                     wars, rivals, rebel regions, terrain corrections)
  make_middleearth.py  builds maps/middle_earth (hand-drawn on the general map of Middle-earth)

Maps        a map is a folder: humans/zombies/defense/owner/terrain PNGs (1 pixel = 1 tile), airports.json, meta.json
            (names, capitals, cities, ports, armies, warheads, wars, rivals, alliances, standing garrisons, start date).
  maps/world        0.35 degree per tile, 1029 x 463, 200 countries; ~0.6 s per day
  maps/world_lite   0.5 degree per tile, 720 x 324
  maps/middle_earth 5 miles per tile, 368 x 331, 23 realms
  python make_world.py --res 0.35 --out maps/world       (--region europe|africa|americas|asia|lon0,lon1,lat0,lat1)
  python make_middleearth.py

Terrain     deep and shallow water, grass, forest, rainforest, wetlands, highlands, mountains, desert, tundra, ice,
            urban, suburban.  Mountains, highlands, forest and wetlands protect.  Terrain is a barrier (terrain.MOVE):
            zombies move into mountains at 0.15x the pace of open ground, ice 0.3x, wetlands 0.4x, highlands and jungle
            0.55x, desert 0.6x - and the scent that draws hordes to people hardly carries over mountains, so hordes go
            round a range or trickle through its passes.  Ranges like the Rockies or the Himalaya make good borders.
            Nobody lives in the water; people cross it by boat.

How a game goes
  The outbreak  zombies bite and spread tile by tile, hunt people over land, wander into shallow water and swim ashore,
                drift at sea (hordes swim for land).  Infected airports fly the infection on (long-haul flights rarely);
                frightened coasts send refugee boats, ports now and then an ocean ship; stragglers slip away from
                threatened places to quiet ones far off - some of them bitten.
  The world     once the outbreak is big (and any cover-up is over - China hides it for 45 days, as in World War Z) the
                world is alarmed: every government partly mobilizes, flights between countries mostly stop, a country in
                an emergency grounds its own flights, a country that shuts its borders shuts its airports.
  Governments   watch the zombies in their region; fortify cities and passes, purge hordes, evacuate, shut borders,
                man a front line (stronger for bigger, better armies; thinner the longer it is), sweep zombies from
                their land, push out with fortified bases and retake land.  Big countries fight with more than small
                ones (strikes, sweeps and stockpiles scale with population).  Morale falls while an unprotected front
                spreads, with riots, famine and losses; a government that breaks keeps its heartland if it can, and its
                regions carry on as juntas, republics, warlords or clans - only hopeless cities fall into anarchy.
                A lost capital moves; a region cut off from it goes its own way; a country that grows too fast or holds
                much land that was never its own may split.  Now and then a besieged big city barricades itself and
                holds out - as a fortress of its government, or as a free city of its own.
  Land          a government keeps empty land only near its people (wilderness excepted); it resettles emptied and clean
                land - its own and a few tiles beyond its border - from crowded and full places, and annexes clean land
                next to land it guards (overseas only near what it held; at home within 25 degrees of its capital).
                Survivors on ungoverned land found new states.  People grow back to what each place held before.
  Economy       farms feed people (countries that imported food keep importing while world shipping runs), industry makes
                materials for forts, ammunition, transport and armies; ports trade and ship food.
  Wars          existing wars (Russia-Ukraine, US-Iran, Israel-Palestine; in Middle-earth Mordor-Gondor and
                Isengard-Rohan); scarcity wars between neighbours; old rivals; civil wars over regions that break away.
                Members of one alliance never fight each other.  Nuclear powers may, rarely, hit a giant horde or - losing
                a war - an enemy city; a nuclear power that is hit usually strikes back.
  Aid           (aid.py) safe, strong, reasonably big countries help the ones in trouble they can reach (by land,
                between ports, or by air for the strongest armies) and aren't at war with: food from full granaries,
                and peacekeeping missions (~60 days) that sweep the zombies around the recipient's people.  On the
                world map that's the UN; on a map with alliances, only allies help each other.  The panel counts the
                UN missions running.
  Overseas      (expeditions.py) a big country with a strong army, no threat at home, not at war and ports on the
                same sea may land an army on a lost coast across the water - in a country whose government has
                fallen, with no government holding anything nearby, well away from its own land - within reach of
                its capital (20-45 degrees by size and strength: China to Indonesia, not the Dominican
                Republic to New York); the landing becomes a base that clears and resettles the coast, and the country
                may expand from it on that landmass.  Overseas land that was never part of the country - won this way
                or annexed - has a good chance of declaring independence later (fracture.independence).
  Rebuilding    when the zombies are gone a government declares the emergency over, dismantles forts it no longer needs,
                demobilizes (not while the world is alarmed) and its people go back to the towns.

Middle-earth (maps/middle_earth)
  23 realms in two alliances.  Free Peoples: Gondor, Rohan, Lindon, Rivendell, Lothlorien, the Woodland Realm, Erebor,
  the Iron Hills, Dale, the Beornings and Woodmen, Fangorn, the Shire, Bree-land, the Rangers of the North.  Shadow:
  Mordor (with Dol Guldur), Isengard, Dunland, Moria, Gundabad, Rhun, Khand, Harad, Umbar.  Armies from the Shire's
  0.05 to Mordor's 1.0; elves and Ents few but formidable.  Standing fortresses: Minas Tirith, Osgiliath, Cair Andros,
  Pelargir, Dol Amroth, Edoras, Helm's Deep, Dunharrow, Isengard, Barad-dur, Minas Morgul, Cirith Ungol, the Morannon,
  Dol Guldur, Caras Galadhon, Rivendell, Thranduil's Halls, Erebor, the Iron Hills, Mithlond, Umbar, Moria, Gundabad.
  Terrain has scattered woods, downs, fens along the rivers and marshes besides the named forests and ranges; borders
  are ragged; people thin out gradually from the towns into the countryside.
  The Anduin is open water from the Gladden Fields to the sea; the other rivers are marshy valleys.  No airports, no
  warheads.  Calendar from 23 September 3018.  Edit make_middleearth.py (realms, places, armies) and rerun it.

Balance knobs
  --virulence (1.25: usually stays in Asia; 1.4 default; 1.75: everywhere)   world reaction: front.ALARM_ALERT,
  engine.TRAVEL_BAN / LONG_HAUL / GROUNDED, sim.ALARM_RATE   spread by sea: boats.SHIP_CHANCE / INFECTED
  stragglers: people.STRAY_*   holdouts: holdouts.HOLDOUT_CHANCE   overextension: fracture.OVEREXTEND_*
  rebuilding: restart.RESETTLE_* / PIONEER_REACH   aid: aid.*   expeditions: expeditions.EXP_*
  independence: fracture.INDEPENDENCE_CHANCE   terrain as a barrier: terrain.MOVE.  Results vary a lot from seed to seed - judge with several.
