"""
Module documentation.


"""

import streamlit as st
import extra_streamlit_components as stx

class BaseStreamlitUtilityClass:
    """Shared Streamlit session-state helpers for pydelling web utilities.

    Category: Web application utility.
    Tags: streamlit, session-state, cookie-manager, ui-state.
    Use when: an MCP agent needs to identify the common helper API used by
        Streamlit components to persist values across reruns.
    """

    def save_in_session_state(self, key, value: object):
        """Store a value directly in ``st.session_state`` under ``key``.

        Category: Web application utility.
        Tags: streamlit, session-state, state-write.
        Use when: a component needs to persist a computed object, uploaded
            reader, or UI setting for later Streamlit reruns.
        Args:
            key: Session-state key to write.
            value: Python object to store under that key.
        Side effects:
            Mutates ``st.session_state``.
        """
        st.session_state[key] = value

    def initialize_in_session_state(self, key: str, value: object=None):
        """Create a session-state value only when it is not already present.

        Category: Web application utility.
        Tags: streamlit, session-state, default-value.
        Use when: a component must define a stable default without overwriting
            user-provided state from a previous rerun.
        Args:
            key: Session-state key to initialize.
            value: Default object to assign when the key is missing.
        Side effects:
            Mutates ``st.session_state`` only for missing keys.
        """
        if key not in st.session_state:
            st.session_state[key] = value

    def get_from_session_state(self, key: str):
        """Return a value from ``st.session_state``.

        Category: Web application utility.
        Tags: streamlit, session-state, state-read.
        Use when: a Streamlit component or MCP tool needs the current value
            stored by an earlier UI action.
        Args:
            key: Session-state key to retrieve.
        Returns:
            The object stored under ``key``.
        """
        return st.session_state[key]

    def initialize(self):
        """Hook for subclasses that need one-time Streamlit setup.

        Category: Web application utility.
        Tags: streamlit, lifecycle, extension-point.
        Use when: documenting or implementing a web utility subclass that needs
            to prepare state before rendering controls.
        """
        pass

    def set_to_session_state(self, key: str, value: object):
        """Alias for :meth:`save_in_session_state`.

        Category: Web application utility.
        Tags: streamlit, session-state, state-write, compatibility.
        Use when: legacy component code uses the older setter name but should
            still be understood as a direct session-state write.
        Args:
            key: Session-state key to write.
            value: Python object to store under that key.
        Side effects:
            Mutates ``st.session_state`` through ``save_in_session_state``.
        """
        self.save_in_session_state(key, value)

    @staticmethod
    @st.cache(allow_output_mutation=True, suppress_st_warning=True)
    def get_manager():
        """Return a cached extra-streamlit-components cookie manager.

        Category: Web application utility.
        Tags: streamlit, cookies, cache, session.
        Use when: a Streamlit view needs persistent browser-cookie access
            without recreating the manager on every rerun.
        Returns:
            ``extra_streamlit_components.CookieManager`` instance cached by
            Streamlit.
        """
        return stx.CookieManager()
