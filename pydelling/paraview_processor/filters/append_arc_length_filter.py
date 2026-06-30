"""
This class implements the Append Arc-Length filter


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class AppendArcLengthFilter(base_filter):
    """ParaView AppendArcLength filter wrapper.

    Category: ParaView filter.
    Tags: paraview, arc-length, polyline, filter.
    Use when: to append cumulative arc-length values to a
        ParaView line or path dataset.
    """

    filter_type: str = "Append_arc_length"
    counter: int = 0

    def __init__(self, input_filter, name):
        """
        __init__ method.
        
        Args:
            input_filter (Any): Description.
            name (Any): Description.
        """
        super().__init__(name=name)
        AppendArcLengthFilter.counter += 1
        self.filter = AppendArcLength(Input=input_filter)
