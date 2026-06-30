"""
Module documentation.


"""


class Scalar:
    """Simple scalar geometry value wrapper.

    Category: geometry primitive.
    Tags: scalar, value, geometry.
    Usage: to recognize scalar primitive wrappers used by
        pydelling geometry utilities.
    """

    def __init__(self, value=0.0):
        """
        __init__ method.
        
        Args:
            value (Any): Description.
        """
        self.value = value

    def __repr__(self):
        return f"Scalar({self.value})"

    def __str__(self):
        return f"Scalar({self.value})"
