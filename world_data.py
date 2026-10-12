"""Hand-kept facts for make_world.py that Natural Earth doesn't carry: armies, nuclear arsenals, the wars going on
when the outbreak starts, regions held by rebels, and a few corrections to the terrain.

Everything is keyed by country name as make_world.py names them (Natural Earth's NAME, shortened by NAME_FIX).
Edit freely - the map has to be regenerated afterwards (python make_world.py ...).
"""

NAME_FIX = {
    "United States of America": "United States", "Dem. Rep. Congo": "DR Congo", "Congo": "Congo",
    "Central African Rep.": "Central African Republic", "S. Sudan": "South Sudan", "Bosnia and Herz.": "Bosnia",
    "Dominican Rep.": "Dominican Republic", "Eq. Guinea": "Equatorial Guinea", "W. Sahara": "Western Sahara",
    "Solomon Is.": "Solomon Islands", "Falkland Is.": "Falkland Islands", "Fr. S. Antarctic Lands": "French Antarctic",
    "N. Cyprus": "Northern Cyprus", "Côte d'Ivoire": "Ivory Coast", "eSwatini": "Eswatini",
    "Timor-Leste": "Timor-Leste", "Macedonia": "North Macedonia", "North Macedonia": "North Macedonia",
    "Czech Rep.": "Czechia", "Czechia": "Czechia", "Lao PDR": "Laos", "Dem. Rep. Korea": "North Korea",
    "Republic of Korea": "South Korea", "Korea": "South Korea", "Russian Federation": "Russia",
    "Fr. Polynesia": "French Polynesia", "Heard I. and McDonald Is.": "Heard Island",
    "S. Geo. and the Is.": "South Georgia", "Br. Indian Ocean Ter.": "Chagos", "Faeroe Is.": "Faroe Islands",
    "Cayman Is.": "Cayman Islands", "Turks and Caicos Is.": "Turks and Caicos", "Marshall Is.": "Marshall Islands",
    "N. Mariana Is.": "Northern Mariana Islands", "Cook Is.": "Cook Islands", "U.S. Virgin Is.": "US Virgin Islands",
    "British Virgin Is.": "British Virgin Islands", "Wallis and Futuna Is.": "Wallis and Futuna",
    "St. Vin. and Gren.": "Saint Vincent", "Antigua and Barb.": "Antigua", "St. Kitts and Nevis": "Saint Kitts",
    "São Tomé and Principe": "Sao Tome", "Siachen Glacier": "Siachen", "Indian Ocean Ter.": "Indian Ocean Territories",
    "Ashmore and Cartier Is.": "Ashmore Islands", "Pitcairn Is.": "Pitcairn", "Åland": "Aland",
}

# Natural Earth lists these under another country's sovereignty; they stay countries of their own on the map.
KEEP_SEPARATE = {"Palestine", "Western Sahara", "Taiwan", "Kosovo", "Somaliland", "Northern Cyprus"}

