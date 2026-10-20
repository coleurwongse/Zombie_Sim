"""Generates maps/discworld: the Disc, in the year the Borogravian war comes to a head (the time of Monstrous Regiment).

    python make_discworld.py                     (writes maps/discworld)
    python main.py maps/discworld

Laid out on a picture of the whole Disc (data/discworld_reference.png, 1024 x 1024; the Disc itself is a circle about
745 pixels across - 10,000 miles - so ~13 miles per pixel), 2 pixels a tile.  The land is traced from the picture
(its colours: sea is blue, land is ochre, and round the Hub the snow is white), everything else is drawn from the
lists below: the Ramtops running rimward from Cori Celesti at the Hub, the Hublands' ice, the mountains of Überwald, the
Great Nef, the jungles of Howondaland, the red heart of Fourecks, rivers and swamps.  Outside the Rim there's nothing.
Drawn by drawmap.py: the realms grow out from their towns over the ground, so their borders follow rivers and ridges.

The realms of the time, and who stands with whom:
  the Sto Plains      Ankh-Morpork (the Patrician's city - by far the biggest on the Disc), Sto Lat, Sto Helit, Sto
                      Kerrig, Pseudopolis, Quirm: cabbage country, the old Morporkian sphere - they stand together.
  the Ramtops         Lancre (a small kingdom with a very capable Queen and some witches), Llamedos, Chirm, the
                      dwarf-mines of Copperhead; the Hubland barbarian clans in the ice beyond.
  the Dwarves         Copperhead and Schmaltzberg (the Low King's seat) stand together.
  Überwald            not one country: Bonk, Escrow (the vampire counts), Lipwig, Bad Schüschein - every lord for
                      himself; Borogravia and Zlobenia at war on the Kneck river (WARS).
  the Circle Sea      Ephebe (a democracy, of sorts), Tsort, Djelibeybi (the Old Kingdom: a river valley of pyramids),
                      Omnia (the Church's theocracy, the Citadel at Kom), Klatch (the Seriph's empire, Al Khali) with
                      Hersheba; the Ephebians and Tsorteans have hated each other since the Tsortean Wars, Omnia
                      wants Ephebe back, Klatch and Ankh-Morpork nearly went to war over Leshp (RIVALS).
  Howondaland         clans of the savannah; the Tezuman Empire in the turnwise jungles.
  the Counterweight   the Agatean Empire - the Emperor at Hunghung, behind the Great Wall, and the Five Families
  Continent           (Hong, Sung, Tang, Fang, McSweeney) who hold its provinces and scheme against each other;
                      Bhangbhangduc on the eastern peninsula.
  the Rim             Krull (the island on the edge that looks over it), Fourecks (XXXX, Bugarup), the Brown Islands.
The Red Army of the Agatean Empire, the Seriph's army, the Omnian Divine Legion, the Borogravian army, the Low King's
dwarfs and the Watch of Ankh-Morpork are the strongest forces.  The outbreak starts in Escrow, in Überwald: the
undead were always going to come out of Überwald.
"""
import os

import numpy as np

MILES = 26.0                     # miles per tile
UNIT = 2.0                       # reference pixels per tile
X0, Y0 = 130, 75                 # (the part of the picture the map covers: the Disc and a little sea round it)
WIDTH, HEIGHT = 772, 772
START = "2005-07-01"
AMP = 1.3                        # (how far outlines are pushed about by noise, x drawmap's tiles)
RIVER_WIDTH, FEN_WIDTH = 2, 6
DISTRICT_MILES = 140.0
MARGIN, SPILL = 3, 12.0
REAL_POPULATION = 1.8e8          # (what the panel shows: the people of the Disc)
SOURCE = "traced from the 'Maffa Discworld' map (make_discworld.py)"
HUB = (512, 425)                 # Cori Celesti
RIM_CENTRE, RIM_RADIUS = (515, 458), 368

