"""Small Supabase Auth helpers used by the Streamlit dashboard."""
from __future__ import annotations

import os

from supabase import Client, create_client


def auth_settings() -> tuple[str, str] | None:
    """Read the public Supabase project URL and anon key from secrets/env."""
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_ANON_KEY", "")
    except Exception:
        url, key = "", ""
    url = url or os.getenv("SUPABASE_URL", "")
    key = key or os.getenv("SUPABASE_ANON_KEY", "")
    return (url, key) if url and key else None


def make_client(url: str, anon_key: str) -> Client:
    # Each Streamlit browser session owns its own client; do not cache a client
    # whose mutable Auth session could otherwise be shared between viewers.
    return create_client(url, anon_key)


def current_user(client: Client, access_token: str, refresh_token: str = ""):
    """Validate a saved token and refresh it when an app session has expired."""
    if not access_token:
        return None
    try:
        return client.auth.get_user(access_token).user
    except Exception:
        if not refresh_token:
            return None
    try:
        refreshed = client.auth.refresh_session(refresh_token)
        import streamlit as st
        st.session_state["auth_access_token"] = refreshed.session.access_token
        st.session_state["auth_refresh_token"] = refreshed.session.refresh_token
        return refreshed.user
    except Exception:
        return None

