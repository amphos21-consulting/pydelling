from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class AppendArcLengthFilter(base_filter):
    """
    This class implements the Append Arc-Length filter
    """
    filter_type: str = "Append_arc_length"
    counter: int = 0

    def __init__(self, input_filter, name):
        super().__init__(name=name)
        AppendArcLengthFilter.counter += 1
        self.filter = AppendArcLength(Input=input_filter)