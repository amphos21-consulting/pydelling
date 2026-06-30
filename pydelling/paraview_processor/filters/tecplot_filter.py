"""
Module documentation.


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class TecplotFilter(base_filter):
    """ParaView Tecplot reader wrapper.

    Category: ParaView filter.
    Tags: paraview, tecplot, reader, filter.
    Use when: to load Tecplot files into a pydelling ParaView
        processing pipeline.
    """

    filter_type: str = "tecplot_reader"
    counter: int = 0

    def __init__(self, filename, name):
        """
        __init__ method.
        
        Args:
            filename (Any): Description.
            name (Any): Description.
        """
        super().__init__(name=name)
        self.filter = TecplotReader(FileNames=str(filename))
        TecplotFilter.counter += 1