# ------------------------------------------------------------------------------------------------ geography
# in pixels of the reference picture (x turnwise-ish, y down); shifted onto the map at the end of the module
SNOW_ZONE = [(405, 335), (470, 335), (560, 335), (640, 360), (700, 395), (700, 450), (405, 450)]
NOT_LAND = [(495, 175, 600, 275), (295, 145, 360, 205), (785, 300, 875, 372), (755, 252, 785, 285),
            (555, 330, 585, 355), (630, 365, 662, 395), (305, 475, 335, 510), (318, 612, 345, 650),
            (252, 658, 275, 688), (437, 607, 465, 645)]  # (the sun, a moth, a rider, ships and a sea-horse)
ISLANDS = []
WATER = {
    "Lake by the Hub": [(431, 419), (438, 418), (441, 432), (440, 446), (433, 447), (430, 434)],
    "Turnwise lake": [(693, 556), (702, 553), (707, 570), (707, 600), (701, 616), (693, 610), (691, 585)],
}
COLD = [   # (the Hub's cold: paint_ground)
    ([(225, 152), (300, 148), (360, 160), (440, 140), (446, 190), (402, 186), (360, 204), (318, 196), (282, 214),
      (250, 230), (230, 205)], 10, 0.5),                                              # the Counterweight's far north
]
OPEN_RIVERS = {}
RIVERS = {
    "Ankh": [(486, 500), (488, 530), (492, 560), (500, 585), (509, 598)],
    "Smarl": [(445, 520), (458, 548), (470, 572), (485, 588)],
    "Kneck": [(560, 520), (575, 538), (588, 556), (598, 580)],
    "Vieux": [(650, 480), (675, 500), (700, 512), (727, 522)],
    "Djel": [(470, 740), (468, 715), (466, 690), (467, 664), (468, 648)],
    "Tsort river": [(515, 715), (510, 690), (505, 668), (503, 650)],
    "Howondaland river": [(600, 760), (590, 720), (575, 690), (560, 665)],
    "Agatean river": [(270, 270), (300, 285), (330, 300), (365, 318)],
    "Jade river": [(400, 230), (390, 260), (370, 290), (350, 310)],
}
MOUNTAINS = {                    # ridge lines (picture pixels) and widths
    "Ramtops": ([(512, 428), (509, 440), (503, 452), (506, 466), (500, 480), (502, 494), (496, 508), (499, 522),
                 (493, 536), (495, 550)], 12),
    "Ramtops (Lancre spur)": ([(505, 446), (494, 452), (484, 460), (473, 463), (462, 472), (452, 470)], 6),
    "Ramtops (rimward spur)": ([(499, 520), (512, 528), (522, 540), (528, 556)], 6),
    "Ramtops (Copperhead)": ([(502, 494), (490, 504), (478, 507), (470, 517)], 5),
    "Überwald mountains": ([(514, 434), (526, 446), (538, 450), (548, 464), (562, 470), (574, 484), (590, 488),
                            (604, 500), (620, 504), (630, 516)], 9),
    "Überwald spur": ([(560, 470), (568, 455), (582, 446), (596, 440)], 5),
    "Überwald ranges": ([(652, 422), (668, 432), (684, 428), (700, 438), (716, 436), (732, 446), (748, 444)], 6),
    "Morpork hills": ([(412, 538), (424, 548), (436, 556), (444, 570), (456, 578)], 9, "hills"),
    "Carrack Mountains": ([(606, 540), (614, 552), (626, 560), (632, 574), (642, 584)], 6),
    "Klatchian spine": ([(554, 616), (560, 632), (558, 648), (566, 664), (565, 682), (570, 698), (564, 716),
                         (566, 734), (558, 752), (552, 772)], 8),
    "Nef hills": ([(412, 690), (424, 698), (436, 700), (448, 712), (462, 718)], 7, "hills"),
    "Howondaland highlands": ([(468, 760), (482, 772), (498, 774), (512, 786), (530, 790)], 8, "hills"),
    "Counterweight range": ([(272, 338), (282, 326), (290, 314), (302, 306), (312, 294), (326, 284), (334, 270),
                             (348, 262), (364, 252)], 8),
    "Counterweight south": ([(298, 344), (306, 354), (308, 366), (318, 378)], 5),
    "Counterweight north": ([(300, 200), (318, 210), (334, 206), (350, 214)], 5, "hills"),
    "Fourecks ranges": ([(688, 158), (696, 172), (702, 188), (712, 200), (718, 216)], 5, "hills"),
}
PEAKS = {"Cori Celesti": (512, 425, 5), "Copperhead": (494, 500, 3), "Dunmanifestin heights": (510, 440, 3)}
HILLS = {
    "Lancre": (478, 476, 10), "Llamedos": (428, 462, 12), "Schmaltzberg": (590, 505, 10),
    "Bonk heights": (630, 455, 10), "Krull": (590, 148, 6), "Ephebe hills": (420, 660, 9),
}
FORESTS = {                      # polygons, or (x, y, radius); with the share of the ground that is wooded
    "Überwald forests": ([(595, 420), (650, 412), (720, 405), (780, 415), (800, 450), (770, 480), (720, 470),
                          (680, 470), (640, 480), (610, 470)], 0.5),
    "Skund": ([(785, 520), (825, 500), (835, 540), (815, 600), (795, 640), (780, 620)], 0.6),
    "Lancre woods": ((468, 470, 10), 0.6),
    "Agatean forests": ([(240, 300), (280, 270), (300, 300), (270, 340), (240, 345)], 0.4),
    "Krull woods": ((598, 160, 7), 0.5),
}
RAINFOREST = {                   # the turnwise jungles of Howondaland and the Tezumen
    "Tezuman jungle": ([(605, 612), (632, 604), (660, 610), (690, 602), (720, 616), (748, 630), (760, 652),
                        (742, 672), (744, 690), (712, 696), (682, 702), (650, 690), (628, 694), (612, 668),
                        (616, 640)], 0.8),
    "Howondaland jungle": ([(560, 762), (582, 748), (604, 752), (630, 764), (618, 786), (600, 800), (572, 806),
                            (556, 790)], 0.75),
}
WOODLAND = {
    "Sto Plains": ([(380, 490), (480, 480), (500, 560), (470, 600), (380, 590)], 0.1),
    "Überwald": ([(560, 430), (800, 400), (800, 540), (560, 540)], 0.25),
    "Genua": ([(650, 480), (760, 480), (760, 600), (650, 600)], 0.2),
    "Counterweight": ([(225, 150), (500, 150), (500, 380), (225, 380)], 0.15),
    "Howondaland": ([(400, 740), (620, 740), (620, 830), (400, 830)], 0.15),
}
DOWNS = 0.07
MARSHES = {
    "Genua swamps": [(705, 525), (725, 515), (740, 530), (735, 560), (715, 568), (700, 550)],
    "Ankh delta": (507, 600, 5), "Vieux bayous": (690, 505, 8), "Kneck marshes": (588, 560, 5),
    "Djel delta": (467, 650, 4), "Bhangbhangduc fens": (480, 345, 8),
}
DESERTS = {
    "Great Nef": ([(462, 722), (486, 714), (510, 718), (532, 712), (552, 726), (548, 744), (558, 762),
                   (534, 774), (520, 786), (494, 778), (474, 782), (458, 764), (466, 744)], 0.8),
    "Klatchian desert": ([(420, 676), (444, 670), (470, 680), (496, 684), (520, 694), (538, 714), (512, 718),
                          (480, 712), (452, 724), (424, 714)], 0.55),
    "Fourecks": ([(672, 172), (700, 162), (730, 170), (744, 192), (732, 222), (706, 236), (684, 224), (668, 198)],
                 0.75),                                 # (the red centre: the coasts are farmed)
    "Hersheba": ([(582, 682), (604, 674), (628, 680), (640, 702), (630, 724), (604, 734)], 0.45),
}

