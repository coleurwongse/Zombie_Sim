"""Terrain types and everything that depends on them, in one place.

    id  name       colour (terrain view / terrain.png)   notes
    0   deep water   (0, 0, 255)       open sea; zombies drift, hordes head for land
    1   grass        (0, 150, 0)       farmland, plains
    2   forest       (0, 100, 0)
    3   mountain     (75, 75, 75)      zombies slow, defenders strong, few people
    4   desert       (150, 150, 0)
    5   ice          (255, 255, 255)   polar ice caps, glaciers: nobody lives here
    6   urban        (150, 150, 150)
    7   suburban     (100, 100, 100)
    8   shallow water (70, 130, 255)   coastal shelf, lakes: zombies swim, come ashore easily
    9   highlands    (125, 135, 70)    between plains and mountains: a little protection, fewer people
    10  tundra       (165, 185, 160)   cold, thin, few people
    11  wetlands     (40, 140, 130)    marsh, swamp, bog: zombies (and everyone else) bog down, few people
    12  rainforest   (10, 70, 35)      dense tropical forest: slow going, hard to see what's coming, few people

Ids 0-7 are the original ones, so old maps load unchanged.  Water = deep or shallow; everything else is land.
"""
import numpy as np

DEEP, GRASS, FOREST, MOUNTAIN, DESERT, ICE, URBAN, SUBURBAN, SHALLOW, HIGHLANDS, TUNDRA, WETLAND, RAINFOREST = range(13)
N = 13
NAMES = ("deep water", "grass", "forest", "mountain", "desert", "ice", "urban", "suburban", "shallow water",
         "highlands", "tundra", "wetlands", "rainforest")
COLORS = np.array([(0, 0, 255), (0, 150, 0), (0, 100, 0), (75, 75, 75), (150, 150, 0), (255, 255, 255),
                   (150, 150, 150), (100, 100, 100), (70, 130, 255), (125, 135, 70), (165, 185, 160),
                   (40, 140, 130), (10, 70, 35)], dtype=np.int32)

#                         deep grass forest mount desert ice  urban suburb shallow highl tundra wetl  rainf
CAP = np.array([           0, 110,  70,   30,   25,    0,  255,  200,    0,     60,   12,    30,   35])   # people a tile supports
FOOD_YIELD = np.array([  0.0, 0.100, 0.0375, 0.002, 0.030, 0.0, 0.0, 0.025, 0.0,  0.050, 0.010, 0.030, 0.020])
MATERIAL_YIELD = np.array([0.0, 0.00020, 0.0004, 0.0016, 0.00008, 0.0, 0.007, 0.004, 0.0, 0.0010, 0.0005, 0.0002,
                           0.0006])
PROTECTION = np.array([     0,   0,    1,    5,    0,    0,    0,    0,    0,     3,    1,     2,    2])   # how hard to overrun
DENSITY = np.array([      0.0, 1.0, 0.35, 0.12, 0.03, 0.0,  1.0,  1.0,  0.0,   0.45, 0.04,  0.15, 0.18])  # map generators
# how readily zombies move onto the terrain, relative to open ground (engine.py, zombies.py): mountains are a real
# barrier (hordes go round, or trickle through the passes), deserts, swamps, jungle and hills slow them down
#                         deep grass forest mount desert ice  urban suburb shallow highl tundra wetl  rainf
MOVE = np.array([         1.0, 1.0,  0.85, 0.15, 0.6,  0.3,  1.0,  1.0,  1.0,  0.55, 0.75,  0.4,  0.55], dtype=np.float32)


def is_water(T):
    return (T == DEEP) | (T == SHALLOW)


def is_land(T):
    return (T != DEEP) & (T != SHALLOW)


def habitable(T):
    """Land people can settle (not water, not ice)."""
    return is_land(T) & (T != ICE)
