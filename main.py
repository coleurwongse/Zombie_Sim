# Import statements
import pygame
import keyboard
import math
import time

# Setting variables
map = []
mode = 3
knowledge_current = 0
knowledge_past = 0
pixel_size = 6
text = True
done = False


pygame.init()

screen = pygame.display.set_mode((1800, 1000))
pygame.display.set_caption("Zombie Infection Simulator")
font = pygame.font.Font(None, 36)

# Opening map file
f = open("map.txt","r")
for line in f:
    map.append(line.split('; '))
f.close()

# Setting variables to integers
for i in range(len(map)):
    for j in range(len(map[i])):
        map[i][j] = map[i][j].split(';')
        map[i][j][0] = int(map[i][j][0])
        map[i][j][1] = int(map[i][j][1])
        map[i][j][2] = int(map[i][j][2])
        map[i][j][3] = int(map[i][j][3])
        map[i][j][4] = int(map[i][j][4])
        map[i][j][5] = eval(map[i][j][5])

# Creating civilizations
civilizations = [[0, 10], [8, 10]]

# Displaying map on screen
def draw(map):
    if mode == 1 or mode == 3:
        screen.fill((0, 0, 0))
    else:
        screen.fill((0, 0, 255))
    # Iterating through datapoints
    for i in range(len(map)):
        for j in range(len(map[i])):
            # Normalizing human and zombie populations
            map[i][j][1] = normalize(map[i][j][1], 0, 255)
            map[i][j][0] = normalize(map[i][j][0], 0, 255)
            # Displays based on who controls territory
            if mode == 1:
                # If there are significantly more humans
                if map[i][j][0] > 10 >= map[i][j][1]:
                    # If there is a moderate amount of humans
                    if map[i][j][0] > 80:
                        # If there is a large amount of humans
                        if map[i][j][0] > 200:
                            pygame.draw.rect(screen, (0, 0, 255), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                        else:
                            pygame.draw.rect(screen, (0, 0, 150), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                    else:
                        pygame.draw.rect(screen, (0, 0, 75), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                # If there are significantly more zombies
                elif map[i][j][0] <= 10 < map[i][j][1]:
                    # If there is a moderate amount of zombies
                    if map[i][j][1] > 80:
                        # If there is a large amount of zombies
                        if map[i][j][1] > 200:
                            pygame.draw.rect(screen, (255, 0, 0), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                        else:
                            pygame.draw.rect(screen, (150, 0, 0), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                    else:
                        pygame.draw.rect(screen, (75, 0, 0), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                # If the populations are both small
                elif map[i][j][0] <= 10 and map[i][j][1] <= 10:
                    pygame.draw.rect(screen, (0, 0, 0), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                # If the populations are both moderately sized
                else:
                    pygame.draw.rect(screen, (255, 0, 255), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
            # Displays based on terrain
            elif mode == 2:
                # Ocean
                if map[i][j][3] == 0:
                    pygame.draw.rect(screen, (0, 0, 255), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                # Grassland
                elif map[i][j][3] == 1:
                    pygame.draw.rect(screen, (0, 150, 0), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                # Forest
                elif map[i][j][3] == 2:
                    pygame.draw.rect(screen, (0, 100, 0), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                # Mountain
                elif map[i][j][3] == 3:
                    pygame.draw.rect(screen, (75, 75, 75), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                # Desert
                elif map[i][j][3] == 4:
                    pygame.draw.rect(screen, (150, 150, 0), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                # Ice
                elif map[i][j][3] == 5:
                    pygame.draw.rect(screen, (255, 255, 255), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                # Urban
                elif map[i][j][3] == 6:
                    pygame.draw.rect(screen, (150, 150, 150), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
                # Suburban
                elif map[i][j][3] == 7:
                    pygame.draw.rect(screen, (100, 100, 100), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
            # Displays based on population density
            elif mode == 3:
                pygame.draw.rect(screen, (map[i][j][1], 0, map[i][j][0]), pygame.Rect(j * pixel_size, i * pixel_size, pixel_size, pixel_size))
            # Displays data from point on mouse position
            if text:
                try:
                    # Gets mouse position
                    mouse_pos = pygame.mouse.get_pos()
                    # Converts mouse position into grid coordinates
                    x = math.floor(mouse_pos[1] / pixel_size)
                    y = math.floor(mouse_pos[0] / pixel_size)
                    # Gets data from grid coordinates
                    text_surface = font.render(f"{map[x][y]}", True, (255, 255, 255))
                    # Displays data
                    screen.blit(text_surface, (800, 800))
                except:
                    pass
    # Updates display
    pygame.display.update()

# Human movement
def human_movement(num_humans, x, y, x1, y1):
    # If target point is off the map
    if y1 >= len(map):
        y1-=len(map)
    if x1 < len(map):
        num = 0
        # If original point is not on the ocean
        if map[x][y][3] != 0:
            # If target point has a higher defense level
            if map[x][y][2] < map[x1][y1][2] + 1:
                if int(num_humans/8) + map[x1][y1][0] > 255:
                    num = 255 - num_humans
                else:
                    num = int(num_humans/8)
            # If target point is a mountain
            elif map[x1][y1][3] == 3 and map[x][y][3] != 3:
                if int(num_humans/8) + map[x1][y1][0] > 255:
                    num = 255 - num_humans
                else:
                    num = int(num_humans/8)
            # If target point is ocean
            elif map[x1][y1][3] == 0:
                if int(num_humans/8) + map[x1][y1][0] > 255:
                    num = 255 - num_humans
                else:
                    num = int(num_humans/8)
            # If target point has fewer zombies
            elif map[x][y][1] > map[x1][y1][1] and map[x][y][2] <= map[x1][y1][2]:
                if int(num_humans/8) + map[x1][y1][0] > 255:
                    num = 255 - num_humans
                else:
                    num = int(num_humans/8)
        # If target point is a mountain
        elif map[x1][y1][3] == 3 and map[x1][y1][1] < map[x][y][1]:
            if int(num_humans / 8) + map[x1][y1][0] > 255:
                num = 255 - num_humans
            else:
                num = int(num_humans / 8)
        # If target point has fewer zombies
        elif map[x1][y1][1] + 5 <= map[x][y][1]:
            if int(num_humans / 8) + map[x1][y1][0] > 255:
                num = 255 - num_humans
            else:
                num = int(num_humans / 8)
        # Updates human populations
        map[x][y][0] -= num
        map[x1][y1][0] += num

# Zombie movement
def zombie_movement(num_zombies, x, y, x1, y1):
    # If target point is off the map
    if y1 >= len(map):
        y1-=len(map)
    if x1 < len(map) and map[x1][y1][2] < 7:
        num = 0
        # If the original point is ocean
        if map[x][y][3] == 0:
            if map[x1][y1][0] > 5:
                num = int(num_zombies / 5)
            elif map[x1][y1][1] < num_zombies:
                num = int((num_zombies - map[x1][y1][1]) / 3)
        # If the original point is mountain
        elif map[x][y][3] == 3:
            if map[x1][y1][0] > 5:
                num = int(num_zombies / 5)
            elif map[x1][y1][1] < num_zombies:
                num = int((num_zombies - map[x1][y1][1]) / 3)
        else:
            # If datapoint is not ocean
            if map[x1][y1][3] > 0:
                if map[x1][y1][0] > 5:
                    # If datapoint is not mountain
                    if map[x1][y1][3] != 3:
                        num = int(num_zombies / 5)
                    else:
                        num = int(num_zombies / 8)
                elif map[x1][y1][1] < num_zombies:
                    num = int((num_zombies - map[x1][y1][1]) / 3)
            elif map[x1][y1][1] < int(num_zombies / 5):
                num = math.ceil((num_zombies - map[x1][y1][1]) / 100)
        # Updates zombie populations
        map[x][y][1] -= num
        map[x1][y1][1] += num

# Normalizes variables
def normalize(num, min, max):
    if num < min:
        num = min
    elif num > max:
        num = max
    return num

# Game loop
while not done:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            done = True
    knowledge_past = knowledge_current

    # Changing display modes
    if keyboard.is_pressed('1'):
        mode = 1
    elif keyboard.is_pressed('2'):
        mode = 2
    elif keyboard.is_pressed('3'):
        mode = 3
    if keyboard.is_pressed('t'):
        text = False
    draw(map)
    civilizations[1][1] = 0

    # Counting number of points controlled by civilization
    for i in range(len(map)):
        for j in range(len(map[i])):
            if map[i][j][4] > 0 and map[i][j][0] > 10:
                civilizations[map[i][j][4]][1] += 1
            elif map[i][j][0] <= 10:
                map[i][j][4] = 0
                map[i][j][2] = 1

    # Setting morale and defense levels
    for i in range(len(civilizations)):
        # If number of points controlled is too low, morale goes down
        if civilizations[i][1] < 2:
            civilizations[i][0] -= 1
        # Otherwise, morale goes up
        elif civilizations[i][0] < 10:
            civilizations[i][0] += 1
        # If morale is too low, civilization collapses into anarchy
        if civilizations[i][0] < 2:
            for j in range(len(map)):
                for k in range(len(map[j])):
                    if map[j][k][4] == i:
                        map[j][k][4] = 0
    # Iterates through datapoints
    for i in range(len(map)):
        for j in range(len(map[i])):
            if map[i][j][0] > 0:
                # If there is an airport
                if map[i][j][5]:
                    # If the datapoint is infected
                    if map[i][j][1] > 10 or map[i][j][0] < 5:
                        # If datapoint is completely infected, there is no airport
                        if map[i][j][1] > map[i][j][0]:
                            map[i][j][5] = []
                        # Otherwise, infection spreads to other airports
                        else:
                            for k in map[i][j][5]:
                                if map[k[0]][k[1]][1] < 1:
                                    map[k[0]][k[1]][1] += 1

                # If there are zombies and the defense level is extremely high, zombies are exterminated
                if map[i][j][1] > 0 and map[i][j][2] >= 7:
                    map[i][j][1] = 0
                # If population is high enough, defense level is moderate
                if map[i][j][0] > 122 and map[i][j][4] > 0 and map[i][j][2] < 5 and map[i][j][3] == 6:
                    map[i][j][2] = 5
                # If human population is high enough and there is a zombie population, knowledge of infection increases
                if map[i][j][0] > 20 and  knowledge_current < 50 and map[i][j][1] > 5 and knowledge_current - knowledge_past < 1:
                    knowledge_current += 1
                # If knowledge of infection is high enough, defense level increases
                if knowledge_current == 25 or knowledge_current == 49:
                    map[i][j][2] += 1
                # If human population is too low, defense level decreases
                if map[i][j][0] < 50 and map[i][j][2] > 5:
                    map[i][j][2] = 5
                    # If human population is too low, defense level decreases even more
                    if map[i][j][0] < 10 and map[i][j][2] > 2:
                        map[i][j][2] = 2
                        # If human population is too low, defense decreases
                        if map[i][j][0] < 5:
                            map[i][j][2] = 1
                            # If human population is too low, it can be ignored
                            if map[i][j][0] < 3:
                                map[i][j][0] = 0
                # If morale is too low, defense decreases
                if civilizations[map[i][j][4]][0] < map[i][j][2] - 2:
                    map[i][j][2] = civilizations[map[i][j][4]][0]
                # Normalizes defense level
                map[i][j][2] = normalize(map[i][j][2], 0, 10)
                # Calculates casualties
                # If the datapoint is not ocean or mountain
                if map[i][j][0] > 0 and map[i][j][3] != 3:
                    # Helps zombies survive in low populations from airports
                    if 0 < map[i][j][1] < 5 and map[i][j][2] < 5 and map[i][j][5]:
                        num = math.ceil(map[i][j][0] * map[i][j][1] / map[i][j][2] / 80) + 7
                        map[i][j][0] -= num
                        map[i][j][1] += num
                    # Otherwise, do normal calculations
                    else:
                        num = int(map[i][j][0] * map[i][j][1] / map[i][j][2] / 80)
                        map[i][j][0] -= num
                        map[i][j][1] += num - int((map[i][j][1] / 255) * map[i][j][2] * map[i][j][2])
                # If the datapoint is mountain
                elif map[i][j][3] == 3 and map[i][j][0] > 10:
                    num = int(map[i][j][0] * map[i][j][1] / map[i][j][2] / 255)
                    map[i][j][0] -= num
                    map[i][j][1] += num - int((map[i][j][1] / 20) * map[i][j][2] * map[i][j][2])
                # If the datapoint is ocean
                elif map[i][j][3] == 0 and map[i][j][0] > 10:
                    num = int(map[i][j][0] * map[i][j][1] / map[i][j][2] / 80)
                    map[i][j][0] -= num
                    map[i][j][1] += num - int((map[i][j][1] / 255) * map[i][j][2] * map[i][j][2])
            # Zombie movement
            if map[i][j][1] > 0:
                num_zombies = map[i][j][1]
                zombie_movement(num_zombies, i, j, i+1, j)
                zombie_movement(num_zombies, i, j, i-1, j)
                zombie_movement(num_zombies, i, j, i, j+1)
                zombie_movement(num_zombies, i, j, i, j-1)
            # Human movement
            if knowledge_current > 5 and map[i][j][1] > 5 and map[i][j][0] > 0:
                num_humans = map[i][j][0]
                human_movement(num_humans, i, j, i+1, j)
                human_movement(num_humans, i, j, i-1, j)
                human_movement(num_humans, i, j, i, j+1)
                human_movement(num_humans, i, j, i, j-1)
                human_movement(num_humans, i, j, i+1, j+1)
                human_movement(num_humans, i, j, i-1, j-1)
                human_movement(num_humans, i, j, i-1, j+1)
                human_movement(num_humans, i, j, i+1, j-1)
                human_movement(num_humans, i, j, i+2, j)
                human_movement(num_humans, i, j, i-2, j)
                human_movement(num_humans, i, j, i, j+2)
                human_movement(num_humans, i, j, i, j+2)