# Army strength 0..1 (size, equipment, experience) - roughly the usual world rankings.  Others get a default from
# their population.  This sets how strong a government's army is when the outbreak starts and how fast it can train.
MILITARY = {
    "United States": 1.0, "Russia": 0.95, "China": 0.95, "India": 0.85, "South Korea": 0.78, "United Kingdom": 0.72,
    "Japan": 0.72, "Turkey": 0.72, "France": 0.72, "Pakistan": 0.68, "Italy": 0.62, "Egypt": 0.62, "Brazil": 0.58,
    "Israel": 0.68, "Iran": 0.62, "Indonesia": 0.58, "Germany": 0.62, "North Korea": 0.72, "Ukraine": 0.75,
    "Vietnam": 0.55, "Saudi Arabia": 0.55, "Taiwan": 0.58, "Australia": 0.58, "Poland": 0.6, "Spain": 0.52,
    "Thailand": 0.48, "Canada": 0.5, "Algeria": 0.48, "Mexico": 0.42, "Greece": 0.48, "Sweden": 0.5,
    "Philippines": 0.42, "Myanmar": 0.45, "Bangladesh": 0.42, "Colombia": 0.45, "Argentina": 0.4, "Nigeria": 0.38,
    "Ethiopia": 0.42, "Morocco": 0.42, "Iraq": 0.42, "Syria": 0.35, "Netherlands": 0.45, "Norway": 0.48,
    "Finland": 0.52, "Switzerland": 0.45, "Singapore": 0.55, "United Arab Emirates": 0.48, "Peru": 0.38,
    "Venezuela": 0.38, "Chile": 0.4, "South Africa": 0.42, "Kazakhstan": 0.4, "Belarus": 0.42, "Romania": 0.42,
    "Czechia": 0.42, "Hungary": 0.4, "Azerbaijan": 0.42, "Armenia": 0.38, "Georgia": 0.36, "Uzbekistan": 0.38,
    "Malaysia": 0.42, "Cuba": 0.38, "Jordan": 0.4, "Kuwait": 0.38, "Qatar": 0.4, "Oman": 0.38, "Libya": 0.3,
    "Afghanistan": 0.3, "Yemen": 0.3, "Sudan": 0.32, "Angola": 0.35, "Kenya": 0.34, "Tanzania": 0.3, "DR Congo": 0.25,
    "Serbia": 0.38, "Portugal": 0.42, "Denmark": 0.42, "Belgium": 0.4, "Austria": 0.4, "New Zealand": 0.4,
    "Mongolia": 0.3, "Cambodia": 0.3, "Laos": 0.25, "Sri Lanka": 0.36, "Nepal": 0.3, "Lebanon": 0.3,
    "Tunisia": 0.35, "Bolivia": 0.3, "Ecuador": 0.32, "Paraguay": 0.28, "Uruguay": 0.3, "Mali": 0.25, "Niger": 0.25,
    "Chad": 0.28, "Eritrea": 0.32, "Rwanda": 0.36, "Uganda": 0.32, "Zimbabwe": 0.3, "Mozambique": 0.26,
    "Somalia": 0.2, "South Sudan": 0.22, "Palestine": 0.15, "Haiti": 0.1, "Iceland": 0.15,
}

# Nuclear warheads (approximate stockpiles).  These governments can, rarely and in desperation, use them (nukes.py).
NUKES = {"Russia": 5500, "United States": 5000, "China": 600, "France": 290, "United Kingdom": 225, "India": 180,
         "Pakistan": 170, "Israel": 90, "North Korea": 50}

# Personalities that differ from the usual random ones (caution: acts sooner - shuts borders, fortifies;
# aggression: starts wars and offensives sooner).  North Korea sealed itself off in World War Z; Israel built a wall.
# China covered the outbreak up at first in World War Z: slow to act, and no mobilization for its first 45 days.
TRAITS = {"China": {"caution": 0.6, "denial": 45}, "North Korea": {"caution": 1.6}, "Israel": {"caution": 1.5}, "Cuba": {"caution": 1.3},
          "Russia": {"aggression": 1.3}, "Iceland": {"caution": 1.4}}

# Wars already being fought when the outbreak starts (both sides by name).  Edit to taste.
WARS = [("Russia", "Ukraine"), ("United States", "Iran"), ("Israel", "Palestine")]

# Old rivals: under the strain of the outbreak these go to war with each other much more readily than other neighbours
# (even without sharing a border - then it's a war of air and missile strikes), and where both have warheads a war
# between them can go nuclear (nukes.py).
RIVALS = [("India", "Pakistan"), ("China", "Taiwan"), ("North Korea", "South Korea"), ("Israel", "Iran"),
          ("China", "India"), ("Armenia", "Azerbaijan"), ("Venezuela", "Guyana"), ("Ethiopia", "Eritrea"),
          ("Saudi Arabia", "Iran"), ("Morocco", "Algeria"), ("Serbia", "Kosovo"), ("Russia", "Poland"),
          ("North Korea", "Japan"), ("Pakistan", "Afghanistan")]

# Land held by someone other than its country when the outbreak starts.
#   "to": an existing country takes it over (occupation); "new": a breakaway government with a form of government.
#   "war": whether the two are fighting.  Polygons are (lon, lat).
SPLITS = [
    dict(of="Ukraine", to="Russia", war=False, name="occupied Crimea and Donbas", poly=[
        (32.5, 46.2), (36.7, 45.4), (36.0, 44.3), (33.3, 44.3), (32.4, 45.3)]),
    dict(of="Ukraine", to="Russia", war=False, name="occupied south and east", poly=[
        (32.6, 46.6), (35.0, 47.3), (36.4, 47.7), (37.4, 48.2), (37.9, 48.9), (38.6, 49.9), (40.3, 49.7),
        (40.2, 47.9), (38.4, 47.0), (36.8, 46.6), (35.0, 46.2), (33.6, 46.05)]),
    dict(of="Sudan", new="Rapid Support Forces", gov="warlord", war=True, poly=[
        (21.8, 23.2), (27.5, 20.0), (29.6, 16.5), (30.6, 13.6), (30.6, 10.4), (27.0, 9.3), (23.4, 9.3),
        (21.8, 12.0)]),
    dict(of="Myanmar", new="Myanmar Resistance", gov="democracy", war=True, poly=[
        (95.3, 28.6), (98.9, 28.0), (99.2, 22.4), (98.0, 21.3), (96.6, 22.5), (95.6, 24.0), (94.8, 26.0)]),
    dict(of="DR Congo", new="M23", gov="junta", war=True, poly=[
        (28.6, -0.4), (29.9, -0.4), (29.9, -3.1), (28.6, -3.3)]),
    dict(of="Yemen", new="Houthis", gov="warlord", war=False, poly=[
        (42.5, 17.6), (45.6, 17.4), (45.7, 15.4), (44.9, 13.9), (43.6, 12.7), (42.6, 14.5)]),
]

