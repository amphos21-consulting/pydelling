"""
This class implements the Paraview Integrate Variables filter


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass




class IntegrateVariablesFilter(base_filter):
    """ParaView IntegrateVariables wrapper.

    Category: ParaView filter.
    Tags: paraview, integrate-variables, cell-data, volume.
    Use when: to integrate field variables over a ParaView
        dataset.
    """

    filter_type: str = "Integrate_variables"
    counter: int = 0

    def __init__(self, input_filter, name, divide_cell_data_by_volume=False):
        """Create an IntegrateVariables filter.

        Category: ParaView filter.
        Tags: paraview, integrate-variables, initialization.
        Use when: adding an integration step to a ParaView processing pipeline.
        Args:
            input_filter: Upstream ParaView proxy to integrate.
            name: Logical filter name passed to the base filter wrapper.
            divide_cell_data_by_volume: Whether to normalize cell data by
                integrated volume.
        Side effects:
            Creates the ParaView ``IntegrateVariables`` proxy and sets
            normalization behavior.
        """
        super().__init__(name=name)
        IntegrateVariablesFilter.counter += 1
        self.filter = IntegrateVariables(Input=input_filter)
        self.set_divide_cell_data_by_volume(divide_cell_data_by_volume)

    def set_divide_cell_data_by_volume(self, value):
        """Set whether cell data is divided by volume.

        Category: ParaView filter.
        Tags: paraview, integrate-variables, volume-normalization.
        Use when: toggling volume-normalized integrated results.
        Args:
            value: Boolean-like value assigned to the ParaView property.
        Side effects:
            Mutates ``self.filter.DivideCellDataByVolume``.
        """
        self.filter.DivideCellDataByVolume = value
