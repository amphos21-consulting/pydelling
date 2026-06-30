"""
Module documentation.


"""

from pydelling.paraview_processor.filters import base_filter
try:
    from paraview.simple import *
except:
    pass


class CalculatorFilter(base_filter):
    """ParaView Calculator filter wrapper for derived array expressions.

    Category: ParaView filter.
    Tags: paraview, calculator, expression, cell-data, point-data.
    Use when: to add a calculated field to a ParaView
        processing pipeline.
    """

    filter_type: str = "Calculator"
    counter: int = 0

    def __init__(self, input_filter, function, name, output_array_name=None, attribute_type='Cell Data'):
        """Create and configure a ParaView Calculator proxy.

        Category: ParaView filter.
        Tags: paraview, calculator, initialization, expression.
        Use when: adding a derived array calculation to an existing pipeline.
        Args:
            input_filter: Upstream ParaView proxy used as calculator input.
            function: Calculator expression string.
            name: Logical filter name passed to the base filter wrapper.
            output_array_name: Optional name for the result array.
            attribute_type: Target association, usually ``"Cell Data"`` or
                ``"Point Data"``.
        Side effects:
            Creates a ParaView ``Calculator`` proxy and sets function,
            attribute type, and optional result-array name.
        """
        super().__init__(name=name)
        CalculatorFilter.counter += 1
        self.filter = Calculator(Input=input_filter)
        self.filter.Function = function
        self.filter.AttributeType = attribute_type
        if output_array_name:
            self.filter.ResultArrayName = output_array_name

    def set_attribute_type(self, attribute_type):
        """Set the Calculator attribute association.

        Category: ParaView filter.
        Tags: paraview, calculator, cell-data, point-data.
        Use when: switching whether the expression acts on cell or point data.
        Args:
            attribute_type: ParaView attribute type string.
        Side effects:
            Mutates ``self.filter.AttributeType``.
        """
        self.filter.AttributeType = attribute_type

    def set_function(self, function):
        """Set the Calculator expression.

        Category: ParaView filter.
        Tags: paraview, calculator, expression.
        Use when: changing the derived array formula after filter creation.
        Args:
            function: ParaView Calculator expression string.
        Side effects:
            Mutates ``self.filter.Function``.
        """
        self.filter.Function = function

    @property
    def calculation(self):
        """Return the calculated result array from cell or point data.

        Category: ParaView filter.
        Tags: paraview, calculator, result-array.
        Use when: retrieving the output of a Calculator expression from the
            wrapper's data dictionaries.
        Returns:
            Array selected by ``self.filter.ResultArrayName`` from cell or point
            data depending on ``AttributeType``.
        """
        if self.filter.AttributeType == "Cell Data":
            return self.cell_data[self.filter.ResultArrayName]
        if self.filter.AttributeType == "Point Data":
            return self.point_data[self.filter.ResultArrayName]
