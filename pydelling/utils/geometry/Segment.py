import numpy as np

from . import Line, Point, BasePrimitive


class Segment(Line):
    def __init__(self, p1, p2):
        super().__init__(p1, p2)
        self.p1 = Point(p1)
        self.p2 = Point(p2)
        self.displacement = self.p2 - self.p1

    def __repr__(self):
        return f"Segment(p1: {self.p1}, p2: {self.p2})"

    def __str__(self):
        return f"Segment(p1: {self.p1}, p2: {self.p2})"

    @property
    def length(self):
        return np.sqrt(np.sum(self.displacement ** 2))


    def intersect(self, primitive: BasePrimitive):
        from .intersections import intersect_plane_segment

        if primitive.__class__.__name__ == "Plane":
            return intersect_plane_segment(segment=self, plane=primitive)

        else:
            raise NotImplementedError(f"Intersection of {type(self)} with {type(primitive)} is not implemented")

    def contains(self, point):
        # Calculate direction vectors
        segment_vector = self.p2 - self.p1
        point_vector = point - self.p1

        # Check if point_vector is a scalar multiple of segment_vector
        cross_product = np.cross(segment_vector, point_vector)
        if not np.allclose(cross_product, 0):
            return False

        # Check if the point lies between the segment endpoints
        dot_product = np.dot(segment_vector, point_vector)
        segment_length_squared = np.dot(segment_vector, segment_vector)

        return 0 <= dot_product <= segment_length_squared