# ------------------------------------------------------------------------------------------------ the realms
STO, DWARVES, AGATEA, KLATCH = "the Sto Plains", "the Dwarves", "the Agatean Empire", "the Klatchian Empire"
REALMS = [
    # the Sto Plains and the Ramtops
    dict(name="Ankh-Morpork", side=STO, land=[(488, 562), (528, 560), (545, 585), (538, 610), (500, 612),
         (484, 592)], rural=81, floor=0.5, army=0.6, gov="national", traits={"caution": 1.1}),
    dict(name="Sto Lat", side=STO, land=[(450, 532), (488, 528), (492, 562), (484, 590), (456, 588), (444, 560)],
         rural=68, floor=0.5, army=0.45, gov="national", traits={}),
    dict(name="Sto Helit", side=STO, land=[(398, 545), (446, 538), (454, 585), (430, 602), (400, 592)], rural=61,
         floor=0.5, army=0.35, gov="national", traits={"caution": 1.2}),
    dict(name="Sto Kerrig", side=STO, land=[(418, 495), (470, 490), (482, 528), (450, 535), (418, 535)], rural=61,
         floor=0.5, army=0.3, gov="national", traits={}),
    dict(name="Pseudopolis", side=STO, land=[(530, 552), (578, 552), (585, 588), (562, 610), (542, 605)], rural=61,
         floor=0.5, army=0.4, gov="democracy", traits={}),
    dict(name="Quirm", side=STO, land=[(358, 518), (400, 520), (410, 560), (396, 596), (372, 590), (355, 560)],
         rural=54, floor=0.5, army=0.3, gov="national", traits={"caution": 1.2}),
    dict(name="Chirm", side=None, land=[(358, 448), (410, 450), (416, 500), (382, 515), (355, 500)], rural=40,
         floor=0.4, army=0.3, gov="national", traits={}),
    dict(name="Llamedos", side=None, land=[(402, 430), (450, 430), (456, 480), (420, 492), (405, 470)], rural=34,
         floor=0.5, army=0.25, gov="tribal", traits={"caution": 1.3}),
    dict(name="Lancre", side=None, land=[(455, 455), (490, 450), (495, 488), (472, 500), (455, 485)], rural=34,
         floor=0.5, army=0.4, gov="national", traits={"caution": 1.4}, margin=2),
    dict(name="Copperhead", side=DWARVES, land=[(484, 486), (506, 486), (510, 515), (488, 520)], rural=34,
         floor=0.6, army=0.75, gov="national", traits={"caution": 1.3}, margin=2, spill=6.0),
    dict(name="Hubland Clans", side=None, land=[(420, 352), (600, 355), (690, 402), (690, 432), (620, 428),
         (560, 418), (520, 412), (470, 420), (430, 432), (415, 400)], rural=14, floor=0.8, army=0.65, gov="tribal",
         traits={"aggression": 1.7, "caution": 0.6}),
    # Überwald and its borderlands
    dict(name="Schmaltzberg", side=DWARVES, land=[(570, 480), (625, 480), (625, 530), (590, 540), (570, 520)],
         rural=40, floor=0.6, army=0.85, gov="national", traits={"caution": 1.3}),
    dict(name="Bonk", side=None, land=[(590, 430), (660, 425), (660, 470), (625, 478), (590, 470)], rural=40,
         floor=0.5, army=0.5, gov="warlord", traits={"aggression": 1.2}),
    dict(name="Escrow", side=None, land=[(660, 410), (730, 405), (735, 450), (690, 460), (660, 450)], rural=45,
         floor=0.5, army=0.5, gov="warlord", traits={"aggression": 1.3}),
    dict(name="Lipwig", side=None, land=[(722, 420), (792, 410), (802, 462), (762, 482), (732, 466)], rural=27,
         floor=0.5, army=0.4, gov="national", traits={}),
    dict(name="Bad Schüschein", side=None, land=[(630, 470), (700, 460), (702, 510), (660, 520), (630, 510)],
         rural=30, floor=0.5, army=0.4, gov="warlord", traits={}),
    dict(name="Borogravia", side=None, land=[(530, 508), (580, 505), (590, 545), (572, 562), (540, 556)], rural=40,
         floor=0.5, army=0.85, gov="junta", traits={"aggression": 1.4, "caution": 0.8}),
    dict(name="Zlobenia", side=None, land=[(588, 540), (640, 530), (662, 572), (622, 595), (588, 578)], rural=40,
         floor=0.5, army=0.7, gov="national", traits={"aggression": 1.1}),
    dict(name="Genua", side=None, land=[(675, 500), (722, 490), (738, 540), (722, 582), (690, 584), (672, 540)],
         rural=47, floor=0.5, army=0.5, gov="national", traits={"caution": 1.1}),
    dict(name="Skund", side=None, land=[(782, 520), (835, 500), (832, 560), (802, 650), (778, 640)], rural=16,
         floor=0.5, army=0.3, gov="tribal", traits={}),
    # round the Circle Sea, and rimward
    dict(name="Ephebe", side=None, land=[(388, 640), (442, 635), (446, 672), (420, 692), (388, 680)], rural=54,
         floor=0.5, army=0.5, gov="democracy", traits={"caution": 1.1}),
    dict(name="Djelibeybi", side=None, land=[(455, 640), (480, 640), (478, 700), (460, 700)], rural=61, floor=0.4,
         army=0.3, gov="national", traits={"caution": 1.2}, margin=1, spill=6.0),
    dict(name="Tsort", side=None, land=[(482, 640), (526, 640), (526, 682), (486, 688)], rural=54, floor=0.5,
         army=0.55, gov="national", traits={"aggression": 1.1}),
    dict(name="Omnia", side=None, land=[(525, 622), (572, 612), (582, 660), (546, 676), (526, 666)], rural=54,
         floor=0.5, army=0.85, gov="junta", traits={"aggression": 1.4, "caution": 0.8}),
    dict(name="Klatch", side=KLATCH, land=[(420, 690), (582, 672), (600, 742), (560, 782), (470, 782),
         (420, 742)], rural=40, floor=0.5, army=0.85, gov="national", traits={"aggression": 1.2}),
    dict(name="Hersheba", side=KLATCH, land=[(582, 660), (640, 660), (650, 722), (600, 742)], rural=34, floor=0.5,
         army=0.45, gov="national", traits={}),
    dict(name="Howondaland", side=None, land=[(410, 760), (480, 785), (560, 790), (610, 805), (560, 830),
         (470, 828), (420, 800)], rural=19, floor=0.7, army=0.4, gov="tribal", traits={}),
    dict(name="Tezuman Empire", side=None, land=[(620, 600), (720, 600), (760, 640), (740, 692), (640, 702),
         (610, 650)], rural=34, floor=0.5, army=0.6, gov="national", traits={"aggression": 1.3}),
    # the Counterweight Continent
    dict(name="Agatean Empire", side=AGATEA, land=[(285, 255), (345, 245), (370, 275), (360, 315), (320, 330),
         (285, 315)], rural=81, floor=0.6, army=0.95, gov="national", traits={"caution": 1.6}),
    dict(name="House of Hong", side=AGATEA, land=[(370, 245), (440, 230), (455, 270), (420, 300), (372, 300)],
         rural=74, floor=0.6, army=0.7, gov="national", traits={"aggression": 1.2}),
    dict(name="House of Sung", side=AGATEA, land=[(280, 175), (360, 165), (380, 215), (345, 245), (285, 250)],
         rural=68, floor=0.6, army=0.65, gov="national", traits={}),
    dict(name="House of Tang", side=AGATEA, land=[(225, 290), (285, 255), (285, 320), (255, 345), (225, 335)],
         rural=68, floor=0.6, army=0.6, gov="national", traits={}),
    dict(name="House of Fang", side=AGATEA, land=[(285, 320), (330, 330), (345, 375), (305, 385), (280, 350)],
         rural=68, floor=0.6, army=0.6, gov="national", traits={"aggression": 1.1}),
    dict(name="House of McSweeney", side=AGATEA, land=[(380, 150), (445, 140), (450, 200), (400, 225),
         (380, 205)], rural=54, floor=0.6, army=0.55, gov="national", traits={}),
    dict(name="Bhangbhangduc", side=None, land=[(455, 260), (500, 250), (505, 385), (470, 385), (450, 320)],
         rural=54, floor=0.5, army=0.4, gov="national", traits={"caution": 1.2}),
    # the Rim
    dict(name="Fourecks", side=None, land=[(636, 136), (765, 136), (765, 272), (636, 272)], rural=14, floor=0.6,
         army=0.45, gov="national", traits={"caution": 1.2}),
    dict(name="Krull", side=None, land=[(569, 127), (614, 127), (614, 171), (569, 171)], rural=54, floor=0.5,
         army=0.6, gov="national", traits={"aggression": 1.2}),
    dict(name="Brown Islands", side=None, land=[(182, 517), (204, 517), (204, 558), (182, 558)],
         extra=[[(231, 494), (251, 494), (251, 521), (231, 521)], [(261, 626), (286, 626), (286, 658), (261, 658)]],
         rural=27, floor=0.5, army=0.15, gov="tribal", traits={}),
]
# towns and fortresses: name, realm, x, y, people at the centre, radius (tiles), garrison level (0 = none)
PLACES = [
    ("Ankh-Morpork", "Ankh-Morpork", 510, 596, 255, 3, 7), ("Unseen University", "Ankh-Morpork", 504, 590, 230, 0, 7),
    ("Pseudopolis Yard", "Ankh-Morpork", 516, 590, 200, 0, 0), ("Sheepridge", "Ankh-Morpork", 495, 572, 70, 0, 0),
    ("Sto Lat", "Sto Lat", 470, 560, 210, 1, 6), ("Scrote", "Sto Lat", 460, 540, 60, 0, 0),
    ("Sto Helit", "Sto Helit", 428, 568, 170, 1, 5), ("Sto Kerrig", "Sto Kerrig", 445, 512, 150, 1, 0),
    ("Pseudopolis", "Pseudopolis", 556, 578, 200, 1, 6), ("Quirm", "Quirm", 378, 548, 190, 1, 5),
    ("Chirm", "Chirm", 392, 482, 120, 0, 0), ("Llamedos", "Llamedos", 428, 465, 110, 0, 0),
    ("Lancre Town", "Lancre", 474, 478, 130, 0, 6), ("Bad Ass", "Lancre", 486, 462, 40, 0, 0),
    ("Copperhead", "Copperhead", 495, 500, 160, 0, 7),
    ("Hubland camps", "Hubland Clans", 560, 400, 60, 0, 0), ("Hubland steadings", "Hubland Clans", 465, 410, 45, 0, 0),
    ("Hubland winter camp", "Hubland Clans", 640, 418, 40, 0, 0),
    ("Schmaltzberg", "Schmaltzberg", 592, 505, 230, 1, 7), ("Bonk", "Bonk", 628, 452, 170, 1, 6),
    ("Escrow", "Escrow", 690, 436, 200, 1, 0), ("Castle Escrow", "Escrow", 700, 426, 90, 0, 6), ("Lipwig", "Lipwig", 755, 445, 130, 0, 0),
    ("Bad Schüschein", "Bad Schüschein", 662, 488, 150, 1, 0), ("Uberwald villages", "Escrow", 676, 448, 90, 0, 0),
    ("Plotz", "Borogravia", 556, 528, 140, 0, 6), ("Kneck Fort", "Borogravia", 576, 548, 90, 0, 7),
    ("Zlobenia", "Zlobenia", 615, 562, 140, 0, 6), ("Genua", "Genua", 726, 524, 200, 1, 6),
    ("Skund", "Skund", 805, 560, 60, 0, 0),
    ("Ephebe", "Ephebe", 428, 656, 200, 1, 6), ("Djelibeybi", "Djelibeybi", 467, 664, 160, 1, 6),
    ("Tsort", "Tsort", 503, 662, 180, 1, 6), ("Kom", "Omnia", 548, 645, 190, 1, 7),
    ("Al Khali", "Klatch", 512, 700, 240, 2, 7), ("Klatchian oasis", "Klatch", 452, 724, 80, 0, 0),
    ("Gebra", "Klatch", 572, 722, 90, 0, 0), ("Hersheba", "Hersheba", 610, 690, 120, 0, 5),
    ("Howondaland kraal", "Howondaland", 470, 795, 80, 0, 0), ("Howondaland river town", "Howondaland", 590, 790, 70, 0, 0),
    ("Tezuman city", "Tezuman Empire", 655, 650, 140, 0, 6),
    ("Hunghung", "Agatean Empire", 315, 290, 255, 2, 7), ("Bes Pelargic", "House of Hong", 410, 275, 230, 1, 6),
    ("Sung province", "House of Sung", 320, 205, 140, 0, 0), ("Tang province", "House of Tang", 250, 315, 130, 0, 0),
    ("Fang province", "House of Fang", 305, 355, 130, 0, 0), ("McSweeney province", "House of McSweeney", 420, 175, 100, 0, 0),
    ("Bhangbhangduc", "Bhangbhangduc", 478, 320, 130, 0, 0),
    ("Bugarup", "Fourecks", 725, 230, 140, 0, 5), ("Fourecks station", "Fourecks", 680, 170, 40, 0, 0),
    ("Krull", "Krull", 590, 150, 170, 0, 6),
    ("Brown Islands", "Brown Islands", 192, 537, 50, 0, 0),
]
PORTS = [("Ankh-Morpork", 8), ("Quirm", 4), ("Al Khali", 6), ("Ephebe", 4), ("Bes Pelargic", 6), ("Bugarup", 3),
         ("Genua", 4), ("Krull", 3), ("Tsort", 2)]
