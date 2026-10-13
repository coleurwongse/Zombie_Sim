Zombie Infection Simulator
==========================

Run       python main.py maps/world              the world, outbreak at the Three Gorges, today's date
          python main.py maps/middle_earth       Middle-earth, September 3018: outbreak at Bree (main.py's default)
          python main.py maps/beleriand          Beleriand, midwinter of First Age 455: outbreak in Angband's forges
          python main.py maps/world_lite         the world at half the detail - about twice as fast
          options: --seed N (repeat a run)  --outbreak CITY (patient zero anywhere, e.g. "New York", Edoras)
                   --virulence X (default 1.4)  --no-nukes  --no-civil-war  --war  --deterministic
Keys      F11 or F: full screen (Esc leaves it); the window can also be resized by dragging its edges;
          mouse wheel over the map: zoom; right-drag / arrows / WASD: pan; Home: whole map; +/-: speed;
          1/2/3/4: views (who holds a tile / terrain / governments / density); T: hover text; SPACE: pause; R: new run;
          mouse wheel over the panel or PgUp/PgDn: scroll the list of governments.
          Terrain view: cyan = working ports, pink = airports still flying.  The map remembers zombies for a few
          days (fading), so a lone one wandering on and off a tile doesn't make borders blink.  Zombie ground is
          shaded by how dense the horde is against the densest on the map at the moment (dark blood red for thin
          fringes, red for a horde's body, light hot red for its core), so hordes show up as bodies on the crowded
          world map too, not a flat red mass (render.HORDE_*; display only).
Panel     numbers of people and zombies (and the people rioting, fleeing, evacuating, moving, settling) are scaled to the real population the map stands for and shown as 950, 12.3k,
          4.5m, 1.2b - on the world map each country at its own real population (meta "real_pops": China 1.4b,
          Russia 154m ...), on Middle-earth 6m and Beleriand 3.5m in all.  The simulation keeps its own small numbers.
          date (one tick = one day), people, zombies, shipping still running, world alarm; then every government, most
          important first.  Letters: J junta, R republic, W warlords, C clans; W at war, Q borders shut, p at peace;
          actions Q quarantine, Rt retreat, F fortify, P purge, E evacuate, Rc reclaim, O offensive.  Long log
          messages wrap onto the next line.
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
  resolve.py         the turning point: countries adapt to the fight; hordes with nothing to eat starve
  settlers.py        groups of settlers leave thriving countries and found new states on emptied land
  aid.py             international aid - the UN (or allies): food and peacekeepers for countries in trouble
  expeditions.py     strong countries retaking lost coasts across the sea
  render.py          the map views and hover text  mapio.py  map folders (PNG layers)  labels.py  connected regions
  terrain.py         terrain types and what they mean
  make_world.py      builds world maps from Natural Earth (data/natural_earth), with world_data.py (armies, warheads,
                     wars, rivals, rebel regions, terrain corrections)
  make_middleearth.py  builds maps/middle_earth (hand-drawn on the general map of Middle-earth)
  make_beleriand.py    builds maps/beleriand (hand-drawn on a political map of Beleriand and Tolkien's own map)
  drawmap.py         how both are drawn: the ground, then realms grown from their towns over it, then the people

Maps        a map is a folder: humans/zombies/defense/owner/terrain PNGs (1 pixel = 1 tile), airports.json, meta.json
            (names, capitals, cities, ports, armies, warheads, wars, rivals, alliances, standing garrisons, start date).
  maps/world        0.35 degree per tile, 1029 x 463, 200 countries
  maps/world_lite   0.5 degree per tile, 720 x 324
  maps/middle_earth 5 miles per tile, 368 x 331, 36 realms
  maps/beleriand    3 miles per tile, 284 x 277, 22 realms
  python make_world.py --res 0.35 --out maps/world       (--region europe|africa|americas|asia|lon0,lon1,lat0,lat1)
  python make_middleearth.py         python make_beleriand.py

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
                threatened places to quiet ones - most a short way, a few to a city or port further off (bigger
                cities likelier) - some of them bitten, unless the country they reach is mobilized and screens them.
  The world     once the outbreak is big (and any cover-up is over - China hides it for 45 days, as in World War Z) the
                world is alarmed: every government partly mobilizes, flights between countries mostly stop, a country in
                an emergency grounds its own flights, a country that shuts its borders shuts its airports.
  Governments   watch the zombies in their region; fortify cities and passes, purge hordes, evacuate, shut borders,
                man a front line (stronger for bigger, better armies; thinner the longer it is), sweep zombies from
                their land, push out with fortified bases and retake land.  Big countries fight with more than small
                ones (strikes, sweeps and stockpiles scale with population).  Morale falls while an unprotected front
                spreads, with riots, famine and losses - but a government that still holds 60% of its peak population
                doesn't dissolve over a bad month (civilization.MORALE_HELD).  One that breaks keeps its heartland if it can, and its
                regions carry on as juntas, republics, warlords or clans - only hopeless cities fall into anarchy.
                A lost capital moves; a region cut off from it goes its own way; a country that overextends may split:
                grown fast, much land that was never its own, far more land than its country held at the start, or
                foreign land far from its capital - the bigger and the more of these, the likelier (fracture.OVEREXTEND_*);
                so the map doesn't end as a few giant supercountries.  New states take the region's biggest city as capital and
                are named after a city no other government is named after (a region without a town of its own after
                the land it was part of - "East Rhun Clans" - never after a city another government holds); a quiet province (no horde near it - Alaska
                when the lower 48 fall) becomes a state of its own even if small, never anarchy.  A country that has
                conquered a lot of another one (more than 0.4x its own land) often loses it again, the conquered
                country rising up along its old borders.  Now and then a besieged big city barricades itself and
                holds out - as a fortress of its government, or as a free city of its own.
  Land          a government keeps empty land only near its people (wilderness excepted); it resettles emptied and clean
                land - its own and a few tiles beyond its border - from crowded and full places, and annexes clean land
                next to land it guards (overseas only near what it held; at home within 25 degrees of its capital).
                Survivors on ungoverned land found new states.  People grow back to what each place held before.
                Settlers (settlers.py): a safe, thriving country now and then sends a group to once-settled land that
                is empty and clean, well away from any government - over land, or by sea from its ports - and they
                found a state of their own there that grows like any other.  Old big cities draw them most, and new
                colonies keep their distance from other settlers' colonies (settlers.SETTLE_SPACING / SPREAD; nobody
                hurries back where a colony just failed; the map's meta "settle_scale" - 2 on Middle-earth and
                Beleriand - stretches the spacing and halves the rate), so they spread out instead of crowding one spot; that's how emptied continents fill up again.
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
  Overseas      (expeditions.py) a sizeable country with a real army, little threat at home (more allowed past its
                turning point), not at war and with working ports may land an army on a lost, once-settled coast
                across the water - in a country whose government has fallen, with no government holding anything
                nearby, well away from its own land - within a voyage of its ports (25-55 degrees by size and
                strength, measured by sea: China to Indonesia, not the Dominican Republic to New York, and nobody
                sails round Africa to the Arctic); up to two at once, not straight back to a failed landing; the
                landing becomes a base that clears and resettles the coast, and the country
                may expand from it on that landmass.  Overseas land that was never part of the country - won this way
                or annexed - has a good chance of declaring independence later (fracture.independence).
                Open land: where most of a region's once-settled land is empty and nobody's (a continent the zombies
                emptied), countries doing fine elsewhere come for it - from up to 110 degrees by sea, up to 4 landings
                at once, a wider beachhead - and settlers sail for it too ("to claim the emptied land" in the log;
                expeditions.OPEN_*).
  Turning point (resolve.py) for the first ADAPT_START (70) days nobody has learned anything and the outbreak spreads
                at full speed over large parts of continents.  From then on a government that keeps fighting while it
                still holds a fair part of its people adapts over about 80 days: its front line, sweeps, strikes and training get stronger, morale losses shrink,
                and it can recover while its line merely holds.  Once adapted, when the zombies around it stop
                growing, it rallies ("TURNING POINT" in the log) and starts fortifying, rebuilding and retaking ground.
                A front on mountains, hills, marsh or desert, or behind a river or the coast, holds much better - that's
                usually where the tide turns.  Zombies with no people near them slowly starve, so regions they have
                eaten bare thin out, and lone stragglers far from anyone soon die; militias and patrols hunt down lone
                stragglers on a government's land and up to 6 tiles beyond its people (not the edge of a horde) - so
                an emptied continent isn't kept empty by a thin dust of strays.  A fresh outbreak still meets a country at resolve 0: the damage comes first.
  Rebuilding    when the zombies are gone a government declares the emergency over, dismantles forts it no longer needs,
                demobilizes (not while the world is alarmed) and its people go back to the towns.

Middle-earth (maps/middle_earth)
  36 realms in two alliances (and Dorwinion on its own).  Free Peoples: Gondor with its fiefs (Dol Amroth, Lebennin,
  Lamedon, Morthond Vale, Lossarnach), Rohan with the Westfold and the Eastfold, Lindon, Rivendell, Lothlorien, the
  Woodland Realm, Erebor, the Iron Hills, Dale and Lake-town (Esgaroth), the Beornings and the Woodmen, Fangorn, the
  Shire and Buckland, Bree-land, the Rangers of the North (thinly, over old Arnor).  Shadow: Mordor (with Dol Guldur),
  Isengard, Dunland, Moria, Gundabad, Rhun, Khand, Harad with Harondor and Haradwaith, Umbar.  Armies from the Shire's
  0.05 to Mordor's 1.0; elves and Ents few but formidable.  Standing fortresses: Minas Tirith, Osgiliath, Cair Andros,
  Pelargir, Dol Amroth, Edoras, Helm's Deep, Dunharrow, Isengard, Barad-dur, Minas Morgul, Cirith Ungol, the Morannon,
  Dol Guldur, Caras Galadhon, Rivendell, Thranduil's Halls, Erebor, the Iron Hills, Mithlond, Umbar, Moria, Gundabad.
  The Anduin is open water from the Gladden Fields to the sea; the other rivers are marshy valleys.  No airports, no
  warheads.  Calendar from 23 September 3018.  Edit make_middleearth.py (realms, places, armies) and rerun it.

Beleriand (maps/beleriand)
  The end of the Siege of Angband, midwinter of First Age 455 (the Battle of Sudden Flame).  The outbreak starts in
  the forges of Thangorodrim and turns on Morgoth's own orc-hosts first.  Alliances as they were - the Noldor were not
  one people: Morgoth (Angband); Fingolfin's house (Hithlum, Dor-lomin under Fingon, the House of Hador, Nargothrond,
  Tol Sirion, Dorthonion, the House of Beor); Thingol's Sindar (Doriath, the Falas and Brithombar, the Green-elves of
  Ossiriand, the Haladin of Brethil); Feanor's sons (Himring, Maglor's Gap, Himlad, Thargelion, East Beleriand) -
  Thingol's old rivals, not his allies; the Dwarves (Belegost, Nogrod); Gondolin, hidden and on its own, and the Men
  of Estolad.  Angband 1.0, the High King's host 0.9, Gondolin and Himring 0.9, Doriath 0.85 ... Ossiriand 0.4.
  Fortresses: Angband, Barad Eithel, Tol Sirion, Gondolin, Menegroth, Nargothrond, Himring, Aglon, Maglor's Gap,
  Helevorn, Eglarest, Brithombar, Barad Nimras, Belegost, Nogrod, Amon Ereb - and Melian's Girdle, a standing line
  of defence all round Doriath that stands as long as Menegroth does.  Angband is at war with the realms of the Siege.

