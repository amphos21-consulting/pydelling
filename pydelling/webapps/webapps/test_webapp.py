import streamlit as st

from pydelling.webapps.web_app_runer import WebAppRunner


class TestWebApp(WebAppRunner):
    """Minimal Streamlit webapp used to verify the webapp runner path.

    Category: Web application.
    Tags: streamlit, test-webapp, runner, smoke-test.
    Use when: an MCP agent needs to identify the simplest pydelling webapp
        implementation and its render hook.
    """

    def construct(self):
        """Render a basic Streamlit header.

        Category: Web application.
        Tags: streamlit, test-webapp, construct.
        Use when: smoke-testing that ``WebAppRunner`` can render a concrete
            subclass.
        Side effects:
            Writes a header to the Streamlit page.
        """
        st.header("Test WebApp")


if __name__ == '__main__':
    test_webapp = TestWebApp()
    test_webapp.run()