WARS = [("Borogravia", "Zlobenia")]
RIVALS = [("Klatch", "Ankh-Morpork"), ("Omnia", "Ephebe"), ("Tsort", "Ephebe"), ("Borogravia", "Ankh-Morpork"),
          ("Hubland Clans", "Sto Lat"), ("Hubland Clans", "Lancre"), ("Bonk", "Schmaltzberg"), ("Escrow", "Lipwig"),
          ("Escrow", "Lancre"), ("House of Hong", "House of Sung"), ("House of Hong", "House of Tang"),
          ("House of Hong", "House of Fang"), ("House of Hong", "House of McSweeney"), ("Klatch", "Omnia"),
          ("Tezuman Empire", "Hersheba"), ("Djelibeybi", "Tsort")]
OUTBREAK = "Escrow"
VIRULENCE_SCALE = 1.0
SETTLE_SCALE = 1.5               # (colonies keep a bit further apart than on the world map)
WILD_RURAL = 3


def land_mask(cv):
    """The land of the Disc, traced from the picture: ochre land, blue sea; ships, monsters and the sun drawn on the
    sea left out; the snows round the Hub (white, like the sea-foam) drawn in by hand; nothing beyond the Rim."""
    from PIL import Image, ImageDraw, ImageFilter
    import labels
    here = os.path.dirname(os.path.abspath(__file__))
    img = Image.open(os.path.join(here, "data", "discworld_reference.png")).convert("RGB")
    a = np.asarray(img.filter(ImageFilter.MedianFilter(5))).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    hgt, wid = r.shape
    yy, xx = np.mgrid[:hgt, :wid]
    inside = (xx - RIM_CENTRE[0]) ** 2 + (yy - RIM_CENTRE[1]) ** 2 < RIM_RADIUS ** 2
    land = (r - b > 35) & (r >= g - 8) & inside
    zone = Image.new("L", (wid, hgt), 0)                # (the snows round the Hub: white land, teal sea)
    ImageDraw.Draw(zone).polygon([(x + X0, y + Y0) for x, y in SNOW_ZONE], fill=255)
    snowy = (np.asarray(zone) > 0) & (g - r < 14) & (b - r < 3) & ~land
    land |= snowy
    for x0, y0, x1, y1 in NOT_LAND:
        land[y0:y1, x0:x1] = False
        snowy[y0:y1, x0:x1] = False
    lab, n = labels.label(land)                         # (specks: drawings on the sea)
    size = np.bincount(lab.ravel())
    keep = size >= 150
    keep[0] = False
    land = keep[lab]
    wl, n = labels.label(~land)                         # (holes: drawings on the land)
    size = np.bincount(wl.ravel())
    fill = size < 400
    fill[0] = False
    fill[wl[0, 0]] = False
    land |= fill[wl]
    k = int(UNIT)

    def down(m):
        sub = m[Y0:Y0 + cv.rows * k, X0:X0 + cv.cols * k].astype(np.float32)
        return sub.reshape(cv.rows, k, cv.cols, k).mean(axis=(1, 3)) >= 0.5
    global _SNOW
    _SNOW = down(snowy & land)
    return down(land)


