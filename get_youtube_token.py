"""Run ONCE per channel on your own laptop (not Railway) to get that channel's refresh token.

    pip install google-auth-oauthlib
    python get_youtube_token.py client_secret.json

A browser opens: sign in, then CHOOSE THE CHANNEL (brand account) this token is for.
Copy the printed refresh token into Railway as YT_REFRESH_TOKEN_A or YT_REFRESH_TOKEN_B.
"""
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

if __name__ == "__main__":
    secret = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
    flow = InstalledAppFlow.from_client_secrets_file(secret, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    print("\nREFRESH TOKEN (keep it secret):\n")
    print(creds.refresh_token)
    print("\nClient ID:", creds.client_id)