# Deserts Natural Earth doesn't outline (or outlines too small), and its 'deserts' that are really farmland.
EXTRA_DESERTS = {
    "Arabia": [(36.0, 30.5), (39.0, 32.0), (44.0, 30.5), (47.0, 29.0), (49.5, 26.0), (51.0, 24.0), (55.5, 22.5),
               (55.0, 19.0), (52.0, 17.5), (47.0, 16.8), (44.5, 17.5), (42.0, 19.5), (40.0, 22.5), (38.5, 25.0),
               (36.5, 28.0)],
    "Iran": [(51.0, 35.0), (55.0, 35.8), (59.0, 35.0), (60.5, 32.0), (59.5, 29.0), (57.0, 29.5), (54.0, 31.0),
             (52.0, 33.0)],
    "Baluchistan": [(58.5, 28.5), (61.0, 31.5), (66.0, 31.5), (66.5, 29.0), (65.0, 27.0), (62.0, 26.5), (59.5, 27.0)],
    "Australian interior": [(114.5, -22.0), (120.0, -19.5), (128.5, -17.5), (136.0, -19.5), (140.5, -22.5),
                            (142.0, -27.5), (139.5, -31.5), (135.0, -32.5), (129.0, -31.0), (123.0, -31.5),
                            (118.0, -29.5), (115.0, -26.5)],
    "Patagonia": [(-71.0, -38.0), (-66.0, -38.5), (-64.5, -42.0), (-66.5, -46.0), (-68.5, -50.0), (-71.5, -50.0),
                  (-71.0, -44.0)],
    "Horn": [(40.5, 14.5), (42.5, 13.0), (43.0, 11.0), (45.0, 10.4), (49.5, 11.0), (51.0, 10.5), (50.5, 8.0),
             (48.0, 4.5), (45.5, 2.5), (42.5, 3.0), (41.0, 4.0), (42.5, 8.0), (41.5, 10.0), (40.5, 12.5)],
    "Ordos-Alxa": [(99.0, 42.0), (106.0, 42.0), (110.0, 40.0), (110.0, 38.5), (106.0, 38.6), (103.0, 38.0),
                   (100.0, 39.0)],
    "Great Basin": [(-120.0, 42.0), (-114.0, 42.0), (-112.5, 38.0), (-114.5, 35.5), (-118.0, 35.5), (-119.5, 38.5)],
}
NOT_DESERT = {"PUNJAB", "CAATINGAS"}
# low, old ranges: hill country (highlands) rather than mountains
LOW_RANGES = {"GREAT DIVIDING RANGE", "URAL MOUNTAINS", "APPALACHIAN MTS.", "EASTERN GHATS", "Vindhya Range",
              "CRYSTAL MOUNTAINS", "Dabie Mts.", "Nan Ling Mts.", "Wuyi Mts.", "Siwalik Hills", "Lesser Khingan Range",
              "Central Highlands", "MITUMBA MTS."}

