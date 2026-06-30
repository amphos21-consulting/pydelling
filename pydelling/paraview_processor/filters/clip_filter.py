"""
This class implements the Paraview Integrate Variables filter


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class ClipFilter(base_filter):
    """ParaView Clip filter wrapper.

    Category: ParaView filter.
    Tags: paraview, clip, box, geometry.
    Usage: to clip a ParaView dataset, including
        box-shaped clipping regions.
    """

    filter_type: str = "Clip"
    counter: int = 0

    def __init__(self, input_filter, name, *args, **kwargs):
        """
        __init__ method.
        
        Args:
            input_filter (Any): Description.
            name (Any): Description.
            *args (Any): Description.
            **kwargs (Any): Description.
        """
        super().__init__(name=name)
        ClipFilter.counter += 1
        self.filter = Clip(Input=input_filter)
        for kwarg in kwargs:
            setattr(self.filter, kwarg, kwargs[kwarg])

    def clip_box(self, box_position, box_length, exact = True):
        """
        This method clips a box like domain into the filter
        Args:
            box_position: bottom left corner coordinates of the box.
            box_length: length vector of the box.
            exact: if true, the box will clip exactly the source filter.
        """
        self.filter.ClipType = 'Box'
        self.filter.ClipType.Position = box_position
        self.filter.ClipType.Length = box_length
        self.filter.Exact = exact
