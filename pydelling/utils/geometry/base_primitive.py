from __future__ import annotations

class BasePrimitive:
    """Base marker for geometry primitives.

    Category: geometry primitive.
    Tags: geometry, primitive, tolerance.
    Use when: to understand the shared base type for points, lines, planes,
        vectors, segments, and polygons.
    """

    eps = 1e-15