# Wetlands: (polygon, share of the tiles inside that are marsh / swamp / bog).  Natural Earth's own "Wetlands" (Pantanal,
# Entre Rios / Ibera) and the Sudd are added in make_world.py; big lowland bogs by name in WETLAND_REGIONS.
WETLANDS = {
    "Everglades": ([(-81.6, 26.9), (-80.4, 26.9), (-80.4, 25.2), (-81.2, 25.1), (-81.8, 25.8)], 0.8),
    "Louisiana bayous": ([(-93.5, 30.4), (-89.6, 30.4), (-89.0, 29.0), (-92.5, 29.4)], 0.55),
    "Okavango": ([(21.8, -18.3), (23.8, -18.6), (23.9, -20.0), (22.3, -19.9)], 0.85),
    "Vasyugan": ([(73.0, 58.5), (82.0, 58.8), (83.0, 56.3), (75.0, 56.0)], 0.7),
    "Hudson Bay Lowlands": ([(-95.0, 58.8), (-86.0, 56.0), (-81.0, 55.0), (-79.5, 51.5), (-82.0, 50.5), (-88.0, 51.5),
                             (-94.0, 56.5)], 0.6),
    "Sundarbans": ([(88.0, 22.4), (90.5, 22.5), (90.5, 21.6), (88.0, 21.6)], 0.8),
    "Pripet Marshes": ([(24.0, 52.4), (30.5, 52.4), (30.5, 51.3), (24.0, 51.3)], 0.55),
    "Mesopotamian Marshes": ([(46.2, 31.8), (47.8, 31.8), (47.8, 30.4), (46.2, 30.4)], 0.7),
    "Inner Niger Delta": ([(-5.2, 15.8), (-3.0, 15.8), (-3.0, 14.0), (-5.2, 14.0)], 0.6),
    "Lake Chad": ([(13.2, 14.2), (15.2, 14.2), (15.2, 12.4), (13.2, 12.4)], 0.6),
    "Bangweulu": ([(29.5, -10.8), (30.8, -10.8), (30.8, -12.4), (29.5, -12.4)], 0.7),
    "Llanos de Moxos": ([(-66.5, -12.5), (-63.5, -12.5), (-63.5, -15.5), (-66.5, -15.5)], 0.5),
    "Mackenzie Delta": ([(-136.5, 69.3), (-133.5, 69.3), (-133.5, 67.8), (-136.5, 67.8)], 0.7),
    "Cuvette Centrale": ([(15.8, 1.8), (17.2, 2.6), (18.6, 1.6), (20.2, 1.2), (21.6, -0.4), (20.6, -1.6),
                          (18.9, -2.4), (17.4, -3.2), (16.2, -2.4), (16.6, -0.8)], 0.5),
    "Rann of Kutch": ([(68.5, 24.6), (71.2, 24.6), (71.2, 23.4), (68.5, 23.4)], 0.6),
    "Polesie / Biebrza": ([(22.0, 53.8), (23.5, 53.8), (23.5, 53.1), (22.0, 53.1)], 0.6),
}
WETLAND_REGIONS = {"PANTANAL": 0.8, "Entre Rios": 0.35, "SUDD": 0.75, "WESTERN SIBERIAN PLAIN": 0.3,
                   "KOLYMA LOWLAND": 0.3, "NORTH SIBERIAN LOWLAND": 0.2, "VYCHEGDA LOWLAND": 0.3}

# Rainforest: forest in these humid tropical areas (besides everything within 10 degrees of the equator outside dry
# East Africa, and Natural Earth's Amazon / Congo basins) is rainforest.  (lon0, lon1, lat0, lat1) boxes get ragged
# edges; polygons are used as they are.
RAINFOREST = {
    "Southeast Asia": (90.0, 160.0, -11.0, 23.5),
    "Central America": (-93.0, -77.0, 7.0, 18.5),
    "Atlantic Forest": (-50.0, -34.0, -28.0, -5.0),
    "Eastern Madagascar": [(48.0, -12.5), (50.5, -15.0), (49.5, -20.0), (47.5, -25.0), (46.8, -24.0), (48.5, -18.0)],
    "Queensland": [(144.5, -15.0), (146.5, -15.0), (146.5, -19.0), (145.0, -19.0)],
    "Western Ghats": [(73.5, 15.5), (76.5, 15.5), (77.5, 8.5), (76.0, 8.5)],
}