_SNOW = None
HUB_ICE, HUB_TUNDRA = 22, 48     # (picture pixels from Cori Celesti: ice within about this, tundra within that)


def paint_ground(cv, T, land, noise, noise2):
    """The cold of the Hub: the land the picture shows under snow is tundra (ice nearest the Hub), and round Cori
    Celesti ice and tundra in ragged rings - the further from the Hub, the warmer (the Disc's 'north')."""
    from terrain import ICE, TUNDRA
    rows, cols = T.shape
    hr, hc = (HUB[1]) / UNIT, (HUB[0]) / UNIT
    rr, cc = np.mgrid[:rows, :cols]
    d = np.hypot(rr - hr, cc - hc) * UNIT                # (in picture pixels)
    fine = cv.field(710, cells=(16, 32, 64, 128))
    wob = (0.6 * (noise - 0.5) + (fine - 0.5)) * 40
    snow = _SNOW if _SNOW is not None else np.zeros(T.shape, dtype=bool)
    T[land & (snow | (d + wob < HUB_TUNDRA))] = TUNDRA
    T[land & (d + wob < HUB_ICE) & (noise2 < 0.8)] = ICE
    T[land & snow & (d + 0.5 * wob < 2.2 * HUB_TUNDRA) & (fine > 0.55)] = ICE


