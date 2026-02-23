# Zombie_Sim
A zombie infection simulator using Pygame\
Takes in a txt file as input, creates a 2d array of datapoints to be used as a map\
Datapoint format: [Human Population, Zombie Population, Defense Level, Terrain, Civilization, Connected Airports]\
Human population - (0 - 255)\
Zombie population - (0 - 255)\
Defense level - (0 - 10)\
Terrain:\
  0 - Ocean\
  1 - Grassland\
  2 - Forest\
  3 - Mountain\
  4 - Desert\
  5 - Ice / Snow\
  6 - Urban\
  7 - Suburban\
Civilization - (0 - anarchy, > 0 - belongs to a civilization)\
Airport - [(76, 82), (25, 43)]

Civilization Format - [Civilization Number, Morale]\
Civilization Number - (0 - anarchy, > 0 belongs to a civilization)\
Morale - (0 - 10)

The goal of civilizations is to have a way for the humans to mount an organized defense against the zombies, and to distinguish between nations (zombies aren't the only enemy). Currently, the civilizations don't really do anything, but I will try to implement behavior into them soon.
