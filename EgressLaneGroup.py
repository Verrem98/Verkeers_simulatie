from LaneGroup import LaneGroup

class EgressLaneGroup(LaneGroup):

    def __init__(self, ID, length, xml_dict, loc, kind, color = 'red'):
        LaneGroup.__init__(self, ID, length, color, xml_dict, loc, kind)
        self.color = color


