"""Generates maps/beleriand: Beleriand and the lands to the north, at the end of the Siege of Angband (First Age 455,
the winter of the Dagor Bragollach).

    python make_beleriand.py                     (writes maps/beleriand)
    python main.py maps/beleriand

Laid out on a political map of Beleriand (in its pixel coordinates, about 0.78 miles per pixel), with Tolkien's own
map of Beleriand for the rivers, hills, forests and fens; 3 miles per tile.  Drawn by drawmap.py: the ground first,
then the realms grow out from their towns over it, so their borders follow the rivers and ridges.

The realms of the time and who stood with whom - the Noldor were not one people:
  Morgoth          Angband, the Iron Prison under Thangorodrim: the strongest host in the world.
  Fingolfin's house (the High King's allegiance): Hithlum (Fingolfin), Dor-lomin (Fingon) with the House of Hador,
                   Nargothrond (Finrod), Tol Sirion (Orodreth), Dorthonion (Angrod and Aegnor) with the House of
                   Beor in Ladros.
  Thingol's Sindar Doriath behind Melian's Girdle, the Falas (Cirdan) and the haven of Brithombar, the Green-elves of
                   Ossiriand, the Haladin of Brethil.
  Feanor's sons    Himring (Maedhros), Maglor's Gap, Himlad (Celegorm and Curufin), Thargelion (Caranthir), East
                   Beleriand (Amrod and Amras).  Thingol will have nothing to do with them, nor they with him (RIVALS).
  the Dwarves      Belegost and Nogrod in the Blue Mountains.
  on their own     Gondolin (Turgon's hidden city: no one knows where it is), the Men of Estolad.
Angband is already at war with the realms of the Siege (Hithlum, Tol Sirion, Dorthonion, Himring).  The outbreak starts
in the forges of Thangorodrim: Morgoth's last weapon, and it turns on his own orc-hosts first.
"""
import os

MILES = 3.0                      # miles per tile
MILES_PER_PX = 0.777             # the reference map's scale (its 200-mile bar)
UNIT = MILES / MILES_PER_PX      # reference-map pixels per tile
WIDTH, HEIGHT = 1100, 1070       # reference-map pixels
START = "0455-12-21"             # midwinter: the Battle of Sudden Flame
AMP = 0.5                        # (the outlines below are already detailed: push them about less than Middle-earth's)
RIVER_WIDTH, FEN_WIDTH = 5, 16
DISTRICT_MILES = 25.0
MARGIN, SPILL = 3, 14.0          # (realms keep close to their drawn outlines: Ard-galen and Nevrast are no one's)
REAL_POPULATION = 3.5e6
SOURCE = "hand-drawn after a political map of Beleriand and Tolkien's map of Beleriand (make_beleriand.py)"

# ------------------------------------------------------------------------------------------------ geography
# x east, y south, in pixels of the reference map (1500 x 1104; the map itself is 36..1092 x 36..1066).
COAST = [(38, 38), (1090, 38), (1090, 1064), (472, 1064), (460, 1034), (436, 1024), (436, 1010), (458, 998),
         (470, 986), (476, 968), (494, 962), (500, 950), (542, 914), (550, 890), (566, 878), (566, 868), (578, 856),
         (578, 838), (554, 814), (548, 796), (530, 796), (524, 802), (496, 800), (490, 806), (466, 806), (452, 814),
         (430, 808), (392, 824), (386, 796), (400, 754), (380, 724), (380, 710), (362, 706), (340, 692), (326, 688),
         (310, 674), (292, 674), (290, 640), (268, 640), (244, 652), (226, 652), (226, 616), (218, 614), (206, 620),
         (200, 610), (208, 568), (202, 562), (190, 562), (206, 512), (188, 488), (178, 478), (166, 478), (166, 472),
         (196, 448), (200, 436), (218, 416), (230, 412), (236, 394), (254, 386), (262, 364), (242, 362), (226, 346),
         (202, 350), (188, 302), (164, 286), (148, 286), (152, 262), (140, 254), (140, 242), (104, 218), (92, 218),
         (56, 196), (62, 176), (76, 176), (82, 170), (80, 160), (52, 164), (38, 176), (38, 40)]
ISLANDS = [[(436, 890), (446, 890), (446, 896), (428, 922), (404, 944), (370, 952), (362, 944), (362, 934), (398, 902),
            (434, 892)]]                                                      # the Isle of Balar
