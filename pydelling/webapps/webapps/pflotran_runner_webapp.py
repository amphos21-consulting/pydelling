"""This webapp allows to run PFLOTRAN simulations on JURECA and visualize the evolution"""

from pydelling.webapps import WebAppRunner
import streamlit as st

class PflotranRunnerWebapp(WebAppRunner):
    """Placeholder Streamlit app for PFLOTRAN runner UI experiments.

    Category: Web application.
    Tags: streamlit, pflotran, runner, prototype.
    Use when: to identify the current PFLOTRAN runner webapp
        prototype and understand that it does not yet launch simulations.
    """

    def construct(self):
        """Render the current PFLOTRAN runner placeholder content.

        Category: Web application.
        Tags: streamlit, pflotran, prototype, text-area.
        Use when: smoke-testing that the PFLOTRAN runner webapp route renders.
        Side effects:
            Writes a disabled text area to the Streamlit page.
        """
        txt = st.text_area('Text to analyze', '''
             It was the best of times, it was the worst of times, it was
             the age of wisdom, it was the age of foolishness, it was
             the epoch of belief, it was the epoch of incredulity, it
             was the season of Light, it was the season of Darkness, it
             was the spring of hope, it was the winter of despair, (...)
             ''', height=1000, disabled=True)


if __name__ == '__main__':
    webapp = PflotranRunnerWebapp()
    webapp.run()
