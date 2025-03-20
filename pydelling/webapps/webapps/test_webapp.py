import streamlit as st

from pydelling.webapps.web_app_runer import WebAppRunner


class TestWebApp(WebAppRunner):
    def construct(self):
        st.header("Test WebApp")


if __name__ == '__main__':
    test_webapp = TestWebApp()
    test_webapp.run()