WATER = {
    "Lake Mithrim": [(450, 330), (468, 322), (488, 325), (492, 336), (470, 343), (452, 341)],
    "Linaewen": [(262, 413), (285, 405), (318, 407), (316, 418), (288, 423), (265, 420)],
    "Lake Helevorn": [(963, 447), (983, 433), (1001, 427), (1004, 437), (986, 447), (970, 453)],
    "Ivrin": [(425, 405), (435, 402), (438, 412), (427, 415)],
}
COLD = [   # (shape, terrain, share): the Grinding Ice, the Regions of Everlasting Cold, the barren cold below them
    ([(38, 38), (240, 38), (200, 90), (150, 150), (110, 190), (70, 205), (38, 200)], 5, 1.0),
    ([(240, 38), (1092, 38), (1092, 128), (1040, 138), (980, 140), (900, 135), (850, 140), (800, 138), (760, 128),
      (700, 118), (640, 105), (580, 95), (520, 80), (460, 72), (400, 62), (340, 58), (290, 62), (250, 70)], 5, 1.0),
    ([(250, 70), (400, 62), (560, 90), (700, 118), (800, 138), (1092, 128), (1092, 178), (900, 172), (800, 178),
      (700, 152), (560, 128), (400, 100), (300, 112)], 10, 0.75),
]
OPEN_RIVERS = {                  # the great rivers, open water below their marshes
    "Lower Sirion": [(582, 558), (560, 578), (536, 600), (518, 630), (512, 668), (523, 708), (540, 745), (548, 780),
                     (546, 805)],
    "Lower Gelion": [(908, 615), (906, 640), (895, 690), (880, 740), (870, 790), (866, 840), (860, 875), (835, 905),
                     (800, 930), (765, 955), (730, 980), (690, 998), (640, 1012), (590, 1015), (545, 1012), (505, 1018),
                     (478, 1035)],
}
RIVERS = {                       # marshy river valleys: slow going, and borders like to follow them
    "Sirion": [(533, 292), (545, 318), (545, 345), (538, 372), (540, 400), (550, 430), (553, 465), (556, 500),
               (568, 535), (582, 558)],
    "Teiglin": [(462, 392), (478, 430), (493, 465), (515, 500), (545, 512), (556, 515)],
    "Narog": [(428, 412), (428, 450), (434, 490), (445, 530), (455, 570), (462, 605), (470, 640), (490, 670),
              (514, 690)],
    "Ginglith": [(365, 445), (378, 485), (400, 522), (430, 560), (452, 578)],
    "Esgalduin": [(640, 400), (640, 440), (645, 480), (640, 510), (612, 540), (588, 557)],
    "Aros": [(745, 385), (750, 420), (746, 455), (752, 490), (746, 530), (722, 558), (680, 568), (630, 566),
             (588, 558)],
    "Celon": [(832, 398), (815, 430), (790, 465), (770, 500), (755, 530), (742, 553)],
    "Mindeb": [(585, 408), (575, 440), (560, 465)],
    "Rivil": [(600, 350), (575, 330), (555, 305)],
    "Little Gelion": [(872, 412), (885, 450), (895, 490), (900, 520)],
    "Greater Gelion": [(962, 425), (930, 440), (908, 470), (900, 520)],
    "Gelion": [(900, 520), (906, 560), (908, 615)],
    "Ascar": [(1008, 575), (970, 592), (935, 605), (908, 615)],
    "Thalos": [(1000, 650), (960, 660), (920, 668), (906, 672)],
    "Legolin": [(995, 700), (950, 705), (910, 712), (895, 715)],
    "Brilthor": [(990, 745), (940, 748), (900, 752), (880, 755)],
    "Duilwen": [(985, 800), (935, 805), (895, 808), (870, 810)],
    "Adurant": [(990, 860), (940, 880), (900, 880), (863, 875)],
    "Brithon": [(262, 505), (248, 545), (232, 580), (212, 600)],
    "Nenning": [(335, 495), (322, 560), (310, 610), (300, 648)],
    "Hithlum streams": [(420, 220), (440, 270), (462, 322)],
    "Hithlum streams 2": [(505, 240), (482, 290), (472, 322)],
}
MOUNTAINS = {                    # ridge lines and widths (pixels); "hills": highlands only
    "Ered Engrin": ([(165, 62), (230, 58), (300, 56), (380, 66), (450, 82), (520, 100), (580, 118), (640, 130),
                     (700, 138), (760, 150), (820, 160), (880, 160), (950, 152), (1020, 148), (1092, 140)], 34),
    "Ered Lomin": ([(165, 62), (195, 115), (225, 170), (255, 225), (280, 270), (300, 310), (315, 350), (318, 388),
                    (305, 420)], 26),
    "Ered Wethrin": ([(345, 95), (400, 150), (445, 190), (490, 225), (525, 255), (540, 285), (535, 320), (510, 355),
                      (475, 385), (435, 402), (395, 415), (355, 425), (310, 433), (265, 443), (225, 455), (195, 468)],
                     26),
    "Mountains of Mithrim": ([(335, 332), (385, 326), (435, 342), (478, 364)], 16),
    "Echoriath": ([(592, 383), (588, 398), (577, 409), (562, 413), (547, 409), (536, 398), (532, 383), (536, 368),
                   (547, 357), (562, 353), (577, 357), (588, 368), (592, 383)], 13),
    "Dorthonion scarp": ([(585, 342), (640, 337), (700, 334), (760, 338)], 12),
    "Dorthonion heights": ([(570, 368), (640, 365), (720, 360)], 26, "hills"),
    "Ered Gorgoroth": ([(585, 396), (630, 390), (680, 387), (722, 392)], 16),
    "Ladros heights": ([(695, 385), (730, 368), (765, 350), (795, 336)], 14),
    "Andram": ([(520, 598), (560, 608), (610, 620), (660, 636), (700, 650), (740, 664), (780, 672), (805, 676)], 14),
    "Taur-en-Faroth": ([(395, 588), (430, 598), (468, 610)], 18, "hills"),
    "March of Maedhros": ([(775, 350), (810, 372), (850, 400), (900, 398), (950, 388), (985, 380)], 18, "hills"),
    "Ered Luin": ([(1088, 228), (1060, 270), (1030, 310), (1012, 350), (1002, 400), (998, 450), (1000, 500),
                   (1010, 550), (1020, 600), (1020, 650), (1010, 700), (1005, 750), (1010, 800), (1015, 850),
                   (1022, 900), (1032, 950), (1045, 1000), (1060, 1062)], 34),
    "Falas hills": ([(248, 498), (268, 512), (292, 520)], 14, "hills"),
    "Eglamar hills": ([(252, 600), (282, 604)], 12, "hills"),
}
PEAKS = {"Thangorodrim": (660, 232, 13), "Mount Taras": (195, 468, 7), "Himring": (850, 405, 6),
         "Amon Ereb": (842, 695, 6), "Amon Rudh": (532, 522, 6), "Mount Rerir": (965, 422, 7),
         "Mount Dolmed": (1018, 560, 8)}
