"""Generates maps/middle_earth: north-western Middle-earth in September of T.A. 3018, just before the War of the Ring.

    python make_middleearth.py                   (writes maps/middle_earth)
    python main.py maps/middle_earth

Laid out on the "Realm of Middle Earth" general map (in its pixel coordinates, ~0.92 miles per pixel; extended
south to take in Near Harad and Umbar), 5 miles per tile.
Everything is drawn from the lists below - coasts, seas and lakes, mountain ranges, hills, forests, marshes, deserts,
rivers (the Anduin is open water from the Gladden Fields to the sea; the others are marshy river valleys), the
realms of the time with their peoples, armies, alliances and fortresses, and the wars already being fought (Mordor
against Gondor, Isengard against Rohan).  No airports and no warheads; ports at the Grey Havens, Dol Amroth, Pelargir,
Umbar...  The outbreak starts at Bree, in Eriador.
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw

import mapio
import terrain as TR
from make_world import fbm, dilate, blur
from terrain import (DEEP, SHALLOW, GRASS, FOREST, MOUNTAIN, DESERT, ICE, URBAN, SUBURBAN, HIGHLANDS, TUNDRA,
                     WETLAND)

MILES = 5.0                      # miles per tile
MILES_PER_PX = 0.92              # the reference map's scale
UNIT = MILES / MILES_PER_PX      # reference-map pixels per tile
WIDTH, HEIGHT = 2000, 1800       # reference-map pixels
SS = 2                           # supersampling when drawing
START = "3018-09-23"             # Frodo leaves Bag End

# ------------------------------------------------------------------------------------------------ geography
# Coordinates are pixels of the reference map (the "Realm of Middle Earth" general map, 2000 x 1526 px, about 0.92
# miles per pixel), extended south to 1800 px to take in Near Harad and Umbar.  x east, y south.
COAST = [(70, 170), (150, 60), (260, 25), (700, 0), (2000, 0), (2000, 1800), (1050, 1800), (1035, 1740),
         (1060, 1700), (1100, 1680), (1110, 1600), (1100, 1530), (1105, 1470), (1090, 1410), (1095, 1340),
         (1120, 1280), (1150, 1262), (1120, 1250), (1070, 1262), (1030, 1240), (1010, 1215), (985, 1190), (960, 1200),
         (930, 1185), (880, 1180), (800, 1170), (700, 1175), (600, 1170), (520, 1165), (470, 1150), (490, 1125),
         (550, 1100), (590, 1050), (610, 1000), (580, 960), (545, 900), (540, 840), (555, 790), (520, 770),
         (470, 740), (420, 700), (360, 680), (290, 650), (220, 630), (150, 590), (100, 520), (170, 492), (245, 480),
         (190, 455), (110, 440), (80, 380), (60, 300)]
WATER = {                        # seas, bays and lakes inside the land
    "Ice Bay of Forochel": [(300, 40), (640, 35), (650, 100), (480, 110), (320, 90)],
    "Lake Evendim": [(380, 250), (430, 245), (440, 290), (390, 300)],
    "Sea of Rhun": [(1700, 560), (1790, 530), (1880, 540), (1940, 580), (1920, 680), (1860, 760), (1760, 770),
                    (1720, 700), (1700, 640)],
    "Sea of Nurnen": [(1570, 1170), (1680, 1160), (1700, 1230), (1620, 1260), (1570, 1230)],
    "Long Lake": [(1350, 300), (1362, 300), (1366, 340), (1352, 340)],
    "Nen Hithoel": [(1185, 930), (1205, 930), (1210, 965), (1190, 968)],
}
ANDUIN_OPEN = [(1060, 520), (1070, 650), (1100, 720), (1140, 820), (1170, 900), (1195, 945), (1220, 980),
               (1250, 1010), (1270, 1030), (1300, 1060), (1290, 1130), (1260, 1190), (1225, 1215), (1180, 1235),
               (1130, 1258)]
RIVERS = {                       # marshy river valleys: slow going (wetland), but no barrier
    "Upper Anduin": [(1100, 220), (1090, 330), (1080, 380), (1060, 520)],
    "Brandywine": [(420, 290), (530, 400), (560, 450), (540, 560), (480, 660), (420, 700)],
    "Greyflood": [(820, 520), (740, 600), (620, 700), (560, 780)],
    "Hoarwell": [(840, 250), (820, 450), (820, 520)],
    "Loudwater": [(920, 380), (850, 470)],
    "Isen": [(880, 880), (900, 930), (820, 960), (700, 990), (610, 1000)],
    "Entwash": [(1000, 840), (1080, 900), (1170, 980), (1240, 1000)],
    "River Running": [(1360, 330), (1560, 420), (1640, 500), (1720, 580)],
    "Redwater": [(1600, 300), (1640, 400), (1660, 480)],
    "Forest River": [(1290, 300), (1350, 310)],
    "Harnen": [(1440, 1300), (1250, 1420), (1105, 1470)],
    "Poros": [(1360, 1240), (1250, 1280), (1150, 1300)],
}
MOUNTAINS = {                    # ridge lines and their width: mountains in the middle, highlands on the flanks
    "Ered Luin (north)": ([(235, 140), (255, 250), (275, 350), (290, 420)], 45),
    "Ered Luin (south)": ([(290, 520), (320, 590), (340, 620)], 45),
    "Misty Mountains": ([(1000, 190), (1020, 250), (1000, 380), (980, 460), (955, 560), (940, 650), (930, 760),
                         (890, 860), (870, 890)], 45),
    "Mountains of Angmar": ([(640, 110), (760, 120), (850, 140), (960, 190)], 35),
    "Grey Mountains": ([(1050, 200), (1180, 200), (1300, 175), (1400, 170)], 40),
    "Iron Hills": ([(1480, 280), (1690, 290)], 30),
    "White Mountains": ([(500, 1120), (580, 1080), (650, 1040), (760, 1005), (880, 990), (960, 1010), (1060, 1040),
                         (1160, 1060), (1265, 1065)], 45),
    "Lebennin hills": ([(960, 1040), (990, 1100), (1010, 1150)], 30),
    "Ephel Duath": ([(1320, 975), (1340, 1080), (1360, 1150), (1385, 1230), (1450, 1230), (1560, 1215),
                     (1700, 1190), (1880, 1180)], 35),
    "Ered Lithui": ([(1330, 965), (1450, 960), (1600, 940), (1720, 935), (1860, 930)], 35),
    "Mountains of Rhun": ([(1630, 700), (1700, 760)], 30),
}
PEAKS = {"Mount Doom": (1450, 1075, 14), "Erebor": (1345, 255, 16), "Methedras": (875, 880, 12)}
HILLS = {                        # (x, y, radius): highlands
    "Barrow-downs": (590, 440, 20), "South Downs": (650, 465, 25), "North Downs": (520, 270, 40),
    "Weather Hills": (700, 380, 25), "Ettenmoors": (860, 300, 45), "Coldfells": (820, 250, 35),
    "Emyn Muil": (1200, 890, 30), "Dunland": (840, 810, 40), "Tower Hills": (330, 450, 12),
    "Pinnath Gelin": (760, 1110, 30), "Emyn Arnen": (1310, 1100, 12), "Hills of Evendim": (430, 230, 25),
    "Khand uplands": (1800, 1260, 60), "Hills of Rhun": (1900, 900, 50),
}
FORESTS = {                      # polygons, or (x, y, radius); with the share of the ground that is wooded
    "Mirkwood": ([(1120, 260), (1290, 230), (1360, 290), (1360, 500), (1320, 640), (1210, 640), (1150, 560),
                  (1120, 400)], 0.95),
    "Fangorn": ([(950, 720), (1040, 710), (1050, 800), (1010, 850), (950, 830)], 1.0),
    "Lothlorien": ((1030, 650, 28), 1.0), "Old Forest": ((580, 425, 16), 1.0), "Chetwood": ((655, 400, 16), 0.9),
    "Trollshaws": ((870, 390, 30), 0.8), "Eryn Vorn": ((420, 690, 25), 0.9), "Firien Wood": ((1150, 1045, 14), 1.0),
    "Druadan Forest": ((1215, 1050, 20), 0.9),
    "Ithilien": ([(1300, 1060), (1330, 1060), (1360, 1230), (1300, 1240)], 0.5),
    "Minhiriath": ((610, 650, 55), 0.35), "Lindon woods": ((150, 350, 45), 0.4),
    "Eryn Lasgalen eaves": ((1100, 290, 25), 0.5),
}
MARSHES = {                      # (x, y, radius)
    "Dead Marshes": (1270, 955, 18), "Nindalf": (1180, 975, 18), "Gladden Fields": (1060, 540, 18),
    "Swanfleet": (800, 570, 22), "Ethir Anduin": (1135, 1255, 18), "Midgewater Marshes": (680, 410, 13),
    "Long Marshes": (1300, 340, 13), "Mouths of Entwash": (1230, 1000, 13),
    "The Marish": (545, 440, 9), "Mouths of Isen": (625, 995, 14), "Fords of Isen fens": (860, 935, 7),
    "Lhun estuary": (215, 470, 10), "Nurnen shores": (1630, 1255, 14), "Sea of Rhun fens": (1700, 660, 16),
    "Mouths of Gwathlo": (575, 785, 12), "Lefnui fens": (540, 1140, 10), "Ethir of Poros": (1160, 1300, 12),
    "Anduin vale marsh": (1085, 450, 10),
}
# scattered woodland and copses (on top of the named forests): area, share of the ground wooded
WOODLAND = {
    "Eriador": ([(300, 200), (900, 220), (900, 820), (560, 830), (300, 640)], 0.2),
    "Lindon": ([(60, 170), (300, 120), (320, 650), (60, 560)], 0.35),
    "Anduin vale": ([(1030, 240), (1160, 240), (1160, 720), (1040, 720)], 0.3),
    "Rhovanion": ([(1360, 380), (1700, 380), (1650, 700), (1360, 700)], 0.18),
    "Gondor": ([(480, 1060), (1300, 1030), (1300, 1260), (480, 1180)], 0.18),
    "Ithilien and Harondor": ([(1290, 1040), (1380, 1040), (1380, 1300), (1290, 1300)], 0.3),
    "Enedwaith": ([(560, 700), (860, 700), (880, 980), (600, 1000)], 0.15),
    "Rohan": ([(900, 850), (1240, 850), (1240, 1030), (900, 1030)], 0.04),
    "Rhun": ([(1500, 450), (2000, 380), (2000, 1100), (1550, 950)], 0.1),
    "Harad": ([(1100, 1300), (2000, 1300), (2000, 1800), (1050, 1800)], 0.06),
}
DOWNS = 0.13                     # share of open country that is rolling downs and hills (highlands)
DESERTS = {                      # polygons and the share of them that is barren
    "Brown Lands": ([(1110, 740), (1220, 720), (1250, 830), (1170, 860), (1120, 820)], 0.9),
    "Dagorlad": ([(1230, 900), (1310, 900), (1320, 960), (1240, 965)], 1.0),
    "Gorgoroth": ([(1350, 990), (1500, 990), (1520, 1100), (1370, 1120)], 1.0),
    "Lithlad": ([(1500, 980), (1830, 960), (1820, 1060), (1520, 1090)], 1.0),
    "South Gondor": ([(1110, 1300), (1400, 1270), (1430, 1300), (1250, 1420), (1110, 1460)], 0.7),
    "Harad": ([(1100, 1460), (2000, 1300), (2000, 1800), (1050, 1800)], 0.6),
    "Khand": ([(1650, 1200), (2000, 1100), (2000, 1350), (1650, 1320)], 0.5),
    "East Rhun": ([(1850, 800), (2000, 800), (2000, 1100), (1850, 1100)], 0.5),
}

# ------------------------------------------------------------------------------------------------ the realms
# name, alliance, land (polygon or (x, y, radius)), people per tile on open farmland, the least share of that any of
# its land holds (desert orc-camps, forest elves ...), army strength 0..1, form of government, personality
REALMS = [
    dict(name="Rangers of the North", side="Free Peoples", land=[(560, 280), (830, 250), (880, 450), (800, 520),
         (660, 520), (570, 470)], rural=3, floor=1.0, army=0.8, gov="tribal", traits={"caution": 1.3}),
    dict(name="Gondor", side="Free Peoples", land=[(480, 1140), (600, 1060), (760, 1010), (880, 1000), (960, 1020),
         (1060, 1040), (1160, 1040), (1230, 1010), (1290, 990), (1320, 990), (1345, 1100), (1370, 1230),
         (1300, 1260), (1180, 1260), (1100, 1290), (1030, 1240), (900, 1190), (600, 1180), (470, 1160)],
         rural=70, floor=0.25, army=0.8, gov="national", traits={"caution": 1.3}),
    dict(name="Rohan", side="Free Peoples", land=[(910, 860), (1000, 850), (1060, 740), (1150, 760), (1200, 860),
         (1230, 960), (1240, 1010), (1160, 1030), (1060, 1020), (950, 1000), (900, 960)],
         rural=30, floor=0.3, army=0.75, gov="national", traits={"aggression": 1.1}),
    dict(name="Isengard", side="Shadow", land=[(845, 845), (880, 830), (905, 845), (920, 880), (912, 915), (875, 928),
         (848, 905), (838, 870)],
         rural=60, floor=0.6, army=0.8, gov="national", traits={"aggression": 1.4}),
    dict(name="Dunland", side="Shadow", land=[(700, 720), (850, 700), (860, 840), (860, 930), (780, 960),
         (700, 870)], rural=25, floor=0.4, army=0.3, gov="tribal", traits={}),
    dict(name="Mordor", side="Shadow", land=[(1320, 960), (1450, 945), (1600, 925), (1750, 920), (1885, 930), (1895, 1060),
         (1885, 1195), (1700, 1205), (1560, 1225), (1385, 1250), (1350, 1150), (1335, 1060)],
         extra=[(1170, 600, 40)], rural=70, floor=0.6, army=1.0, gov="national",
         traits={"aggression": 1.6, "caution": 0.8}),
    dict(name="Rhun", side="Shadow", land=[(1600, 450), (2000, 380), (2000, 1100), (1880, 1100), (1880, 920),
         (1560, 940), (1480, 800), (1520, 600)], rural=22, floor=0.3, army=0.55, gov="national",
         traits={"aggression": 1.3}),
    dict(name="Khand", side="Shadow", land=[(1650, 1215), (1760, 1180), (1880, 1150), (2000, 1100), (2000, 1350), (1880, 1370),
         (1760, 1340), (1660, 1320)],
         rural=35, floor=0.35, army=0.55, gov="warlord", traits={"aggression": 1.2}),
    dict(name="Harad", side="Shadow", land=[(1250, 1420), (1450, 1300), (1650, 1320), (2000, 1350), (2000, 1800),
         (1150, 1800), (1120, 1600), (1110, 1480)], rural=30, floor=0.3, army=0.6, gov="national",
         traits={"aggression": 1.2}),
    dict(name="Umbar", side="Shadow", land=[(1000, 1640), (1150, 1620), (1170, 1800), (1000, 1800)],
         rural=70, floor=0.4, army=0.6, gov="warlord", traits={"aggression": 1.3}),
    dict(name="Beornings and Woodmen", side="Free Peoples", land=[(1035, 270), (1100, 262), (1135, 290),
         (1150, 400), (1145, 520), (1110, 590), (1070, 600), (1045, 520), (1030, 400)], rural=25, floor=0.6, army=0.5, gov="tribal", traits={}),
    dict(name="Woodland Realm", side="Free Peoples", land=[(1150, 250), (1220, 232), (1300, 238), (1345, 265), (1350, 320), (1320, 360), (1240, 372), (1180, 350),
         (1155, 300)],
         rural=25, floor=0.6, army=0.75, gov="national", traits={"caution": 1.5}),
    dict(name="Lothlorien", side="Free Peoples", land=(1030, 650, 38), rural=30, floor=0.6, army=0.85,
         gov="national", traits={"caution": 1.5}),
    dict(name="Moria", side="Shadow", land=(962, 612, 26), rural=0, floor=0.0, army=0.5, gov="warlord",
         traits={"aggression": 1.3}),
    dict(name="Gundabad", side="Shadow", land=[(935, 160), (990, 140), (1070, 165), (1075, 230), (1050, 295), (990, 305), (950, 270),
         (930, 210)], rural=20,
         floor=0.6, army=0.5, gov="warlord", traits={"aggression": 1.3}),
    dict(name="Rivendell", side="Free Peoples", land=(925, 375, 30), rural=15, floor=1.0, army=0.85,
         gov="national", traits={"caution": 1.5}),
    dict(name="Lindon", side="Free Peoples", land=[(60, 170), (240, 120), (260, 300), (280, 440), (300, 470),
         (310, 500), (280, 520), (320, 620), (260, 640), (150, 590), (80, 420)], rural=25, floor=0.5, army=0.8,
         gov="national", traits={"caution": 1.5}),
    dict(name="The Shire", side="Free Peoples", land=[(440, 395), (500, 385), (555, 395), (572, 430), (565, 470), (530, 488),
         (470, 486), (438, 460), (430, 425)], rural=100, floor=0.3, army=0.05, gov="democracy", traits={"caution": 0.6}),
    dict(name="Bree-land", side="Free Peoples", land=(632, 415, 25), rural=40, floor=0.4, army=0.08,
         gov="democracy", traits={"caution": 0.7}),
    dict(name="Dale", side="Free Peoples", land=[(1300, 215), (1380, 200), (1450, 215), (1460, 290), (1430, 360), (1370, 380), (1320, 350),
         (1305, 285)], rural=50,
         floor=0.4, army=0.45, gov="national", traits={}),
    dict(name="Erebor", side="Free Peoples", land=(1345, 255, 20), rural=0, floor=0.0, army=0.7, gov="national",
         traits={"caution": 1.2}),
    dict(name="Iron Hills", side="Free Peoples", land=[(1470, 250), (1560, 225), (1680, 235), (1725, 270), (1690, 320), (1580, 330), (1490, 310)],
         rural=40, floor=0.5, army=0.7, gov="national", traits={"caution": 1.2}),
    dict(name="Fangorn", side="Free Peoples", land=(995, 780, 45), rural=15, floor=1.0, army=0.9, gov="tribal",
         traits={"caution": 0.5, "aggression": 1.5}),
]
# towns and fortresses: name, realm, x, y, people at the centre, radius (tiles), garrison level (0 = none)
PLACES = [
    ("Minas Tirith", "Gondor", 1278, 1060, 255, 2, 7), ("Osgiliath", "Gondor", 1300, 1058, 90, 0, 6),
    ("Cair Andros", "Gondor", 1262, 1020, 90, 0, 6), ("Pelargir", "Gondor", 1222, 1212, 230, 1, 6),
    ("Dol Amroth", "Gondor", 1005, 1205, 230, 1, 7), ("Linhir", "Gondor", 1080, 1210, 160, 1, 0),
    ("Calembel", "Gondor", 850, 1120, 120, 0, 0), ("Ethring", "Gondor", 900, 1110, 110, 0, 0),
    ("Erech", "Gondor", 820, 1070, 100, 0, 0), ("Tarnost", "Gondor", 1060, 1160, 110, 0, 0),
    ("Lossarnach", "Gondor", 1230, 1100, 150, 1, 0), ("Henneth Annun", "Gondor", 1325, 1100, 60, 0, 0),
    ("Edhellond", "Gondor", 980, 1215, 80, 0, 0),
    ("Edoras", "Rohan", 955, 965, 210, 1, 6), ("Helm's Deep", "Rohan", 885, 950, 170, 0, 7),
    ("Aldburg", "Rohan", 1100, 1010, 140, 0, 0), ("Dunharrow", "Rohan", 960, 985, 90, 0, 6),
    ("Westfold", "Rohan", 900, 925, 90, 0, 0),
    ("Isengard", "Isengard", 875, 880, 255, 1, 7),
    ("Dunharg", "Dunland", 800, 820, 110, 0, 0),
    ("Barad-dur", "Mordor", 1525, 1050, 255, 1, 7), ("Minas Morgul", "Mordor", 1342, 1080, 220, 0, 7),
    ("Cirith Ungol", "Mordor", 1355, 1060, 130, 0, 7), ("Morannon", "Mordor", 1325, 975, 220, 1, 7),
    ("Durthang", "Mordor", 1360, 990, 160, 0, 0), ("Udun", "Mordor", 1350, 1005, 150, 0, 0),
    ("Nurn", "Mordor", 1520, 1160, 170, 1, 0), ("Dol Guldur", "Mordor", 1170, 600, 220, 1, 7),
    ("Near Harad", "Harad", 1350, 1500, 200, 1, 0), ("Harad Road", "Harad", 1250, 1450, 140, 0, 0),
    ("Far Harad", "Harad", 1550, 1700, 200, 1, 0), ("Haradwaith", "Harad", 1750, 1550, 160, 0, 0),
    ("Umbar", "Umbar", 1075, 1700, 255, 2, 6), ("Khand", "Khand", 1800, 1250, 170, 1, 0),
    ("Rhun", "Rhun", 1850, 850, 180, 1, 0), ("Dorwinion", "Rhun", 1650, 560, 170, 1, 0),
    ("Easterling Camps", "Rhun", 1700, 880, 150, 0, 0),
    ("Thranduil's Halls", "Woodland Realm", 1275, 300, 170, 0, 7),
    ("Caras Galadhon", "Lothlorien", 1030, 655, 190, 0, 7), ("Moria", "Moria", 962, 612, 230, 1, 7),
    ("Mount Gundabad", "Gundabad", 1000, 200, 230, 1, 7),
    ("Beorn's House", "Beornings and Woodmen", 1095, 400, 70, 0, 0),
    ("Woodmen-town", "Beornings and Woodmen", 1130, 480, 100, 0, 0),
    ("Rhosgobel", "Beornings and Woodmen", 1135, 530, 40, 0, 0), ("Rivendell", "Rivendell", 925, 375, 140, 0, 7),
    ("Mithlond", "Lindon", 240, 478, 170, 1, 6), ("Harlond", "Lindon", 200, 560, 90, 0, 0),
    ("Forlond", "Lindon", 130, 330, 90, 0, 0),
    ("Hobbiton", "The Shire", 490, 425, 170, 0, 0), ("Michel Delving", "The Shire", 460, 445, 160, 0, 0),
    ("Bywater", "The Shire", 505, 428, 140, 0, 0), ("Tuckborough", "The Shire", 480, 462, 140, 0, 0),
    ("Buckland", "The Shire", 562, 440, 140, 0, 0), ("Frogmorton", "The Shire", 525, 425, 110, 0, 0),
    ("Bree", "Bree-land", 630, 415, 170, 0, 0), ("Archet", "Bree-land", 642, 402, 80, 0, 0),
    ("Staddle", "Bree-land", 643, 425, 80, 0, 0),
    ("Weathertop", "Rangers of the North", 715, 410, 40, 0, 0),
    ("The Angle", "Rangers of the North", 840, 450, 50, 0, 0),
    ("Dale", "Dale", 1350, 282, 190, 0, 0), ("Esgaroth", "Dale", 1355, 322, 190, 0, 0),
    ("Erebor", "Erebor", 1345, 255, 230, 1, 7), ("Iron Hills", "Iron Hills", 1600, 285, 170, 1, 6),
    ("Wellinghall", "Fangorn", 990, 770, 45, 0, 0),
    ("Tharbad", None, 735, 600, 35, 0, 0), ("Lond Daer", None, 565, 775, 30, 0, 0),
]
PORTS = [("Mithlond", 6), ("Harlond", 3), ("Dol Amroth", 5), ("Pelargir", 6), ("Umbar", 7), ("Edhellond", 2),
         ("Linhir", 3), ("Lond Daer", 1)]
WARS = [("Mordor", "Gondor"), ("Isengard", "Rohan")]
RIVALS = [("Gondor", "Harad"), ("Gondor", "Umbar"), ("Rohan", "Dunland"), ("Dale", "Rhun"), ("Erebor", "Rhun"),
          ("Woodland Realm", "Mordor"), ("Lothlorien", "Moria"), ("Lothlorien", "Mordor"),
          ("Beornings and Woodmen", "Gundabad"), ("Rivendell", "Gundabad"), ("Fangorn", "Isengard")]
OUTBREAK = "Bree"


# ------------------------------------------------------------------------------------------------ drawing
COLS, ROWS = int(WIDTH / UNIT), int(HEIGHT / UNIT)


def _px(pts):
    return [(x / UNIT * SS, y / UNIT * SS) for x, y in pts]


def _canvas():
    img = Image.new("L", (COLS * SS, ROWS * SS), 0)
    return img, ImageDraw.Draw(img)


def _down(img, thresh=0.5):
    a = np.asarray(img, dtype=np.float32).reshape(ROWS, SS, COLS, SS).mean(axis=(1, 3))
    return a > 255 * thresh


def poly(pts, thresh=0.5):
    img, d = _canvas()
    d.polygon(_px(pts), fill=255)
    return _down(img, thresh)


def disc(x, y, r):
    img, d = _canvas()
    d.ellipse([(x - r) / UNIT * SS, (y - r) / UNIT * SS, (x + r) / UNIT * SS, (y + r) / UNIT * SS], fill=255)
    return _down(img, 0.4)


def line(pts, width):
    img, d = _canvas()
    w = max(1, int(width / UNIT * SS))
    p = _px(pts)
    d.line(p, fill=255, width=w)
    for x, y in p:
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=255)
    return _down(img, 0.4)


def shape(s):
    return disc(*s) if isinstance(s, tuple) else poly(s)


_FIELDS = {}


def _field(salt, cells=(8, 16, 32, 64)):
    if salt not in _FIELDS:
        _FIELDS[salt] = fbm(np.random.default_rng(1000 + salt), ROWS, COLS, cells=cells)
    return _FIELDS[salt]


def ragged(mask, amp=8.0, salt=0, roughness=0.3):
    """Natural-looking shapes: the shape is warped by smooth noise (its outline moves up to `amp` tiles in and out),
    then its edge roughened a little."""
    dy = (_field(2 * salt) - 0.5) * 2 * amp
    dx = (_field(2 * salt + 1) - 0.5) * 2 * amp
    rr = np.clip(np.rint(np.arange(ROWS)[:, None] + dy), 0, ROWS - 1).astype(int)
    cc = np.clip(np.rint(np.arange(COLS)[None, :] + dx), 0, COLS - 1).astype(int)
    warped = mask[rr, cc]
    if roughness <= 0:
        return warped
    fine = _field(500 + salt, cells=(32, 64, 128))
    return blur(warped.astype(np.float64), 1.2, False) + roughness * 2 * (fine - 0.5) > 0.5


def rc(x, y):
    return min(ROWS - 1, int(y / UNIT)), min(COLS - 1, int(x / UNIT))


def build(seed=7):
    rng = np.random.default_rng(seed)
    noise = fbm(rng, ROWS, COLS, cells=(8, 16, 32, 64))
    noise2 = fbm(rng, ROWS, COLS, cells=(12, 24, 48, 96))
    land = ragged(poly(COAST), 9, salt=1, roughness=0.25)
    for i, pts in enumerate(WATER.values()):
        land &= ~ragged(poly(pts), 5, salt=10 + i)
    T = np.where(land, GRASS, DEEP).astype(np.int32)
    yy = (np.arange(ROWS)[:, None] + 0.5) * UNIT + np.zeros((1, COLS))
    # the cold north: tundra, and ice in the far north
    wob = (noise - 0.5) * 120
    T[land & (yy + wob < 190)] = TUNDRA
    T[land & (yy + wob < 80) & (noise2 < 0.6)] = ICE
    for i, (pts, share) in enumerate(DESERTS.values()):
        T[land & ragged(poly(pts), 18, salt=20 + i) & (noise2 < share)] = DESERT
    for i, (s_, share) in enumerate(FORESTS.values()):
        m = ragged(shape(s_), 14, salt=40 + i)
        T[land & m & ((noise < share) if share < 1 else True) & (T != DESERT)] = FOREST
    fine = fbm(np.random.default_rng(seed + 1), ROWS, COLS, cells=(24, 48, 96, 192))
    fine2 = fbm(np.random.default_rng(seed + 2), ROWS, COLS, cells=(20, 40, 80, 160))
    for i, (pts, share) in enumerate(WOODLAND.values()):
        m = ragged(poly(pts), 20, salt=220 + i, roughness=0.2)
        T[land & m & (fine < np.quantile(fine, share)) & (T == GRASS)] = FOREST
    T[land & (fine2 > np.quantile(fine2, 1 - DOWNS)) & (T == GRASS)] = HIGHLANDS
    for i, (x, y, r) in enumerate(HILLS.values()):
        T[land & ragged(disc(x, y, r), 9, salt=60 + i)] = HIGHLANDS
    for i, (pts, width) in enumerate(MOUNTAINS.values()):
        T[land & ragged(line(pts, width * 1.4), 6, salt=80 + i) & (T != MOUNTAIN)] = HIGHLANDS
        T[land & ragged(line(pts, width * 0.7), 6, salt=80 + i)] = MOUNTAIN
    for i, (x, y, r) in enumerate(PEAKS.values()):
        T[land & ragged(disc(x, y, r), 2, salt=120 + i)] = MOUNTAIN
    for i, (x, y, r) in enumerate(MARSHES.values()):
        T[land & ragged(disc(x, y, r), 5, salt=140 + i) & (noise < 0.85)] = WETLAND
    for i, pts in enumerate(RIVERS.values()):
        T[land & ragged(line(pts, 6), 7, salt=160 + i, roughness=0) & (T != MOUNTAIN)] = WETLAND
        # water-meadows and fens along the rivers, here and there
        T[land & ragged(line(pts, 22), 7, salt=160 + i, roughness=0) & (fine2 < np.quantile(fine2, 0.3)) & (T == GRASS)] = WETLAND
    anduin = ragged(line(ANDUIN_OPEN, 6), 5, salt=180, roughness=0)
    T[anduin] = SHALLOW
    land = TR.is_land(T)
    # water: shallow along the coasts and in the lakes, deep further out
    sea = ~land
    lakes = np.zeros(land.shape, dtype=bool)
    for i, pts in enumerate(WATER.values()):
        lakes |= ragged(poly(pts), 5, salt=10 + i)
    T[sea & dilate(land, 1, False)] = SHALLOW
    T[lakes & sea] = SHALLOW

    # realms
    O = np.zeros(T.shape, dtype=np.int32)
    names = [r["name"] for r in REALMS]
    for k, realm in enumerate(REALMS, start=1):
        m = shape(realm["land"])
        for e in realm.get("extra", []):
            m |= disc(*e)
        amp = min(22.0, max(4.0, np.sqrt(m.sum()) / 4))        # (small realms aren't warped out of shape)
        O[ragged(m, amp, salt=7, roughness=0.3) & land] = k     # (one warp for all: borders meet)
    O[~land] = 0
    # people: farmland and towns; orc-hosts camp in desert and mountain, elves live in the woods
    H = np.zeros(T.shape)
    # the countryside fills up around the towns: a town's pull fades with distance (two scales: its farms, its region)
    pull = np.zeros(T.shape)
    for name, realm, x, y, people, radius, level in PLACES:
        r, c = rc(x, y)
        pull[r, c] += people * (1 + radius)
    pull = blur(pull, 5.0, False) / 40.0 + blur(pull, 18.0, False) / 6.0
    pull = np.clip(pull / max(float(np.quantile(pull[land], 0.97)), 1e-9), 0, 1.6)
    hamlets = np.where(fine > np.quantile(fine, 0.85), 1.6, 1.0)                    # villages and hamlets dotted about
    jit = (0.6 + 0.8 * noise2) * (0.75 + 0.5 * fine2) * hamlets
    for k, realm in enumerate(REALMS, start=1):
        m = (O == k) & TR.habitable(T)
        dens = np.maximum(TR.DENSITY[T], realm["floor"])
        H[m] = (realm["rural"] * dens * jit * (0.35 + 1.1 * pull))[m]
    wild = (O == 0) & TR.habitable(T)
    H[wild] = (6 * TR.DENSITY[T] * jit * (0.5 + pull))[wild]     # a few wanderers in the wilds
    H = np.where(land, blur(H, 1.0, False), 0.0)                 # (no hard steps from one tile to the next)
    D = np.full(T.shape, 2, dtype=np.int32)
    by_name = {nm: k for k, nm in enumerate(names, start=1)}
    capitals, cities, sites = {}, [], []
    for name, realm, x, y, people, radius, level in PLACES:
        r, c = rc(x, y)
        if not land[r, c]:                                      # (a harbour drawn just off the coast)
            near = [(abs(dr) + abs(dc), r + dr, c + dc) for dr in range(-4, 5) for dc in range(-4, 5)
                    if 0 <= r + dr < ROWS and 0 <= c + dc < COLS and land[r + dr, c + dc]]
            if near:
                _, r, c = min(near)
        k = by_name.get(realm, 0)
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                rr, cc = r + dr, c + dc
                if not (0 <= rr < ROWS and 0 <= cc < COLS) or not land[rr, cc]:
                    continue
                ring = max(abs(dr), abs(dc))
                H[rr, cc] = max(H[rr, cc], people * (1.0 if ring == 0 else 0.75 if ring == 1 else 0.55))
                if T[rr, cc] not in (MOUNTAIN, ICE, WETLAND):
                    T[rr, cc] = URBAN if ring == 0 and people >= 150 else SUBURBAN if people >= 60 else T[rr, cc]
                if k:
                    O[rr, cc] = k
        if not land[r, c]:
            continue
        cities.append(dict(name=name, row=r, col=c, pop=round(people / 1000.0, 3)))
        if k and str(k) not in capitals:
            capitals[str(k)] = [r, c]
        if k and level:
            D[r, c] = max(D[r, c], min(level, 4))
            sites.append(dict(civ=k, row=r, col=c, level=level, radius=1 if radius else 0))
    H = np.clip(np.rint(H), 0, 255).astype(np.int32)
    H[~land] = 0
    for k, realm in enumerate(REALMS, start=1):                 # every realm has somewhere its people live
        if str(k) not in capitals:
            m = O == k
            if m.any():
                rr, cc = np.unravel_index(int(np.argmax(np.where(m, H, -1))), H.shape)
                capitals[str(k)] = [int(rr), int(cc)]
    Z = np.zeros(T.shape, dtype=np.int32)
    pr, pc = next((c["row"], c["col"]) for c in cities if c["name"] == OUTBREAK)
    Z[pr, pc] = 40
    Z[pr, pc + 1] = 25
    ports = []
    for name, size in PORTS:
        ct = next(c for c in cities if c["name"] == name)
        ports.append([ct["row"], ct["col"], size])
    res = MILES / 69.0                                            # (degrees per tile, as if it were the Earth)
    side = {r["name"]: r["side"] for r in REALMS}
    meta = dict(
        wrap=False, sea_min=0, res=res, bounds=[0.0, COLS * res, 30.0, 30.0 + ROWS * res], start_date=START,
        names={str(k): nm for k, nm in enumerate(names, start=1)}, capitals=capitals, cities=cities, ports=ports,
        military={str(k): r["army"] for k, r in enumerate(REALMS, start=1)},
        governments={str(k): r["gov"] for k, r in enumerate(REALMS, start=1) if r["gov"] != "national"},
        traits={str(k): r["traits"] for k, r in enumerate(REALMS, start=1) if r["traits"]},
        nukes={}, wars=[[by_name[a], by_name[b]] for a, b in WARS],
        rivals=[[by_name[a], by_name[b]] for a, b in RIVALS],
        alliances={s: [by_name[n] for n in names if side[n] == s] for s in ("Free Peoples", "Shadow")},
        sites=sites, patient_zero=[pr, pc], outbreak=OUTBREAK,
        source="hand-drawn after the general map of Middle-earth (make_middleearth.py)")
    return H, Z, D, T, O, {}, meta


def preview(folder, H, T, O):
    import render
    terr = TR.COLORS[T].astype(np.uint8)
    pal = np.array([render.civ_color(k) for k in range(int(O.max()) + 1)], dtype=np.float32)
    own = pal[O] * (0.35 + 0.65 * np.clip(H / 150.0, 0, 1))[..., None]
    own[TR.is_water(T)] = (0, 0, 60)
    img = np.concatenate([terr, own.astype(np.uint8)], axis=1)
    Image.fromarray(img).resize((img.shape[1] * 2, img.shape[0] * 2), Image.NEAREST).save(
        os.path.join(folder, "preview.png"))


if __name__ == "__main__":
    out = os.path.join("maps", "middle_earth")
    H, Z, D, T, O, A, meta = build()
    mapio.save_map(out, H, Z, D, T, O, A)
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    preview(out, H, T, O)
    pops = np.bincount(O.ravel(), weights=H.ravel(), minlength=len(REALMS) + 1)
    print(f"{COLS} x {ROWS} tiles, {len(REALMS)} realms, {len(meta['cities'])} places, {int(H.sum())} people")
    for k, r in enumerate(REALMS, start=1):
        print(f"  {r['name']:24s} {r['side']:12s} {int(pops[k]):7d} people, {int((O == k).sum()):5d} tiles")
    print("saved", out)
