"""
Module documentation.


"""

from pydelling.webapps.components import BaseComponent
import streamlit as st
import time
import paramiko
import extra_streamlit_components as stx


@st.cache(allow_output_mutation=True)
def get_manager():
    return stx.CookieManager()

manager = get_manager()

class RemoteLoginComponent(BaseComponent):
    """Streamlit component for collecting and storing remote SSH login data.

    Category: Web application component.
    Tags: streamlit, ssh, login, cookies, session-state.
    Use when: an MCP agent needs to understand the UI flow that stores remote
        host credentials for pydelling webapp sessions.
    """

    def __int__(self,
                host: str,
                host_name: str = None,
                username: str = None,
                password: str = None,
                login_node: bool = False,
                *args,
                **kwargs
                ):
        """Configure remote login state for a Streamlit component.

        Category: Web application component.
        Tags: streamlit, ssh, login, initialization.
        Use when: constructing the remote-login component and initializing the
            session-state keys it depends on.
        Args:
            host: Remote host address.
            host_name: Display name and cookie namespace for the host. Defaults
                to ``host``.
            username: Optional initial username.
            password: Optional initial password.
            login_node: Whether the component should render an interactive login
                form.
            *args: Positional arguments forwarded to ``BaseComponent``.
            **kwargs: Keyword arguments forwarded to ``BaseComponent``.
        Side effects:
            Initializes Streamlit session-state keys and creates a cookie
            manager reference.
        Notes:
            The method name is currently ``__int__`` in the implementation, so
            Python will not treat it as a constructor unless called explicitly.
        """
        self.initialize_in_session_state('host')
        self.initialize_in_session_state('host_name')
        self.initialize_in_session_state('username')
        self.initialize_in_session_state('cwd')
        self.initialize_in_session_state('password')
        self.host = host
        self.host_name = host_name if host_name is not None else host
        self.client: paramiko.SSHClient
        self.username = username
        self.password = password
        self.login_node = login_node
        self.cookie_manager = self.get_manager()
        super().__init__(host=host,
                         host_name=host_name,
                         username=username,
                         password=password,
                         login_node=login_node,
                         *args,
                         **kwargs,
                         )

    def run(self, login_node=True, *args, **kwargs):
        """Render the login form or prepare an SSH client.

        Category: Web application component.
        Tags: streamlit, ssh, login, form.
        Use when: a Streamlit page needs to collect remote credentials and mark
            the component initialized.
        Args:
            login_node: Whether to show the login form while the component is
                not initialized.
            *args: Accepted for component API compatibility.
            **kwargs: Accepted for component API compatibility.
        Side effects:
            Renders Streamlit inputs, may submit login credentials, or prepares a
            Paramiko ``SSHClient`` with missing-host-key policy.
        """
        if not self.get_from_session_state(f'{self.name}-init') and login_node:
            with st.form(key='login_form'):
                st.markdown(f'Login form for {self.host_name} ({self.host})')
                col1, col2 = st.columns(2)
                with col1:
                    self.username = st.text_input('Username')
                    cwd = st.text_input('Working directory')
                    submitted = st.form_submit_button('Log in')
                with col2:
                    self.password = st.text_input('Password', type='password')
                if submitted:
                    self.login_submit_func(username=self.username, cwd=cwd, password=self.password)
                    st.experimental_rerun()
        else:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # Just run the component logic

    # @st.experimental_memo
    def login_submit_func(self, username, cwd, password):
        # Log in to system and be sure it works
        # self = _self
        """Handle submitted credentials and persist login state.

        Category: Web application component.
        Tags: streamlit, ssh, login, cookies, session-state.
        Use when: the login form has been submitted and the component should
            verify SSH access and store credentials for the session.
        Args:
            username: Remote SSH username.
            cwd: Remote working directory entered by the user.
            password: Remote SSH password.
        Side effects:
            Connects with Paramiko, writes Streamlit session-state values, stores
            an auth dictionary in the cookie manager, and marks login as
            initialized.
        """
        with st.spinner('Logging in...'):
            self.cookie_manager: stx.CookieManager = self.get_manager()
            self.save_in_session_state(f'host', self.host)
            self.save_in_session_state(f'host_name', self.host_name)
            self.save_in_session_state(f'username', username)
            self.save_in_session_state(f'password', self.password)
            self.save_in_session_state(f'cwd', cwd)

            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(self.host, username=username, password=password)
            st.success(f'You are logged in to {self.host}')
            auth_dict = {
                'host': self.host,
                'host_name': self.host_name,
                'username': username,
                'password': password,
                'cwd': cwd,
            }
            get_manager().set(f'{self.host_name}-auth', auth_dict)
            time.sleep(0.3)
            self.save_in_session_state('is_login', True)
            self.save_in_session_state(f'{self.name}-init', True)

    def check_connection(self):
        # Check if the connection is still alive
        """Open a test SSH connection with the stored credentials.

        Category: Web application component.
        Tags: ssh, connection-check, paramiko.
        Use when: a Streamlit workflow needs to verify that the stored remote
            login details still authenticate.
        Returns:
            bool: ``True`` after Paramiko connects successfully.
        Side effects:
            Recreates ``self.client`` and opens an SSH connection.
        """
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(self.host,
                            username=self.username,
                            password=self.password,
                            )
        return True