HILLS = {                        # (x, y, radius) or polygons: highlands
    "Lammoth": (250, 315, 22), "Nevrast hills": (262, 440, 14), "Balar hills": (395, 930, 8),
    "Eriador foothills": [(1060, 260), (1092, 240), (1092, 1064), (1065, 1064), (1045, 900), (1040, 600)],
    "Hithlum uplands": (360, 230, 20),
}
FORESTS = {                      # polygons, or (x, y, radius); with the share of the ground that is wooded
    "Taur-im-Duinath": ([(600, 700), (640, 690), (700, 682), (760, 690), (800, 700), (830, 730), (845, 780),
                         (840, 840), (820, 880), (790, 920), (750, 950), (700, 975), (640, 985), (590, 975),
                         (555, 950), (548, 900), (565, 840), (580, 780), (590, 730)], 0.92),
    "Southern woods": ([(760, 1000), (820, 950), (880, 925), (940, 905), (990, 895), (1005, 950), (1000, 1010),
                        (980, 1060), (900, 1064), (800, 1064), (760, 1045)], 0.9),
    "Neldoreth and Region": ([(555, 450), (600, 440), (660, 442), (720, 440), (745, 455), (750, 500), (740, 545),
                              (715, 560), (660, 566), (600, 565), (570, 545), (555, 500)], 1.0),
    "Nan Elmoth": ((785, 490, 16), 1.0),
    "Brethil": ([(500, 450), (525, 440), (545, 445), (555, 470), (550, 500), (530, 510), (505, 500), (497, 475)], 1.0),
    "Woods of Nuath": ([(300, 455), (330, 445), (370, 445), (400, 455), (400, 475), (370, 490), (330, 485),
                        (305, 475)], 1.0),
    "Nimbrethil": ((455, 750, 18), 1.0), "Birchwoods": ((430, 770, 10), 0.9), "Nan-Tathren": ((522, 705, 14), 0.7),
    "Dorthonion pines": ([(575, 340), (700, 334), (760, 340), (740, 382), (690, 395), (600, 396), (572, 372)], 0.6),
}
WOODLAND = {                     # scattered woods and copses: area, share of the open ground wooded
    "Ossiriand": ([(870, 620), (990, 590), (1000, 860), (870, 870)], 0.4),
    "Blue Mountain eaves": ([(950, 560), (1060, 560), (1080, 1060), (960, 1060)], 0.3),
    "West Beleriand": ([(330, 480), (520, 440), (560, 620), (520, 800), (390, 800), (340, 640)], 0.14),
    "East Beleriand": ([(760, 560), (900, 560), (900, 700), (760, 700)], 0.12),
    "Hithlum": ([(300, 190), (540, 190), (540, 420), (300, 420)], 0.08),
    "Falas": ([(190, 490), (350, 490), (350, 690), (190, 660)], 0.12),
}
DOWNS = 0.08
MARSHES = {                      # (x, y, radius) or polygons
    "Fen of Serech": (552, 302, 10), "Aelin-uial": (577, 573, 15), "Mouths of Sirion": (548, 795, 13),
    "Marshes of Nevrast": (290, 415, 24), "Ivrin": (430, 410, 7), "Nan-Tathren meads": (515, 700, 10),
    "Gelion fens": (865, 880, 10), "Lammoth fens": (225, 345, 8),
}
DESERTS = {                      # polygons and the share of them that is barren
    "Nan Dungortheb": ([(590, 400), (700, 398), (730, 410), (700, 428), (620, 430), (585, 418)], 0.85),
    "Angband": ([(585, 140), (700, 132), (785, 148), (755, 205), (720, 250), (680, 262), (640, 258), (610, 235),
                 (592, 195)], 0.8),
}

