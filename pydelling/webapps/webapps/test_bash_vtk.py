from pydelling.webapps.web_app_runer import WebAppRunner


class TestWebApp(WebAppRunner):
    """Streamlit/PyVista smoke app for embedded VTK visualization.

    Category: Web application.
    Tags: streamlit, pyvista, vtk, test-webapp, visualization.
    Use when: an MCP agent needs to identify the test app that exports a PyVista
        scene and embeds it in Streamlit.
    """

    def construct(self):
        """Render a sample PyVista uniform grid as embedded HTML.

        Category: Web application.
        Tags: streamlit, pyvista, vtk, html, visualization.
        Use when: smoke-testing PyVista HTML export and Streamlit component
            embedding.
        Side effects:
            Writes ``pyvista.html`` and embeds the generated HTML in the page.
        """
        import streamlit.components.v1 as components
        import pyvista
        from pyvista import examples
        mesh = examples.load_uniform()
        pl = pyvista.Plotter(shape=(1, 2))
        _ = pl.add_mesh(mesh, scalars='Spatial Point Data', show_edges=True)
        pl.subplot(0, 1)
        _ = pl.add_mesh(mesh, scalars='Spatial Cell Data', show_edges=True)
        pl.export_html('pyvista.html')  # doctest:+SKIP

        HtmlFile = open("pyvista.html", 'r', encoding='utf-8')
        source_code = HtmlFile.read()
        components.html(source_code, height=500, width=500)



if __name__ == '__main__':
    test_webapp = TestWebApp()
    test_webapp.run()
