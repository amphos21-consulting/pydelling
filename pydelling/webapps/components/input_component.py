"""
Creates a streamlit block in which the user can drag and drop a file and the resulting object is returned


"""

from pathlib import Path

import pandas as pd
import streamlit as st
from translate import Translator

from pydelling.config import config
from pydelling.readers import VTKMeshReader, FemReader, SmeshReader
from pydelling.webapps import WebAppRunner
from pydelling.webapps.components import BaseComponent


class InputComponent(BaseComponent):
    """Streamlit upload component for tabular and mesh-like pydelling inputs.

    Category: Web application component.
    Tags: streamlit, upload, csv, vtk, fem, smesh, session-state.
    Use when: to identify which UI component turns uploaded
        files into pandas data frames or pydelling reader objects.
    """

    def __init__(self, input_type: str, key: str, webapp: WebAppRunner=None, lang=None, *args, **kwargs):
        """Configure an upload component and its Streamlit state keys.

        Category: Web application component.
        Tags: streamlit, upload, state, initialization.
        Use when: constructing a file input widget for a pydelling webapp.
        Args:
            input_type: Input handler to render. Supported values are ``"csv"``,
                ``"vtk"``, ``"fem"``, and ``"smesh"``.
            key: Base Streamlit session-state key used for the resulting object
                and for the ``"{key}_done"`` completion flag.
            webapp: Optional owning ``WebAppRunner``.
            lang: Optional language selector retained for compatibility.
            *args: Positional arguments forwarded to ``BaseComponent``.
            **kwargs: Keyword arguments forwarded to ``BaseComponent``.
        Side effects:
            Initializes ``st.session_state[f"{key}_done"]`` when missing.
        """
        self.key = key
        if not f'{self.key}_done' in st.session_state:
            st.session_state[f'{self.key}_done'] = False
        self.translate = False
        self.input_type = input_type


        super().__init__(webapp=webapp, *args, **kwargs)


    def run(self):
        """Render the configured upload form.

        Category: Web application component.
        Tags: streamlit, upload, dispatch.
        Use when: a webapp needs to render the upload workflow selected by
            ``input_type``.
        Side effects:
            Delegates to the matching ``run_*_input`` method and may populate
            Streamlit session state.
        """
        if self.input_type == 'csv':
            self.run_csv_input()
        elif self.input_type == 'vtk':
            self.run_vtk_input()
        elif self.input_type == 'fem':
            self.run_fem_input()
        elif self.input_type == 'smesh':
            self.run_smesh_input()

    def run_csv_input(self):
        """Render a CSV upload form and store a pandas data frame.

        Category: Web application component.
        Tags: streamlit, upload, csv, pandas, session-state.
        Use when: an MCP-assisted UI workflow needs tabular interpolation data
            loaded through Streamlit.
        Side effects:
            On submit, reads the uploaded CSV with the selected delimiter,
            stores the data frame in ``self._value`` and ``st.session_state`` at
            ``self.key``, and sets ``f"{self.key}_done"`` to ``True``.
        """
        with st.form(f"{self.key}_form"):
            st.write("Drop your input data (the data that contains the information to interpolate) in the box below")
            data = st.file_uploader("Upload your data", type=config.globals.webapp.supported_input_data)
            st.markdown('**Advanced upload options:**')
            cols = st.columns([1, 6, 6])
            with cols[0]:
                sep = st.text_input('Separator', ',')
            whitespace_delimiter = st.checkbox('Whitespace delimiter', value=False)
            # Every form must have a submit button.
            submitted = st.form_submit_button("Upload")
            if submitted:
                with(st.spinner(f'Loading data')):
                    if whitespace_delimiter:
                        read_data = pd.read_csv(data, delim_whitespace=whitespace_delimiter)
                    else:
                        read_data = pd.read_csv(data, sep=sep)
                    st.dataframe(read_data.head())
                    self._value = read_data
                    st.session_state[f'{self.key}_done'] = True
                    if not self.key in st.session_state:
                        st.session_state[f'{self.key}'] = read_data


    def run_vtk_input(self):
        """Render a VTK upload form and store a ``VTKMeshReader``.

        Category: Web application component.
        Tags: streamlit, upload, vtk, mesh-reader, session-state.
        Use when: a webapp needs uploaded VTK mesh or centroid data available as
            a pydelling reader object.
        Side effects:
            Writes the upload to ``temp.vtk``, constructs ``VTKMeshReader`` with
            ``st_file=True``, deletes the temporary file, stores the reader in
            ``st.session_state[self.key]``, and marks the input as done.
        """
        desc = "Drop your mesh/centroid data (the mesh/location you want to interpolate into) in the box below"
        format_desc = 'This data must be in VTK format'
        upload_desc = 'Upload your data'
        upload_button = 'Upload'
        if self.translate:
            desc = self.translator.translate(desc)
            format_desc = self.translator.translate(format_desc)
            upload_desc = self.translator.translate(upload_desc)
            upload_button = self.translator.translate(upload_button)

        with st.form(f'{self.key}_form'):
            st.write(desc)
            st.markdown(format_desc)
            data = st.file_uploader(upload_desc, type='vtk')
            new_submit = st.form_submit_button(upload_button)
            if new_submit:
                # Write file to temp directory
                with open('temp.vtk', 'wb') as f:
                    f.write(data.getbuffer())
                vtk_mesh = VTKMeshReader('temp.vtk', st_file=True)
                Path('temp.vtk').unlink()
                st.session_state[f'{self.key}'] = vtk_mesh
                st.session_state[f'{self.key}_done'] = True


    def run_fem_input(self):
        """Render a FEM upload form and store a ``FemReader``.

        Category: Web application component.
        Tags: streamlit, upload, fem, mesh-reader, session-state.
        Use when: a webapp needs FEM ASCII mesh or centroid data available as a
            pydelling reader object.
        Side effects:
            Writes the upload to ``temp.fem``, constructs ``FemReader`` with
            ``st_file=True``, deletes the temporary file, stores the reader in
            ``st.session_state[self.key]``, and marks the input as done.
        """
        desc = "Drop your mesh/centroid data (the mesh/location you want to interpolate into) in the box below"
        format_desc = 'This data must be in FEM ASCII format'
        upload_desc = 'Upload your data'
        upload_button = 'Upload'
        if self.translate:
            desc = self.translator.translate(desc)
            format_desc = self.translator.translate(format_desc)
            upload_desc = self.translator.translate(upload_desc)
            upload_button = self.translator.translate(upload_button)

        with st.form(f'{self.key}_form'):
            st.write(desc)
            st.markdown(format_desc)
            data = st.file_uploader(upload_desc, type='fem')
            new_submit = st.form_submit_button(upload_button)
            if new_submit:
                # Write file to temp directory
                with open('temp.fem', 'wb') as f:
                    f.write(data.getbuffer())
                vtk_mesh = FemReader('temp.fem', st_file=True)
                Path('temp.fem').unlink()
                st.session_state[f'{self.key}'] = vtk_mesh
                st.session_state[f'{self.key}_done'] = True


    def run_smesh_input(self):
        """Render an SMesh upload form and store a ``SmeshReader``.

        Category: Web application component.
        Tags: streamlit, upload, smesh, mesh-reader, session-state.
        Use when: a webapp needs SMesh ASCII mesh or centroid data available as
            a pydelling reader object.
        Side effects:
            Writes the upload to ``temp.smesh``, constructs ``SmeshReader`` with
            ``st_file=True``, deletes the temporary file, stores the reader in
            ``st.session_state[self.key]``, and marks the input as done.
        """
        desc = "Drop your mesh/centroid data (the mesh/location you want to interpolate into) in the box below"
        format_desc = 'This data must be in SMesh ASCII format'
        upload_desc = 'Upload your data'
        upload_button = 'Upload'
        if self.translate:
            desc = self.translator.translate(desc)
            format_desc = self.translator.translate(format_desc)
            upload_desc = self.translator.translate(upload_desc)
            upload_button = self.translator.translate(upload_button)
        with st.form(f'{self.key}_form'):
            st.write(desc)
            st.markdown(format_desc)
            data = st.file_uploader(upload_desc, type='smesh')
            new_submit = st.form_submit_button(upload_button)
            if new_submit:
                # Write file to temp directory
                with open('temp.smesh', 'wb') as f:
                    f.write(data.getbuffer())
                vtk_mesh = SmeshReader('temp.smesh', st_file=True)
                Path('temp.smesh').unlink()
                st.session_state[f'{self.key}'] = vtk_mesh
                st.session_state[f'{self.key}_done'] = True