# Mountain ranges Natural Earth doesn't outline (Korea, Japan, Taiwan, the Himalaya front ...): (lon, lat) polylines
# and their width in degrees.
MOUNTAINS = [
    ([(73.5, 35.3), (75.5, 34.6), (77.5, 33.0), (79.5, 30.8), (81.5, 29.8), (84.0, 28.7), (86.9, 28.0), (89.0, 27.9), (91.0, 27.9), (93.0, 28.2), (95.0, 29.2), (97.0, 28.5)], 2.0),
    ([(70.0, 35.0), (71.5, 36.2), (74.0, 37.0), (75.5, 36.0), (77.5, 35.6)], 2.2),
    ([(70.5, 38.5), (73.0, 39.0), (74.8, 38.5)], 2.2),
    ([(69.0, 41.6), (72.0, 41.6), (75.0, 42.0), (78.0, 42.0), (80.5, 42.3), (83.5, 43.0), (86.0, 43.3), (89.0, 43.4), (93.5, 43.0), (95.5, 42.6)], 1.8),
    ([(77.0, 36.5), (81.0, 35.8), (86.0, 36.2), (90.0, 36.3), (94.0, 35.8), (98.0, 35.0)], 1.4),
    ([(94.0, 39.3), (97.0, 39.2), (100.5, 38.0), (103.0, 37.0)], 1.0),
    ([(98.0, 32.5), (99.0, 29.0), (99.3, 26.5), (99.0, 24.0), (98.6, 22.5)], 2.2),
    ([(103.0, 33.0), (104.5, 34.0), (107.0, 33.8), (110.5, 33.8)], 0.9),
    ([(107.5, 32.4), (109.0, 32.1), (110.6, 31.7)], 0.6),
    ([(83.5, 50.5), (87.0, 50.0), (90.0, 49.0), (93.0, 47.5), (96.5, 45.8)], 1.6),
    ([(89.0, 52.2), (95.0, 52.6), (101.0, 51.8)], 1.3),
    ([(97.5, 48.5), (100.0, 47.5), (102.0, 46.8)], 1.2),
    ([(119.0, 53.5), (121.0, 50.0), (120.5, 46.5), (118.5, 43.5)], 1.3),
    ([(127.0, 41.5), (129.0, 42.3)], 1.0),
    ([(128.5, 38.8), (129.0, 36.3)], 0.6),
    ([(127.0, 72.0), (129.0, 67.0), (133.0, 63.5), (137.0, 62.0)], 2.0),
    ([(138.0, 68.5), (143.0, 66.0), (148.0, 63.0), (150.0, 62.0)], 2.0),
    ([(120.0, 56.5), (127.0, 56.0), (134.0, 56.5)], 1.4),
    ([(134.5, 50.5), (136.0, 47.5), (134.5, 44.5)], 1.0),
    ([(59.5, 68.0), (60.0, 64.0), (59.0, 60.0), (59.0, 56.0), (58.5, 53.0)], 1.0),
    ([(37.5, 44.3), (40.5, 43.4), (43.5, 42.8), (46.0, 42.0), (48.5, 41.2)], 1.2),
    ([(43.5, 40.8), (45.5, 39.8), (46.3, 39.0)], 1.0),
    ([(29.0, 37.0), (32.0, 37.0), (35.0, 37.6), (38.0, 38.0), (41.0, 38.5), (43.5, 39.2)], 1.2),
    ([(31.0, 40.7), (35.0, 40.8), (39.0, 40.4), (42.0, 40.8)], 0.8),
    ([(45.0, 37.0), (47.0, 34.5), (49.5, 32.0), (52.0, 30.0), (55.0, 28.0), (57.5, 27.2)], 1.8),
    ([(48.5, 37.5), (51.5, 36.2), (54.5, 36.7), (57.0, 37.5)], 0.9),
    ([(69.5, 31.5), (68.5, 29.5), (67.5, 28.0)], 0.9),
    ([(73.5, 20.5), (74.0, 16.0), (75.5, 12.0), (77.0, 9.0)], 0.7),
    ([(93.5, 24.5), (94.5, 21.0), (94.8, 18.0)], 0.8),
    ([(98.5, 19.5), (99.0, 15.0), (99.0, 10.5)], 0.8),
    ([(103.5, 21.0), (105.5, 18.5), (107.0, 16.0), (108.0, 14.5)], 0.9),
    ([(36.0, 28.5), (39.0, 23.0), (42.5, 18.0), (44.0, 14.5)], 0.9),
    ([(38.0, 14.0), (39.5, 11.5), (39.0, 9.0), (38.0, 7.0)], 1.0),
    ([(35.5, 33.0), (36.3, 35.0)], 0.4),
    ([(95.5, 4.5), (98.0, 2.5), (101.0, -1.0), (104.0, -4.8)], 0.7),
    ([(115.0, 1.0), (116.5, 5.5)], 1.0),
    ([(134.5, -3.6), (138.0, -4.2), (141.0, -4.8), (144.5, -5.8), (147.0, -7.5)], 1.5),
    ([(120.9, 23.0), (121.4, 24.5)], 0.6),
    ([(121.0, 16.0), (121.0, 18.0)], 0.7),
    ([(136.5, 35.2), (138.5, 36.5)], 0.6),
    ([(139.5, 37.0), (140.8, 40.5)], 0.5),
]