def post(cv, T, O, D, H, by_name, sites):
    """The Great Wall of the Agatean Empire: a standing line (level 6) along the Empire's land borders with anyone
    outside it, held from Hunghung."""
    agatean = [by_name[r["name"]] for r in REALMS if r.get("side") == AGATEA]
    mine = np.isin(O, agatean)
    land = O > 0
    p = np.pad(mine | ~land, 1, constant_values=True)
    inner = np.ones(mine.shape, dtype=bool)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            inner &= p[1 + dr:p.shape[0] - 1 + dr, 1 + dc:p.shape[1] - 1 + dc]
    wall = mine & ~inner & (H > 10)
    home = next(s for s in sites if s["civ"] == by_name["Agatean Empire"])
    rr, cc = np.nonzero(wall)
    if rr.size:
        sites.append(dict(civ=by_name["Agatean Empire"], row=home["row"], col=home["col"], level=6,
                          tiles=[[int(a), int(b)] for a, b in zip(rr, cc)]))


def _shift_all():
    """Everything above is in pixels of the whole picture: move it onto the part the map covers."""
    g = globals()

    def pt(p):
        return (p[0] - X0, p[1] - Y0)

    def shape(s):
        return (s[0] - X0, s[1] - Y0, s[2]) if isinstance(s, tuple) else [pt(p) for p in s]
    g["SNOW_ZONE"] = [pt(p) for p in SNOW_ZONE]
    g["HUB"] = pt(HUB)
    for name in ("WATER", "RIVERS", "OPEN_RIVERS", "MARSHES"):
        g[name] = {k: shape(v) for k, v in g[name].items()}
    g["COLD"] = [(shape(s), t, share) for s, t, share in COLD]
    g["MOUNTAINS"] = {k: (shape(v[0]),) + tuple(v[1:]) for k, v in MOUNTAINS.items()}
    g["PEAKS"] = {k: (x - X0, y - Y0, rad) for k, (x, y, rad) in PEAKS.items()}
    g["HILLS"] = {k: shape(v) for k, v in HILLS.items()}
    for name in ("FORESTS", "RAINFOREST", "WOODLAND", "DESERTS"):
        g[name] = {k: (shape(s), share) for k, (s, share) in g[name].items()}
    for realm in REALMS:
        realm["land"] = shape(realm["land"])
        if "extra" in realm:
            realm["extra"] = [shape(e) for e in realm["extra"]]
    g["PLACES"] = [(n, rl, x - X0, y - Y0, *rest) for n, rl, x, y, *rest in PLACES]


_shift_all()


if __name__ == "__main__":
    import sys
    import drawmap
    drawmap.make(sys.modules[__name__], os.path.join("maps", "discworld"))
