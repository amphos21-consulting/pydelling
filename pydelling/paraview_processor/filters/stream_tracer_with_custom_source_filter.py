"""
This class implements the Stream Tracer with custom source filter


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class StreamTracerWithCustomSourceFilter(base_filter):
    filter_type: str = "Stream_tracer_with_custom_source"
    counter: int = 0

    def __init__(self, input_filter, seed_source, name):
        """
        __init__ method.
        
        Args:
            input_filter (Any): Description.
            seed_source (Any): Description.
            name (Any): Description.
        """
        super().__init__(name=name)
        StreamTracerWithCustomSourceFilter.counter += 1
        self.filter = StreamTracerWithCustomSource(Input=input_filter)
        self.filter.SeedSource = seed_source

    def set_seed_source(self, seed_source):
        """
        set_seed_source method.
        
        Args:
            seed_source (Any): Description.
        """
        self.filter.SeedSource = seed_source

    def add_vector(self, vector_name):
        """
        add_vector method.
        
        Args:
            vector_name (Any): Description.
        """
        self.filter.Vectors = ['POINTS', vector_name]

    def add_minimum_step_length(self, minimum_step_length):
        """
        add_minimum_step_length method.
        
        Args:
            minimum_step_length (Any): Description.
        """
        self.filter.MinimumStepLength = minimum_step_length
