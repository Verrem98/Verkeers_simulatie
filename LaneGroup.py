import pandas as pd
import numpy as np
from Lane import Lane


class LaneGroup:
    def __init__(self, ID, length, color, lane_df, loc, kind, intersection):

        self.ID = ID
        self.length = length
        self.color = color
        self.lane_df = lane_df
        self.lon = loc[0]
        self.lat = loc[1]
        self.kind = kind
        self.intersection = intersection
        self.lanes = self.get_lanes()
        self.width = len(self.lanes)
        self.order_lanes()

    def order_lanes(self):
        left = []
        right = []
        straight = []
        left_straight = []
        right_straight = []

        if self.kind == 'ingress':
            for lane in self.lanes:

                if lane.connections is not None:

                    maneuvers = list(set([p['maneuver'] for p in lane.connections]))

                    if '010000000000' in maneuvers:
                        if '100000000000' in maneuvers:
                            right_straight.append(lane)
                            continue
                        right.append(lane)

                    elif '001000000000' in maneuvers:
                        if '100000000000' in maneuvers:
                            left_straight.append(lane)
                            continue
                        left.append(lane)

                    elif '100000000000' in maneuvers:
                        straight.append(lane)

            self.lanes = right + right_straight + straight + left_straight + left

    def get_lane_connections(self, id):

        xml = self.intersection.xml_dict['topology']['mapData']['intersections']['intersectionGeometry']['laneSet'][
            'genericLane']

        connection_dict = {}
        for x in xml:

            if x['laneAttributes']['sharedWith'] == '0001000000':

                try:
                    connection_dict[int(x['laneID'])] = [
                        {'connecting_lane': x['connectsTo']['connection']['connectingLane']['lane'],
                         'maneuver': x['connectsTo']['connection']['connectingLane']['maneuver']}]
                except TypeError:

                    temp_list = []
                    for i in x['connectsTo']['connection']:
                        temp_list.append({'connecting_lane': i['connectingLane']['lane'],
                                          'maneuver': i['connectingLane']['maneuver']})
                    connection_dict[int(x['laneID'])] = temp_list
                except KeyError:
                    continue

        try:
            connection = connection_dict[id]
        except KeyError:
            connection = None


        for k,v in connection_dict.items():
            print(k,v)
            print()
        return connection

    def get_lanes(self):
        df = self.lane_df

        lane_numbers = list(df[['laneID']][df[f'{self.kind}Approach'].astype(str) == str(int(self.ID))]['laneID'])

        return [Lane(x, self.color, self.kind, self.get_lane_connections(int(x)), self.intersection) for x in
                lane_numbers]
