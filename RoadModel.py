import random

import numpy as np
from mesa import Model
from mesa.space import MultiGrid
from mesa.time import BaseScheduler

from FillerRoad import FillerRoad
from Vehicle import Vehicle


class RoadModel(Model):

    def __init__(self, length, intersection):

        super().__init__()
        self.length = length
        self.intersection = intersection
        self.step_at_change = 0
        self.active_combo = [3, 4]
        self.schedule = BaseScheduler(self)
        self.grid = MultiGrid(self.intersection.dimensions[0], self.intersection.dimensions[1], torus=False)
        self.create_roads()
        self.create_filler_roads()
        self.create_vehicle()

    def create_roads(self):
        """ Places the lane agents on the canvas

        """

        for lk in ['ingress', 'egress']:

            data = eval(f'self.intersection.{lk}_groups')

            dir_keys = {1: (0, +1), 2: (+1, 0), 3: (0, -1), 4: (-1, 0)}

            # These are the direcion keys that fill in the roads
            ingress_dir_keys = {1: (+1, 0), 2: (0, -1), 3: (-1, 0), 4: (0, +1)}
            egress_dir_keys = {1: (-1, 0), 2: (0, +1), 3: (+1, 0), 4: (0, -1)}

            for counter, lg in enumerate(data):
                if lg is not None:
                    length = lg.length
                    lanes = lg.lanes

                    for j in range(length):

                        x_pos = (int(lg.lon) + dir_keys[counter + 1][0] * j)
                        y_pos = (int(lg.lat) + dir_keys[counter + 1][1] * j)

                        for i, lane in enumerate(lanes):
                            self.grid.place_agent(lane, (
                                x_pos + eval(f"{lk}_dir_keys")[counter + 1][0] * i,
                                y_pos + eval(f"{lk}_dir_keys")[counter + 1][1] * i))

                            # placing the carqueue objects
                            if (j == 1 or j == 3) and lk == 'ingress':

                                if j == 1:
                                    ind = 0
                                if j == 3:
                                    ind = 1

                                self.grid.place_agent(lane.car_lists[ind], (
                                    x_pos + eval(f"{lk}_dir_keys")[counter + 1][0] * i,
                                    y_pos + eval(f"{lk}_dir_keys")[counter + 1][1] * i))

                            if j == 0 and lk == 'ingress':
                                self.grid.place_agent(lane.signal_group, (
                                    x_pos + eval(f"{lk}_dir_keys")[counter + 1][0] * i,
                                    y_pos + eval(f"{lk}_dir_keys")[counter + 1][1] * i))

    def create_filler_roads(self):

        """ place FillerRoad agents between the lanes

        """

        x, y = self.intersection.center
        x, y = int(x), int(y)
        mid_square = self.intersection.mid_square
        sep = self.intersection.sep

        sep = sep - 1
        lst = list(range(x - mid_square - sep, x + 1 + mid_square + sep))

        for i in lst:
            for j in lst:
                self.grid.place_agent(FillerRoad(i + j), (i, j))

    def create_vehicle(self):
        for i in range(2):
            vehicle = Vehicle(i, self)
            self.grid.place_agent(vehicle, (1, 48 - i))
            # print(self.grid.get_cell_list_contents((51,51)))
            self.schedule.add(vehicle)

    def step(self):

        green_timing = 20

        self.schedule.step()
        current_step = self.schedule.steps
        groups = self.intersection.ingress_groups
        traffic_light_combos = self.intersection.traffic_light_combos

        if self.step_at_change + green_timing == current_step:
            self.active_combo = self.get_traffic_prio(groups)
            self.step_at_change = current_step


        for group in groups:
            if group is not None:
                lanes = group.lanes
                for lane in lanes:

                    if lane.signal_group.ID not in self.active_combo:
                        lane.signal_group.change_state('red')
                    else:
                        lane.signal_group.change_state('green')
                    rand = random.randint(0, 10)
                    if rand == 5 or rand == 3 or rand == 1:
                        lane.car_lists[0].add_car(Vehicle(1, self))
                    elif lane.signal_group.state == 'green':
                        if len(lane.car_lists[0].cars) > 0:
                            lane.car_lists[0].remove_car()

    def get_traffic_prio(self, groups):

        prio_dict = {}
        for group in groups:
            if group is not None:
                lanes = group.lanes
                for lane in lanes:
                    try:
                        prio_dict[lane.signal_group.ID] += len(lane.car_lists[0].cars)
                    except KeyError:
                        prio_dict[lane.signal_group.ID] = len(lane.car_lists[0].cars)

        combos = self.intersection.traffic_light_combos

        return combos[np.argmax([sum([prio_dict[x] if x in list(prio_dict.keys()) else 0 for x in i]) for i in combos])]
