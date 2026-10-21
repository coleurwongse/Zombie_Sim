Zombie Infection Simulator
==========================

Run       python main.py maps/world              the world, outbreak at the Three Gorges, today's date
          python main.py maps/middle_earth       Middle-earth, September 3018: outbreak at Bree (main.py's default)
          python main.py maps/beleriand          Beleriand, midwinter of First Age 455: outbreak in Angband's forges
          python main.py maps/discworld          the Disc, the year of the Borogravian war: outbreak in Escrow, Überwald
          python main.py maps/world_lite         the world at half the detail - about twice as fast
          options: --seed N (repeat a run)  --outbreak CITY (patient zero anywhere, e.g. "New York", Edoras)
                   --virulence X (default 1.4)  --coordination X (0..1, default 0.8: how organized the hordes are)
                   --no-nukes  --no-civil-war  --war  --deterministic
Keys      F11 or F: full screen (Esc leaves it); the window can also be resized by dragging its edges;
          mouse wheel over the map: zoom; right-drag / arrows / WASD: pan; Home: whole map; +/-: speed;
          1/2/3/4/5: views (who holds a tile / terrain / governments / density / hordes on the terrain - no people); T: hover text; SPACE: pause; R: new run;
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
  zombies.py         zombies hunting people close by (scent over land; far ones track people from ~200 tiles)
  hordes.py          hordes choosing their prey (big soft cities first) and marching on it as one: they go round
                     mountains and armies, split for two cities, run together for one, encircle a town (pincers)  people.py     panic, refugees, evacuation, stragglers, riots
  boats.py           refugee boats, ocean ships, ports and trade
  economy.py         food (farms, imports, famine), materials, fort upkeep
  civilization.py    governments: morale, decisions (fortify, purge, evacuate, quarantine, reclaim, retreat), armies
  front.py           the manned front line           offensive.py  bases pushed into infested land, land retaken
  fracture.py        governments breaking up: lost capitals, cut-off regions, overextension
  govern.py          forms of government              union.py      fragments of one country joining up again
  war.py             wars, civil wars, alliances      nukes.py      nuclear weapons
  warfare.py         raids on towns, strikes, partisans in rough country, sea landings
  landuse.py         land changing with its people: fields cleared, suburbs and new towns built, cities ruined
  globalaffairs.py   expeditions abroad, reconstruction aid, pacts, proxy wars, tributaries, revolutions, conquest
  peace.py           standing down after the emergency, people going back to town
  restart.py         rebuilding: births, resettlement, pioneers, villages, annexing clean land, survivors founding states
  holdouts.py        besieged cities that barricade themselves       quarantine.py  shut borders
  resolve.py         the turning point: countries adapt to the fight; hordes with nothing to eat starve
  settlers.py        groups of settlers leave thriving countries and found new states on emptied land
  spread.py          the outbreak keeps reaching continents it hasn't hit yet (infected travellers, world map)
  crossings.py       now and then a chunk of a coastal horde swims across to the next landmass
  aid.py             international aid - the UN (or allies): food and peacekeepers for countries in trouble
  expeditions.py     strong countries retaking lost coasts across the sea
  render.py          the map views and hover text  mapio.py  map folders (PNG layers)  labels.py  connected regions
  terrain.py         terrain types and what they mean
  make_world.py      builds world maps from Natural Earth (data/natural_earth), with world_data.py (armies, warheads,
                     wars, rivals, rebel regions, terrain corrections)
  make_middleearth.py  builds maps/middle_earth (hand-drawn on the general map of Middle-earth)
  make_beleriand.py    builds maps/beleriand (hand-drawn on a political map of Beleriand and Tolkien's own map)
  make_discworld.py    builds maps/discworld (land traced from a picture of the Disc, data/discworld_reference.png)
  drawmap.py         how they are drawn: the ground, then realms grown from their towns over it, then the people

Maps        a map is a folder: humans/zombies/defense/owner/terrain PNGs (1 pixel = 1 tile), airports.json, meta.json
            (names, capitals, cities, ports, armies, warheads, wars, rivals, alliances, standing garrisons, start date).
  maps/world        0.35 degree per tile, 1029 x 463, 200 countries
  maps/world_lite   0.5 degree per tile, 720 x 324
  maps/middle_earth 5 miles per tile, 368 x 331, 36 realms
  maps/beleriand    3 miles per tile, 284 x 277, 22 realms
  maps/discworld    26 miles per tile, 386 x 386, 38 realms
  python make_world.py --res 0.35 --out maps/world       (--region europe|africa|americas|asia|lon0,lon1,lat0,lat1)
  python make_middleearth.py         python make_beleriand.py         python make_discworld.py

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
                so the map doesn't end as a few giant supercountries.  An overextended country takes no more of other
                countries' land (only its own former land) and sends no expeditions.  Regrowing over its own land is
                no reason to split.  Mergers (union.py) are rarer, rarer still in peacetime, never make a country
                bigger than its former country (or 600 populated tiles for unrelated states), and a breakaway doesn't
                rejoin anyone for 400 days - so once the zombies are gone the map settles down.
                Borders of a splitting country follow the lie of the land: each region is what its city reaches most
                easily over the ground, so they meet along mountains, deserts, marsh and rivers, in ragged lines -
                never straight lines or arcs (fracture.split_by_ground, BARRIER).  New states take the region's biggest city as capital and
                are named after a city no other government is named after (a region without a town of its own after
                the land it was part of - "East Rhun Clans" - never after a city another government holds); a quiet province (no horde near it - Alaska
                when the lower 48 fall) becomes a state of its own even if small, never anarchy.  A country that has
                conquered a lot of another one (more than 0.4x its own land) often loses it again, the conquered
                country rising up along its old borders.  Now and then a besieged big city barricades itself and
                holds out - as a fortress of its government, or as a free city of its own.
  Land          a government keeps empty land only near its people (wilderness excepted); it resettles emptied and clean
                land - its own and a few tiles beyond its border - from crowded and full places, and annexes clean land
                next to land it guards (overseas only near what it held; at home within 25 degrees of its capital).
                Survivors on ungoverned land found new states (around a fallen government's garrison even when few).
                Wilderness nobody ever lived on (the Sahara, the steppe) needs no settlers: a neighbour claims it once
                no zombie is near it (restart.WILD_*); once-settled empty land only where its people can guard it.
                People grow back to what each place held before.
                Settlers (settlers.py): a safe, thriving country now and then sends a group to once-settled land that
                is empty and clean, well away from any government - over land, or by sea from its ports - and they
                found a state of their own there that grows like any other.  Old big cities draw them most, and new
                colonies keep their distance from other settlers' colonies (settlers.SETTLE_SPACING / SPREAD; nobody
                hurries back where a colony just failed; the map's meta "settle_scale" - 2 on Middle-earth and
                Beleriand - stretches the spacing and halves the rate), so they spread out instead of crowding one spot (a small new state - a colony, a garrison town - lives off its
                stores while its fields grow and sends out its people a group at a time, so it grows instead of
                staying a dot); that's how emptied continents fill up again.
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

Discworld (maps/discworld)
  The whole Disc, Cori Celesti at the Hub, nothing beyond the Rim.  The land is traced from the picture (its colours;
  the snows round the Hub too), the rest drawn by hand: the Ramtops running rimward from the Hub, the mountains of
  Überwald, ice and tundra in ragged rings round the Hub, the Great Nef, the Tezuman and Howondaland jungles, the red
  heart of Fourecks, the Ankh, the Djel, the swamps of Genua.  38 realms: the Sto Plains (Ankh-Morpork - the biggest
  city on the Disc - Sto Lat, Sto Helit, Sto Kerrig, Pseudopolis, Quirm) stand together; Lancre, Llamedos, Chirm and
  the Hubland barbarian clans; the Dwarves (Copperhead, Schmaltzberg) together; Überwald every lord for himself
  (Bonk, Escrow, Lipwig, Bad Schüschein); Borogravia and Zlobenia at war; Genua, Skund; round the Circle Sea Ephebe
  (a democracy), Tsort, Djelibeybi, Omnia (a theocracy - junta), Klatch with Hersheba; Howondaland and the Tezuman
  Empire; the Agatean Empire on the Counterweight Continent with the Five Families' provinces (Hong, Sung, Tang, Fang,
  McSweeney - allied, but scheming) and the Great Wall (a standing line all along its land borders); Bhangbhangduc;
  Krull, Fourecks and the Brown Islands out by the Rim.  Strongest: the Agatean Red Army 0.95, Omnia, Klatch,
  Borogravia and the Low King's dwarfs 0.85, the Ankh-Morpork Watch 0.6.  Old rivalries: Klatch and Ankh-Morpork,
  Omnia and Ephebe, Tsort and Ephebe, the Hublanders and the Sto Plains.  Fortresses: Ankh-Morpork and Unseen
  University, Kom, Al Khali, Hunghung, Schmaltzberg, Copperhead, the Kneck Fort, Castle Escrow, Bonk, Lancre and
  more.  The outbreak starts in Escrow: the undead were always going to come out of Überwald.
  The Counterweight Continent, Fourecks, Krull and the Brown Islands aren't safe for being across the sea: on the
  hand-drawn maps every landmass but the main one gets infected travellers too (spread.py: a continent like the
  Counterweight up to 3 times, an island once, counting hordes that swam ashore) - at one city, so a quick army can
  still stamp it out and some games they hold.  Hordes prefer swimming somewhere new over hopping round a bay to
  another country's coast (crossings.CROSS_NEW, CROSS_STRAIT).  No airports, no
  warheads.  Edit make_discworld.py and rerun it.

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

Spread between continents (world map)
  The outbreak doesn't get a single chance per continent.  While it rages somewhere, infected travellers keep arriving
  in the big cities and ports of continents with no outbreak going on there right now (spread.py) - until each
  continent has been reached about 5 times and each big island (Japan, Madagascar, New Zealand ...) at least once,
  counting hordes that swam ashore.  Some are stamped out again, so runs still differ a lot.
  Big hordes on a coast regularly send a chunk of themselves across the water (crossings.py): to another landmass or
  another continent (the Channel, the Bering Strait, Gibraltar, the Red Sea, between islands; less often across an
  ocean), preferring shores few hordes have reached yet.  You can see them swimming - 4 to 9 tiles of horde - before
  they come ashore; at most 6 are at sea at once (2 from any one continent), so the oceans don't fill up with zombies.
  Hordes far from people track them over ~200 tiles of land and march as a body (zombies.FAR_*); only those with nobody to reach starve.
  Zombies spread out evenly over the land (engine.SPREAD: a horde is a smooth body, not a checkerboard).

Hordes (hordes.py)
  Every 8 days one attraction field is worked out for the map on a coarse grid (~2 degree cells, but at least 45 cells
  across the map - 8 tiles on Middle-earth, 6 on Beleriand): people are prey,
  big cities three times over, less where well defended; the way there costs more over rough ground and through
  forts and manned front lines, and water can't be crossed.  Every horde tile (6+ zombies) then marches downhill on
  it each day - a horde moves as one body toward the best prey within ~70 degrees, round mountain ranges and round an
  army's line.  A horde across the watershed between two cities splits and goes for both; hordes heading for the same
  city run together.  Close to its prey a horde swings round both sides of it (a pincer) and closes in; at the people
  the ordinary hunt takes over.  --coordination (0..1, default 0.8) sets how organized they are: 0 = no marching,
  zombies just spread out; 1 = every horde tile marches and none straggle.  Big hordes turning on a new city are
  noted in the log now and then.
  When a horde moves on to a bigger prize, each nation it would leave behind keeps a rear guard for itself: the part
  of the horde nearest to it, 1.5 zombies per person it has left (hordes.STAY_RATIO; at most half of the zombies
  heading for one prize).  The same tiles stay day after day, so after overrunning the Shire a real body of the horde
  turns on Lindon and finishes it, and a nation half eaten gets eaten - while the rest marches on.
  Recovered countries get involved: safe, strong ones (judged by the danger they're in now, not what they lost
  earlier) send more and longer peacekeeping missions to countries in trouble (aid.py), and send settlers out more
  often - settlers found countries of their own, so emptied land fills with new states, not one country's provinces.

Colonies, reach and islands
  Settlers' colonies are founded only where no big horde is within ~24 tiles; 250 settlers on a dozen tiles with a
  stockade (garrison 6) at the centre, a small army and four months of food; the old country sends troops to see it
  through, and for its first 150 days a colony's morale doesn't break while it has 30% of its people left
  (settlers.COLONY_*).  So colonies take root and grow into countries of their own.
  How far a country may claim land at home (sim.HOME_REACH, ~25 degrees from its capital) has a ragged edge, not an
  arc (HOME_RAGGED); a country holding a lot of land beyond it that wasn't its own may split, and its far provinces
  go on - and keep expanding - as a state of their own (fracture.OVEREXTEND_FAR).
  An island eaten bare - zombies and nobody left - empties itself into the sea: its hordes march to the shore and
  most of them swim for other land (crossings.STRAND_*).  Hordes also cross to another country's coast across a strait
  (the Channel, Malacca), and a sizeable country the outbreak has passed by 60 days in gets introductions of its own
  (spread.INTRO_COUNTRY) - nobody is safe just for sitting behind a narrow land bridge.
  Swimming hordes take the straightest way over open water (not a staircase of sideways steps) and come ashore
  spread over up to 25 tiles of the shore; those leaving an island eaten bare only head for land where people live.
  A country the outbreak has passed by (never more than 15% of its land lost, 60 days in) gets up to 3
  introductions, each spread over a dozen towns at once - an army can sweep one cluster in a day, not twelve.
  A new colony needs room to grow (120 free once-settled tiles within 12) and the land within ~7 tiles of it is its own
  to settle for 150 days (settlers.COLONY_RESERVE); settlers don't settle their own country's old land (it resettles
  that itself).  A small state (under 600 people) has three times the births, and a place filling up past 60% of what
  it held sends its young people out a group at a time - so small states grow instead of staying a dot.
  Introductions stop once the world's outbreak has fallen below 40% of its peak (and after day 250): late in a game
  the recovered world doesn't get big new outbreaks out of nowhere.
  A country's old borders aren't a wall: past 2x its old size (or 65% of its people on others' land) it still takes
  others' land, only slowly (sim.ABROAD_SOFT) - and is likelier to split.

Forms of government (govern.py)
  A new state's form of government is the one that fits best, not a lottery: first the political tradition of the
  country it was part of (established democracies -> republics, fragile states -> warlords or clans, the rest -
  authoritarian - -> juntas; govern.DEMOCRACIES / FRAGILE; on the hand-drawn maps the realm's own government), then
  what it breaks away from (a republic's province tends to stay a republic), then its circumstances: garrisons and an
  army holding it together under attack -> junta, famine or a horde at the gates -> warlords, safe, fed cities ->
  republic, empty countryside -> clans.  Close calls can go either way.

Crossings, holdouts and expansion
  Hordes don't swim across lakes (the Sea of Rhun, the Caspian) - they walk round; and a crossing to another country
  on the same landmass only happens while people still live there.  Swimming hordes don't land on rocks: a landmass
  needs at least 25 tiles (crossings.LANDING_MIN).  Each continent with a horde on its coast gets its turn to send one
  across (at most 2 at sea from one continent), so East Asia and East Africa don't take every crossing - France's
  hordes now cross the Channel, and Britain gets overrun in some games.
  Many more cities barricade themselves (holdouts.py): a city rolls when a horde comes within 6 tiles - before its
  people have fled - about 2 in 5 hold out, and one that didn't gets another roll 150 days later when the next wave
  comes.  On the world map (2500 cities) the chance is smaller, so it's dozens per continent, not hundreds.
  Nations expand into empty land raggedly (restart.EXPAND_PACE / EXPAND_JAG): a frontier tile is taken only some of
  the time, more or less by the lie of the land and slower into rough ground - so two countries growing into the same
  land meet along a winding border, not a straight line.
  A swimming horde doesn't throw itself on a fortified shore: a held coast counts as further away (crossings.
  LANDING_GUARD), so it lands where the coast isn't held if there is such a place - and wherever it lands, it bites
  people as it comes ashore (0.2 per zombie, up to half of each place's people within 4 tiles): even a horde cut down
  on the beach leaves an outbreak behind it.

Landings, rebuilding and war
  A horde that swims ashore takes the country by surprise: for 30 days its strikes, sweeps and peacekeepers can't
  find it within ~12 tiles of where it landed and the line there stands at a third of its strength
  (crossings.SURPRISE_*), and the people it bites on the beach run inland and turn in a dozen towns behind the
  coast (LANDING_BITES, BITE_TOWNS).  A well-prepared country can still win - after a real fight.
  An emptied continent fills fast: a government with hardly a zombie in its region (restart.RUSH_CALM) resettles
  four times as fast, its pioneers go 14 tiles beyond its border instead of 6, and its families are bigger.
  Villages: survivors nobody governs gather into villages on land that can feed them, and villages - and now and
  then homesteaders from a country rebuilding in peace - send groups of ten out to found more, a few tiles off on
  land nobody holds (restart.VILLAGE_*, GATHER*).  They farm and grow, but have no army and no walls; a cluster that
  lasts organizes itself into a state.
  Land use (landuse.py): a country rebuilding in peace (it has lost 15%+ of its people, or was founded since) that
  has filled its land clears forest next to its fields, turns full farmland round its towns into suburbs and
  crowded suburbs into city, and now and then grows a new market town - never past 8% of its land built up (or what
  it had before).  Empty cities fall into ruin (suburbs after 300 days, fields after 500 more), and empty fields
  next to woods go back to forest.  A tile is rebuilt to what its land holds now, not what it held before.
  War (warfare.py): besides the border battles, war parties raid enemy towns near the front (killing, looting food
  and materials, battering defenses); artillery and air strikes hit towns behind the front; rough ground (forest,
  hills, mountains, marsh, jungle) is harder to take and costs its defenders less - and ground taken there breeds
  partisans who kill the occupier's people and soldiers and win districts back; a strong side with ports lands
  troops on a weakly held enemy coast and takes a beachhead.

Global affairs (globalaffairs.py)
  Nobody sits it out.  Strong countries that are safe at home send expeditionary forces to fallen cities anywhere
  they can reach - over land, by sea, or by air with the strongest armies - and sweep the hordes there for a few
  months, at a cost in soldiers, materials and army strength; rich countries send materials and food to friends
  rebuilding.  Countries that fought side by side, or share an enemy, sign defensive pacts (they never fight each
  other and stand by each other when attacked); outside powers arm the side they favour in a war (proxy wars);
  strong countries make weak neighbours pay tribute, and a war won outright ends with the loser a satellite - until
  the overlord falters.  A government in deep trouble (famine, morale broken, a long war - but not with the zombies
  at the gates) may fall to a revolution: a new form of government and a new name.  Strong aggressive countries go to
  war for land; organized states raid the villages nobody governs near them.
  Raids, strikes, landings, partisans, expeditions, revolutions and tributes are marked on the map for a month
  (x raid, o strike, ^ landing, o partisans, + expedition, o revolution, ^ tribute - the legend is at the top right).

Recovery and holding ground
  A government doesn't resettle land while it's under attack (danger above 0.25, its outbreak growing, people being
  overrun), and only land joined to its own safe, lived-on land by safe ground - settlers don't walk through a horde.
  Settlers are shared out by what each place is rebuilt to, so towns fill before farms: a country coming back has
  towns and countryside, not an even spread.  Pioneers go further on open ground than into rough country, and how
  far varies from place to place (civilization.fine_jag): no round blobs.
  The zombies hold what they take: on land they have emptied near living people, thin groups stay put instead of
  marching off, and don't starve - the land can't be quietly resettled behind the horde (hordes.OCCUPY_*).  A
  country that has come through an outbreak and stood down mobilizes five times as fast the next time zombies turn
  up in its region (front.VETERAN_ALERT): a late horde is met, not ignored until it's continent-sized.
  A state with no town of its own is named after a free town nearby (within 15 tiles) before "North Somewhere".
