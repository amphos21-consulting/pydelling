"""
This class creates an OpenFOAM variable data file


"""

import logging

import numpy as np

from pydelling.config import config
from .base_writer import BaseWriter

logger = logging.getLogger(__name__)


class OpenFoamVariableWriter(BaseWriter):
    """Write OpenFOAM field variable files from arrays and config metadata.

    Category: OpenFOAM writer.
    Tags: openfoam, variable, field-file, boundary-field, export.
    Use when: an MCP agent needs to create an OpenFOAM scalar field file from
        computed pydelling values.
    """

    def __init__(self, filename: str = None, header: dict | None = None, outer: dict | None = None, data: np.ndarray | list | None = None, configuration_dict=None, *args, **kwargs):
        """Configure output path, OpenFOAM header metadata, and field values.

        Category: OpenFOAM writer.
        Tags: openfoam, initialization, header, boundary-field, data.
        Use when: preparing a writer from explicit arguments or from the
            ``open_foam_variable_writer`` configuration block.

        A correct set of header/outer needs to be provided to the class.

        It can be automatically used from the config file by creating an instance called "open_foam_variable_writer" for the settings.

        Args:
            filename: Name of the output file.
            header: Object or dictionary-like config containing FoamFile fields.
            outer: Object or dictionary-like config containing boundary fields.
            data: Scalar array or list to write into the OpenFOAM file.
            configuration_dict: Optional config object with ``header``,
                ``outer``, and ``filename`` attributes.
            *args: Positional arguments forwarded to ``BaseWriter``.
            **kwargs: Keyword arguments forwarded to ``BaseWriter``.
        """
        if configuration_dict:
            self.header = configuration_dict.header
            self.outer = configuration_dict.outer
            self.filename = configuration_dict.filename
        else:
            self.header = header if header else config.open_foam_variable_writer.header
            self.outer = outer if outer else config.open_foam_variable_writer.outer
            self.filename = filename if filename else config.open_foam_variable_writer.filename
        self.data = data
        super().__init__(filename=self.filename, *args, **kwargs)

    def run(self, *args, **kwargs):
        """Write the configured OpenFOAM variable file.

        Category: OpenFOAM writer.
        Tags: openfoam, field-file, export, run.
        Use when: exporting computed scalar values to a complete OpenFOAM field
            file.
        Args:
            *args: Accepted for writer API compatibility.
            **kwargs: Accepted for writer API compatibility.
        Side effects:
            Opens ``self.filename`` for writing and emits header, data, and
            boundary-field sections.
        """
        logger.info(f"Writing data to {self.filename}")
        with open(self.filename, "w") as self.output_file:
            self.write_header()
            self.write_data()
            self.write_outer()

    def write_header(self):
        """Write the OpenFOAM FoamFile and internalField header.

        Category: OpenFOAM writer.
        Tags: openfoam, header, FoamFile, internalField.
        Use when: composing the leading metadata section of an OpenFOAM field
            file.
        Side effects:
            Writes to ``self.output_file``.
        """
        self.output_file.write(f"""/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
    \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
     \\\\    /   O peration     | Website:  https://openfoam.org
        \\\\  /    A nd           | Version:  7
         \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {self.header.field_type};
    location    "{self.header.location}";
    object      {self.header.object};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      {self.header.dimensions};
internalField   {self.header.data_type} {self.header.data_structure}\n""")

    def write_data(self):
        """Write scalar internal-field values.

        Category: OpenFOAM writer.
        Tags: openfoam, data, scalar-field, internalField.
        Use when: appending the data block for an OpenFOAM scalar variable file.
        Raises:
            ValueError: If a data element is neither a scalar float nor a vector
                with a fourth scalar value.
        Side effects:
            Writes the parenthesized data block to ``self.output_file``.
        """
        self.output_file.write(f"{len(self.data)}\n")
        self.output_file.write("(\n")
        for data_element in self.data:
            if type(data_element) == np.float64 or type(data_element) == np.float32:
                self.output_file.write(f"{data_element}\n")
            elif len(data_element) == 4:
                self.output_file.write(f"{data_element[3]}\n")
            else:
                logger.error("There is an error provided the data element vector")
                raise ValueError("There was an error providing the data element")

        self.output_file.write(")\n")
        self.output_file.write(";\n")

    def write_outer(self):
        """Write the OpenFOAM ``boundaryField`` section.

        Category: OpenFOAM writer.
        Tags: openfoam, boundary-field, footer.
        Use when: completing an OpenFOAM field file with configured boundary
            condition types.
        Side effects:
            Writes boundary-field entries and the OpenFOAM footer marker.
        """
        self.output_file.write(f"""boundaryField\n{{\n""")
        for region in self.outer.boundary_fields:
            region_dict = self.outer.boundary_fields[region]
            self.output_file.write(f"""\t{region}\n\t{{\n\t\ttype\t{region_dict["type"]};\n\t}}\n""")
        self.output_file.write("}\n")
        self.output_file.write("\n")
        self.output_file.write("// ************************************************************************* //")