# ------------------------------------------------------------------------------------------------ the realms
MORGOTH, FINGOLFIN, THINGOL, FEANOR, DWARVES = ("Morgoth", "Fingolfin's house", "Thingol's Sindar", "Feanor's sons",
                                                "the Dwarves")
REALMS = [
    dict(name="Angband", side=MORGOTH, land=[(585, 140), (700, 132), (785, 148), (755, 205), (720, 250), (680, 262),
         (640, 258), (610, 235), (592, 195)], rural=45, floor=0.6, army=1.0, gov="national",
         traits={"aggression": 1.7, "caution": 0.7}, margin=2, spill=8.0),
    dict(name="Hithlum (Fingolfin)", side=FINGOLFIN, land=[(300, 200), (340, 193), (400, 198), (445, 205), (485, 228),
         (520, 255), (540, 285), (532, 330), (510, 352), (480, 350), (440, 336), (400, 326), (360, 326), (330, 336),
         (305, 330), (295, 280)], rural=35, floor=0.4, army=0.9, gov="national", traits={"caution": 1.1}),
    dict(name="Dor-lomin (Fingon)", side=FINGOLFIN, land=[(325, 338), (360, 330), (400, 330), (415, 340), (410, 375),
         (395, 412), (365, 420), (335, 415), (322, 380)], rural=35, floor=0.4, army=0.8, gov="national",
         traits={"aggression": 1.1}),
    dict(name="House of Hador", side=FINGOLFIN, land=[(415, 340), (440, 345), (465, 362), (480, 388), (450, 402),
         (415, 410), (400, 385)], rural=45, floor=0.4, army=0.55, gov="national", traits={"aggression": 1.2},
         margin=3),
    dict(name="Tol Sirion (Orodreth)", side=FINGOLFIN, land=[(518, 300), (560, 298), (578, 320), (572, 345),
         (548, 360), (525, 348), (514, 322)], rural=20, floor=0.5, army=0.6, gov="national", traits={}, margin=2),
    dict(name="Dorthonion (Angrod and Aegnor)", side=FINGOLFIN, land=[(575, 335), (640, 332), (700, 330), (745, 332),
         (760, 345), (740, 380), (700, 396), (640, 400), (590, 398), (570, 375)], rural=25, floor=0.5, army=0.7,
         gov="national", traits={"aggression": 1.1}),
    dict(name="House of Beor", side=FINGOLFIN, land=[(705, 336), (760, 328), (798, 334), (792, 362), (762, 378),
         (722, 378), (705, 360)], rural=35, floor=0.5, army=0.4, gov="tribal", traits={}, margin=3),
    dict(name="Nargothrond (Finrod)", side=FINGOLFIN, land=[(330, 490), (360, 470), (420, 440), (470, 420), (500, 440),
         (505, 480), (520, 520), (545, 560), (540, 600), (518, 630), (512, 670), (525, 710), (540, 745), (548, 790),
         (530, 798), (490, 805), (450, 812), (420, 808), (395, 820), (388, 795), (398, 755), (380, 720), (355, 700),
         (350, 680), (345, 650), (330, 600), (325, 550)], rural=30, floor=0.4, army=0.8, gov="national",
         traits={"caution": 1.3}),
    dict(name="Gondolin", side=None, land=[(540, 362), (562, 356), (585, 364), (593, 385), (585, 405), (562, 412),
         (540, 404), (533, 383)], rural=60, floor=0.8, army=0.9, gov="national", traits={"caution": 2.0, "aggression": 0.3},
         margin=1, spill=4.0),
    dict(name="Doriath (Thingol)", side=THINGOL, land=[(550, 440), (600, 436), (660, 438), (720, 436), (745, 452),
         (760, 500), (742, 548), (715, 565), (660, 570), (600, 568), (568, 548), (552, 500)], rural=25, floor=0.6,
         army=0.85, gov="national", traits={"caution": 1.8}, margin=2, spill=8.0),
    dict(name="Falas (Cirdan)", side=THINGOL, land=[(205, 505), (245, 490), (290, 495), (325, 505), (330, 560),
         (330, 610), (345, 650), (350, 690), (320, 690), (290, 672), (270, 640), (244, 652), (226, 652), (226, 616),
         (206, 620), (200, 610), (208, 568), (206, 512)],
         extra=[[(436, 890), (446, 890), (428, 922), (404, 944), (370, 952), (362, 934), (398, 902)]],
         rural=30, floor=0.4, army=0.6, gov="national", traits={"caution": 1.2}),
    dict(name="Brithombar", side=THINGOL, rural=30, floor=0.4, army=0.45, gov="national", traits={},
         liege="Falas (Cirdan)", reach=12),
    dict(name="Brethil (Haladin)", side=THINGOL, land=[(500, 450), (525, 440), (545, 445), (555, 470), (550, 500),
         (530, 510), (505, 500), (497, 475)], rural=30, floor=0.6, army=0.4, gov="tribal", traits={"caution": 1.2},
         margin=3),
    dict(name="Ossiriand (Green-elves)", side=THINGOL, land=[(870, 620), (905, 610), (950, 600), (985, 590),
         (990, 650), (985, 700), (1000, 750), (995, 800), (985, 840), (960, 860), (920, 868), (880, 870), (865, 840),
         (868, 780), (880, 720), (895, 680), (900, 640)], rural=12, floor=0.8, army=0.4, gov="tribal",
         traits={"caution": 1.5}),
    dict(name="Himring (Maedhros)", side=FEANOR, land=[(790, 335), (850, 333), (880, 340), (890, 370), (900, 400),
         (905, 435), (880, 450), (850, 445), (830, 420), (805, 395), (795, 365)], rural=25, floor=0.4, army=0.9,
         gov="national", traits={"aggression": 1.2}),
    dict(name="Maglor's Gap (Maglor)", side=FEANOR, land=[(880, 340), (950, 338), (1000, 345), (1010, 370),
         (1000, 395), (960, 415), (925, 430), (905, 435), (900, 400), (890, 370)], rural=20, floor=0.4, army=0.7,
         gov="national", traits={}),
    dict(name="Himlad (Celegorm and Curufin)", side=FEANOR, land=[(742, 385), (775, 378), (800, 385), (830, 410),
         (838, 440), (815, 455), (790, 470), (765, 485), (748, 470), (745, 430)], rural=25, floor=0.4, army=0.75,
         gov="national", traits={"aggression": 1.4, "caution": 0.8}),
    dict(name="Thargelion (Caranthir)", side=FEANOR, land=[(893, 445), (930, 430), (965, 425), (1000, 440),
         (1000, 500), (1000, 540), (985, 570), (950, 600), (920, 620), (905, 600), (905, 550), (898, 500)],
         rural=25, floor=0.4, army=0.65, gov="national", traits={"aggression": 1.2}),
    dict(name="East Beleriand (Amrod and Amras)", side=FEANOR, land=[(795, 470), (830, 450), (870, 455), (893, 480),
         (895, 520), (890, 560), (905, 620), (880, 680), (845, 705), (805, 690), (790, 640), (840, 580), (820, 535),
         (790, 520), (775, 495)], rural=20, floor=0.4, army=0.55, gov="national", traits={}),
    dict(name="Estolad", side=None, land=[(760, 520), (800, 510), (830, 540), (820, 580), (780, 590), (760, 560)],
         rural=40, floor=0.4, army=0.2, gov="tribal", traits={"caution": 0.8}, margin=2, spill=10.0),
    dict(name="Belegost", side=DWARVES, land=[(990, 515), (1030, 508), (1062, 525), (1062, 580), (1030, 585),
         (998, 575)], rural=30, floor=0.5, army=0.8, gov="national", traits={"caution": 1.3}, margin=2),
    dict(name="Nogrod", side=DWARVES, land=[(1000, 588), (1035, 588), (1062, 600), (1062, 660), (1035, 700),
         (1005, 690), (995, 640)], rural=30, floor=0.5, army=0.75, gov="national", traits={"caution": 1.1},
         margin=2),
]
# towns and fortresses: name, realm, x, y, people at the centre, radius (tiles), garrison level (0 = none)
PLACES = [
    ("Angband", "Angband", 660, 255, 255, 2, 7), ("Thangorodrim forges", "Angband", 690, 200, 200, 1, 0),
    ("Orc-hold of the Iron Mountains", "Angband", 610, 170, 160, 0, 0),
    ("Barad Eithel", "Hithlum (Fingolfin)", 535, 293, 220, 1, 7), ("Mithrim", "Hithlum (Fingolfin)", 470, 348, 160, 1, 0),
    ("Hithlum", "Hithlum (Fingolfin)", 400, 262, 130, 0, 0), ("Eithel Ivrin", "Hithlum (Fingolfin)", 380, 300, 80, 0, 0),
    ("Dor-lomin", "Dor-lomin (Fingon)", 368, 375, 170, 1, 6), ("Lammoth", "Dor-lomin (Fingon)", 340, 350, 60, 0, 0),
    ("Hador's Hall", "House of Hador", 440, 378, 160, 0, 0),
    ("Tol Sirion", "Tol Sirion (Orodreth)", 545, 335, 180, 0, 7),
    ("Dorthonion", "Dorthonion (Angrod and Aegnor)", 650, 365, 140, 0, 6),
    ("Aegnor's Hold", "Dorthonion (Angrod and Aegnor)", 678, 356, 110, 0, 0),
    ("Ladros", "House of Beor", 752, 350, 140, 0, 0),
    ("Gondolin", "Gondolin", 562, 383, 255, 1, 7),
    ("Ephel Brandir", "Brethil (Haladin)", 525, 475, 140, 0, 0), ("Brethil", "Brethil (Haladin)", 510, 495, 90, 0, 0),
    ("Menegroth", "Doriath (Thingol)", 642, 505, 230, 1, 7), ("Neldoreth", "Doriath (Thingol)", 610, 470, 90, 0, 0),
    ("Region", "Doriath (Thingol)", 700, 525, 90, 0, 0), ("Iant Iaur", "Doriath (Thingol)", 700, 448, 60, 0, 0),
    ("Nargothrond", "Nargothrond (Finrod)", 455, 590, 240, 1, 7), ("Tumhalad", "Nargothrond (Finrod)", 432, 560, 90, 0, 0),
    ("Talath Dirnen", "Nargothrond (Finrod)", 475, 515, 70, 0, 0), ("Arvernien", "Nargothrond (Finrod)", 440, 785, 100, 0, 0),
    ("Nan-Tathren", "Nargothrond (Finrod)", 518, 700, 60, 0, 0), ("Ivrin", "Nargothrond (Finrod)", 430, 425, 50, 0, 0),
    ("Eglarest", "Falas (Cirdan)", 300, 650, 210, 1, 6), ("Barad Nimras", "Falas (Cirdan)", 232, 648, 80, 0, 6),
    ("Balar", "Falas (Cirdan)", 400, 920, 120, 0, 0), ("Eglamar", "Falas (Cirdan)", 270, 575, 70, 0, 0),
    ("Brithombar", "Brithombar", 213, 600, 200, 1, 6),
    ("Ossiriand", "Ossiriand (Green-elves)", 935, 760, 70, 0, 0),
    ("Tol Galen", "Ossiriand (Green-elves)", 925, 870, 50, 0, 0),
    ("Sarn Athrad", "Ossiriand (Green-elves)", 915, 625, 50, 0, 0),
    ("Himring", "Himring (Maedhros)", 850, 405, 210, 1, 7), ("Lothlann", "Himring (Maedhros)", 880, 360, 90, 0, 0),
    ("Maglor's Gap", "Maglor's Gap (Maglor)", 960, 385, 160, 1, 7),
    ("Aglon", "Himlad (Celegorm and Curufin)", 770, 388, 170, 0, 7),
    ("Himlad", "Himlad (Celegorm and Curufin)", 795, 432, 120, 0, 0),
    ("Helevorn", "Thargelion (Caranthir)", 978, 458, 190, 1, 6), ("Thargelion", "Thargelion (Caranthir)", 945, 530, 110, 0, 0),
    ("Amrod's Hall", "East Beleriand (Amrod and Amras)", 845, 500, 130, 0, 0),
    ("Amon Ereb", "East Beleriand (Amrod and Amras)", 842, 690, 90, 0, 6),
    ("Estolad", "Estolad", 790, 560, 140, 0, 0),
    ("Belegost", "Belegost", 1025, 545, 230, 1, 7), ("Nogrod", "Nogrod", 1042, 625, 230, 1, 7),
    ("Vinyamar", None, 198, 462, 40, 0, 0),
]
PORTS = [("Eglarest", 6), ("Brithombar", 6), ("Balar", 5), ("Arvernien", 2), ("Vinyamar", 1)]
VIRULENCE_SCALE = 1.25        # (the zombies bite harder here than --virulence alone: Beleriand is a hard map)
SETTLE_SCALE = 2.0            # (settlers' colonies keep further apart on this small map: settlers.py)
WARS = [("Angband", "Hithlum (Fingolfin)"), ("Angband", "Dorthonion (Angrod and Aegnor)"),
        ("Angband", "Himring (Maedhros)"), ("Angband", "Tol Sirion (Orodreth)")]
