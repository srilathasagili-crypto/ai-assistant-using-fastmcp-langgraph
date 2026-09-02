import streamlit as st
from google_auth_oauthlib.flow import Flow

from graph.config import get_env_var


GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]


def get_google_client_config():
    """
    Build Google OAuth client configuration
    from Streamlit Secrets.
    """

    client_id = get_env_var(
        "GOOGLE_CLIENT_ID",
        required=True,
    )

    client_secret = get_env_var(
        "GOOGLE_CLIENT_SECRET",
        required=True,
    )

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def get_redirect_uri():
    """
    Redirect URI must exactly match the URI configured
    in Google Cloud Console.
    """

    return (
        "https://ai-assistant-using-fastmcp-langgraph-"
        "xjbjapsc3ti3m23urjcboa.streamlit.app"
    )


def create_oauth_flow():
    """
    Create a Google OAuth flow.
    """

    client_config = get_google_client_config()

    flow = Flow.from_client_config(
        client_config,
        scopes=GMAIL_SCOPES,
    )

    flow.redirect_uri = get_redirect_uri()

    return flow


def get_authorization_url():
    """
    Generate the Google authorization URL.
    """

    flow = create_oauth_flow()

    authorization_url, state = (
        flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
    )

    st.session_state["gmail_oauth_state"] = state

    return authorization_url


def handle_oauth_callback():
    """
    Handle the authorization response after
    Google redirects the user back to Streamlit.
    """

    params = st.query_params

    code = params.get("code")

    if not code:
        return False

    state = st.session_state.get(
        "gmail_oauth_state"
    )

    if not state:
        st.error(
            "Gmail OAuth session expired. "
            "Please click Connect Gmail again."
        )

        return False

    try:

        flow = create_oauth_flow()

        flow.fetch_token(
            code=code
        )

        credentials = flow.credentials

        st.session_state["gmail_credentials"] = credentials

        # Clean OAuth query parameters
        st.query_params.clear()

        st.success(
            "Gmail connected successfully!"
        )

        return True

    except Exception as e:

        st.error(
            f"Could not connect Gmail: {e}"
        )

        return False


def render_gmail_connection():
    """
    Display Gmail connection controls in the sidebar.
    """

    st.sidebar.markdown("### 📧 Gmail")

    credentials = st.session_state.get(
        "gmail_credentials"
    )

    if credentials:

        st.sidebar.success(
            "Gmail connected"
        )

        if st.sidebar.button(
            "🔌 Disconnect Gmail"
        ):
            st.session_state.pop(
                "gmail_credentials",
                None,
            )

            st.session_state.pop(
                "gmail_oauth_state",
                None,
            )

            st.rerun()

    else:

        authorization_url = (
            get_authorization_url()
        )

        st.sidebar.link_button(
            "🔗 Connect Gmail",
            authorization_url,
            use_container_width=True,
        )
