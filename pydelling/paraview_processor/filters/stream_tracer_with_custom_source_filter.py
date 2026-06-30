"""
This class implements the Stream Tracer with custom source filter


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class StreamTracerWithCustomSourceFilter(base_filter):
    """ParaView Stream Tracer wrapper with an externally supplied seed source.

    Category: ParaView filter.
    Tags: paraview, stream-tracer, seed-source, vectors, filter.
    Use when: to configure streamline generation from a
        custom source object in a ParaView processing pipeline.
    """

    filter_type: str = "Stream_tracer_with_custom_source"
    counter: int = 0

    def __init__(self, input_filter, seed_source, name):
        """Create the ParaView stream tracer filter and set its seed source.

        Category: ParaView filter.
        Tags: paraview, stream-tracer, initialization, seed-source.
        Use when: adding a custom-seeded stream tracer to an existing ParaView
            pipeline.
        Args:
            input_filter: Upstream ParaView proxy used as tracer input.
            seed_source: ParaView source proxy used to seed streamlines.
            name: Logical filter name passed to the base filter wrapper.
        Side effects:
            Increments the class counter and creates a
            ``StreamTracerWithCustomSource`` ParaView proxy.
        """
        super().__init__(name=name)
        StreamTracerWithCustomSourceFilter.counter += 1
        self.filter = StreamTracerWithCustomSource(Input=input_filter)
        self.filter.SeedSource = seed_source

    def set_seed_source(self, seed_source):
        """Replace the ParaView seed source proxy.

        Category: ParaView filter.
        Tags: paraview, stream-tracer, seed-source.
        Use when: changing streamline seed geometry after filter creation.
        Args:
            seed_source: ParaView source proxy to assign to ``SeedSource``.
        Side effects:
            Mutates ``self.filter.SeedSource``.
        """
        self.filter.SeedSource = seed_source

    def add_vector(self, vector_name):
        """Select the point-vector field used for streamline integration.

        Category: ParaView filter.
        Tags: paraview, stream-tracer, vectors, point-data.
        Use when: configuring which vector variable drives the stream tracer.
        Args:
            vector_name: Name of the point-data vector array.
        Side effects:
            Sets ``self.filter.Vectors`` to ``["POINTS", vector_name]``.
        """
        self.filter.Vectors = ['POINTS', vector_name]

    def add_minimum_step_length(self, minimum_step_length):
        """Set the minimum integration step length.

        Category: ParaView filter.
        Tags: paraview, stream-tracer, integration, step-length.
        Use when: tuning streamline integration resolution.
        Args:
            minimum_step_length: Minimum step length assigned to the ParaView
                filter.
        Side effects:
            Mutates ``self.filter.MinimumStepLength``.
        """
        self.filter.MinimumStepLength = minimum_step_length