RIVALS = [("Doriath (Thingol)", "Himlad (Celegorm and Curufin)"), ("Doriath (Thingol)", "Himring (Maedhros)"),
          ("Doriath (Thingol)", "Thargelion (Caranthir)"), ("Doriath (Thingol)", "Nogrod"),
          ("Angband", "Nargothrond (Finrod)"), ("Angband", "Doriath (Thingol)"), ("Angband", "Gondolin"),
          ("Angband", "Maglor's Gap (Maglor)"), ("Angband", "Dor-lomin (Fingon)"), ("Angband", "Falas (Cirdan)"),
          ("Angband", "Himlad (Celegorm and Curufin)"), ("Angband", "House of Beor")]
OUTBREAK = "Thangorodrim forges"
WILD_RURAL = 4


def post(cv, T, O, D, H, by_name, sites):
    """Melian's Girdle: a standing line of defence (level 6) all round Doriath, held from Menegroth - it stands as long
    as Menegroth does."""
    import numpy as np
    k = by_name["Doriath (Thingol)"]
    mine = O == k
    p = np.pad(mine, 1, constant_values=False)
    inner = np.ones(mine.shape, dtype=bool)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            inner &= p[1 + dr:p.shape[0] - 1 + dr, 1 + dc:p.shape[1] - 1 + dc]
    ring = mine & ~inner & (H > 10)
    home = next(s for s in sites if s["civ"] == k)
    rr, cc = np.nonzero(ring)
    sites.append(dict(civ=k, row=home["row"], col=home["col"], level=6,
                      tiles=[[int(a), int(b)] for a, b in zip(rr, cc)]))


if __name__ == "__main__":
    import sys
    import drawmap
    drawmap.make(sys.modules[__name__], os.path.join("maps", "beleriand"))