How the fantasy maps are drawn (drawmap.py)
  The ground first (every outline pushed about by smooth noise).  Then each realm grows from its towns over the
  ground, cheaply over open country and dearly over mountains, marshes and rivers, within its drawn outline; the land
  is cut into small districts (shires, valleys) the same way, and each realm is made of whole districts - so borders
  run along rivers and ridges and meet at odd angles like real ones.  A town or fief ("liege", "reach") grows from its
  own towns inside its overlord's land.  People are thickest in the towns and thin out into the countryside.

Balance knobs
  --virulence (1.25: usually stays in Asia; 1.4 default; 1.75: everywhere)   world reaction: front.ALARM_ALERT,
  engine.TRAVEL_BAN / LONG_HAUL / GROUNDED, sim.ALARM_RATE   spread by sea: boats.SHIP_CHANCE / INFECTED
  stragglers: people.STRAY_*   holdouts: holdouts.HOLDOUT_CHANCE   overextension: fracture.OVEREXTEND_*
  rebuilding: restart.RESETTLE_* / PIONEER_REACH   aid: aid.*   expeditions: expeditions.EXP_*
  independence: fracture.INDEPENDENCE_CHANCE   terrain as a barrier: terrain.MOVE, front.TERRAIN_LINE / WATER_LINE
  turning point: resolve.ADAPT_START / ADAPT_TICKS / TURN_AT / ROT / MILITIA, front.RESOLVE_LINE.   settlers: settlers.SETTLE_*
  per map (meta.json): "virulence_scale" multiplies --virulence (Beleriand 1.25: a hard map), "settle_scale".
  regrowth: restart.BIRTH / RESETTLE_* / STRAY_OK.  Results vary a lot from seed to seed - judge with several.
