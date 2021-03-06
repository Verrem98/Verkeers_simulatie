import random

import numpy as np
from mesa import Model
from mesa.datacollection import DataCollector
from mesa.space import MultiGrid
from mesa.time import BaseScheduler

from DenBoschBusRoute.agent import Bus
from DenBoschBusRoute.agent import FillerRoad
from DenBoschBusRoute.agent import Vehicle


class RoadModel(Model):

    def __init__(self, green_length, orange_length, red_clearance_time, bus_weight, traffic_light_priority, create_ci,
                 pity_timer_limit, car_spawn_rate, car_despawn_rate, bus_spawn_rate):

        super().__init__()
        self.bus_spawn_rate = bus_spawn_rate
        self.car_despawn_rate = car_despawn_rate
        self.red_clearance_time = red_clearance_time
        self.car_spawn_rate = car_spawn_rate
        self.pity_timer_limit = pity_timer_limit
        self.bus_weight = bus_weight
        self.traffic_light_priority = traffic_light_priority
        self.ci = None
        create_ci(self)
        self.bus_lanes = self.ci.bus_lanes
        self.green_length = green_length
        self.orange_length = orange_length
        self.schedule = BaseScheduler(self)
        self.grid = MultiGrid(self.ci.dimensions[0], self.ci.dimensions[1], torus=False)
        self.bus_spawns = [None for _ in self.ci.intersections_list]
        self.vehicle_graveyard = [VehicleGraveyard(int(i.ID)) for i in self.ci.intersections_list[::-1]]

        self.create_roads()

        print(self.ci)

        self.datacollector = DataCollector(
            model_reporters={
                "cars_1": self.car_wait_time_1,
                "cars_2": self.car_wait_time_2,
                "busses_1": self.bus_wait_time_1,
                "busses_2": self.bus_wait_time_2
            }
        )
        self.running = True
        self.datacollector.collect(self)

    def create_roads(self):
        """
        Places the lane agents on the canvas

        """

        for intersection in self.ci.intersections.reshape(1, 9)[0]:

            if intersection is not None:
                intersection_id = intersection.ID

                self.create_filler_roads(intersection)

                for lk in ['ingress', 'egress']:

                    data = eval(f'intersection.{lk}_groups')

                    dir_keys = {1: (0, +1), 2: (+1, 0), 3: (0, -1), 4: (-1, 0)}

                    # These are the direcion keys that fill in the roads (for future use)
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
                                    bus_lane = int(self.bus_lanes[intersection_id])
                                    self.grid.place_agent(lane, (
                                        x_pos + eval(f"{lk}_dir_keys")[counter + 1][0] * i,
                                        y_pos + eval(f"{lk}_dir_keys")[counter + 1][1] * i))

                                    # placing the carqueue objects
                                    if (j == 1) and lk == 'ingress':

                                        if j == 1:
                                            ind = 0

                                        self.grid.place_agent(lane.car_lists[ind], (
                                            x_pos + eval(f"{lk}_dir_keys")[counter + 1][0] * i,
                                            y_pos + eval(f"{lk}_dir_keys")[counter + 1][1] * i))

                                    if j == 0 and lk == 'ingress':
                                        self.grid.place_agent(lane.signal_group, (
                                            x_pos + eval(f"{lk}_dir_keys")[counter + 1][0] * i,
                                            y_pos + eval(f"{lk}_dir_keys")[counter + 1][1] * i))

                                    if j == 2 and lk == 'ingress' and int(lane.ID) == bus_lane:
                                        x_cor = x_pos + eval(f"{lk}_dir_keys")[counter + 1][0] * i
                                        y_cor = y_pos + eval(f"{lk}_dir_keys")[counter + 1][1] * i
                                        # stores coordinates where bus icons will be
                                        self.bus_spawns[intersection_id] = (x_cor, y_cor)
                                    if j == 3 and lk == 'ingress' and int(lane.ID) == bus_lane:
                                        self.grid.place_agent(lane.car_lists[1], (
                                            x_pos + eval(f"{lk}_dir_keys")[counter + 1][0] * i,
                                            y_pos + eval(f"{lk}_dir_keys")[counter + 1][1] * i))

    def create_filler_roads(self, intersection):
        """
        place FillerRoad agents between the lanes

        """

        x, y = intersection.center
        x, y = int(x), int(y)

        mid_square = intersection.mid_square
        sep = intersection.sep

        sep = sep - 1
        lst = list(range(x - mid_square - sep, x + 1 + mid_square + sep))
        lst2 = list(range(y - mid_square - sep, y + 1 + mid_square + sep))

        for i in lst:
            for j in lst2:
                self.grid.place_agent(FillerRoad(i + j), (i, j))

    def step(self):
        """
        the main simulation loop, everything in here gets executed every simulation tick

        """

        self.schedule.step()
        self.datacollector.collect(self)
        current_step = self.schedule.steps

        for intersection_id, intersection in enumerate(self.ci.intersections.reshape(1, 9)[0]):

            if intersection is not None:
                intersection_id = intersection.ID

                intersection.pity_traffic_light = self.check_for_pity_timer(intersection)

                groups = intersection.ingress_groups

                for group in groups:
                    if group is not None:
                        lanes = group.lanes
                        for lane in lanes:
                            self.increase_waiting_time(lane)

                            bus_lane = int(self.bus_lanes[intersection_id])
                            self.traffic_light_control(lane, current_step, groups, intersection)

                            self.spawn_vehicle(lane, self.car_spawn_rate, intersection)
                            if lane.signal_group.state == 'green':
                                self.despawn_vehicle(lane, intersection)

                            if int(lane.ID) == bus_lane:
                                if lane.bus is None:
                                    self.spawn_bus(intersection, lane)
                                if lane.signal_group.state == 'green' and lane.bus is not None:
                                    self.despawn_bus(lane, intersection)

    def get_traffic_prio(self, groups, intersection, pity_light):
        """
        get the traffic light combination with the longest queue

        :param groups: lanegroup
        :param intersection: intersection
        :param pity_light: combinations must contain pity light (can be None)
        :return: traffic light combination with the longest queue
        """

        prio_dict = {}
        for group in groups:
            if group is not None:
                lanes = group.lanes
                for lane in lanes:
                    if lane.bus is None:
                        bus_weight = 0
                    else:
                        bus_weight = int(lane.bus.weight)

                    try:
                        prio_dict[lane.signal_group.ID] += (
                                len(lane.car_lists[0].cars) + len(lane.car_lists[1].cars) + bus_weight)
                    except KeyError:
                        prio_dict[lane.signal_group.ID] = (
                                len(lane.car_lists[0].cars) + len(lane.car_lists[1].cars) + bus_weight)

        combos = intersection.traffic_light_combos
        if pity_light is not None:
            combos = ([i for i in combos if pity_light in i])
            if len(combos) == 0:
                combos = intersection.traffic_light_combos
        return combos[np.argmax([sum([prio_dict[x] if x in list(prio_dict.keys()) else 0 for x in i]) for i in combos])]

    def traffic_light_control(self, lane, current_step, groups, intersection):
        """
        traffic light cycle controller

        :param lane: lane
        :param current_step: current simulation step
        :param groups: lanegroup
        :param intersection: intersection
        """

        if lane.signal_group.ID not in intersection.current_green:
            lane.signal_group.change_state('red')
            lane.signal_group.ticks_since_state_change += 1
        if (
                lane.signal_group.state == 'red' or lane.signal_group.state == 'orange') and lane.signal_group.ID in intersection.current_green and intersection.step_at_change + self.green_length > current_step:
            lane.signal_group.change_state('green')
            intersection.step_at_change = current_step
            lane.signal_group.ticks_since_state_change = 0
        if intersection.step_at_change + self.green_length == current_step and lane.signal_group.state == 'green':
            lane.signal_group.change_state('orange')
        if intersection.step_at_change + self.green_length + self.orange_length == current_step:
            lane.signal_group.change_state('red')
        if intersection.step_at_change + self.green_length + self.orange_length + self.red_clearance_time == current_step:
            lane.signal_group.change_state('red')
            if self.traffic_light_priority:
                pity = intersection.pity_traffic_light
                intersection.current_green = self.get_traffic_prio(groups, intersection, pity)
            else:
                try:
                    intersection.current_green = intersection.traffic_light_combos[
                        intersection.traffic_light_combos.index(intersection.current_green) + 1]

                except IndexError:
                    intersection.current_green = intersection.traffic_light_combos[0]

            intersection.step_at_change = current_step + 1

    def spawn_vehicle(self, lane, chance, intersection):
        """
        chance to spawn a vehicle

        :param lane: lane
        :param chance: chance to spawn vehicle every tick
        :param intersection: intersection
        """

        if random.random() < chance:
            bus_lane = int(self.bus_lanes[intersection.ID])
            if lane.shared_with[4] != '1':
                if lane.bus is not None and int(lane.ID) == bus_lane:
                    lane.car_lists[1].add_car(Vehicle(self))
                else:
                    lane.car_lists[0].add_car(Vehicle(self))

    def despawn_vehicle(self, lane, intersection):
        """
        despawn a verhicle every 'car_despawn_rate' ticks

        :param lane: lane
        :param intersection: intersection
        """

        if len(lane.car_lists[0].cars) > 0:
            steps = self.schedule.steps - intersection.step_at_change
            if steps == 0 or steps % self.car_despawn_rate == 0:
                self.vehicle_graveyard[intersection.ID].add_car(lane.car_lists[0].cars[0])
                lane.car_lists[0].remove_car()

    def spawn_bus(self, intersection, lane):
        """
        spawn a bus every 'bus_spawn_rate' ticks

        :param intersection: intersection
        :param lane: lane
        """

        if self.schedule.steps % self.bus_spawn_rate == 0:
            bus = Bus(intersection.ID, self.bus_weight, self)
            lane.bus = bus

            self.schedule.add(lane.bus)
            self.grid.place_agent(lane.bus, self.bus_spawns[intersection.ID])

    def despawn_bus(self, lane, intersection):
        """
        despawn a bus if it can go through a green light

        :param lane: lane
        :param intersection: intersection
        """

        if len(lane.car_lists[0].cars) < 1:
            self.vehicle_graveyard[intersection.ID].add_bus(lane.bus)

            try:
                self.grid.remove_agent(lane.bus)
                self.schedule.remove(lane.bus)
            except ValueError:
                pass
            lane.bus = None
            if len(lane.car_lists[1].cars) > 0:
                for i in lane.car_lists[1].cars:
                    lane.car_lists[0].add_car(i)
                lane.car_lists[1].clear_cars()

    def car_wait_time_1(self):
        """
        :return: avg. waiting time per car in intersection 1

        """

        return np.mean([car.wait_time for car in self.vehicle_graveyard[0].cars]) if len(
            self.vehicle_graveyard[0].cars) > 0 else 0

    def car_wait_time_2(self):
        """
        :return: avg. waiting time per car in intersection 2

        """

        return np.mean([car.wait_time for car in self.vehicle_graveyard[1].cars]) if len(
            self.vehicle_graveyard[1].cars) > 0 else 0

    def bus_wait_time_1(self):
        """
        :return: avg. waiting time per bus in intersection 1

        """

        return np.mean([bus.wait_time for bus in self.vehicle_graveyard[0].busses]) if len(
            self.vehicle_graveyard[0].busses) > 0 else 0

    def bus_wait_time_2(self):
        """
        :return: avg. waiting time per bus in intersection 2

        """

        return np.mean([bus.wait_time for bus in self.vehicle_graveyard[1].busses]) if len(
            self.vehicle_graveyard[1].busses) > 0 else 0

    def increase_waiting_time(self, lane):
        """
        increase the wait time attribute of all cars in a specific lane

        :param lane: lane
        """

        for i in range(2):
            for car in lane.car_lists[i].cars:
                car.increase_wait_time()

        if lane.bus is not None:
            lane.bus.increase_wait_time()

    def check_for_pity_timer(self, intersection):
        """
        check for every traffic light if they've been inactive for 'pity_timer_limit' ticks, if True, return the traffic light ID

        :param intersection: intersection
        :return: traffic_light_id or None
        """

        if intersection is not None:

            groups = intersection.ingress_groups

            for group in groups:
                if group is not None:
                    lanes = group.lanes
                    for lane in lanes:

                        if self.pity_timer_limit < lane.signal_group.ticks_since_state_change:
                            return lane.signal_group.ID
                            continue

            return None


class VehicleGraveyard:

    def __init__(self, i):
        self.cars = []
        self.ID = i
        self.busses = []

    def add_car(self, car):
        self.cars.append(car)

    def add_bus(self, car):
        self.busses.append(car)
