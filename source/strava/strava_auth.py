# source/strava/strava_auth.py
from __future__ import annotations

"""
Strava OAuth 2.0 authentication with PKCE.
Implements secure browser-based login flow.
"""

import secrets
import hashlib
import base64
import webbrowser
from urllib.parse import urlencode, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import requests
from typing import Optional, Callable

from .strava_config import StravaConfig

from ..utils.log import setup_logger

log = setup_logger("strava.auth")

class StravaAuth:
    """Handles Strava OAuth 2.0 authentication with PKCE."""
    
    def __init__(self, config: StravaConfig, log_callback: Optional[Callable[[str, str], None]] = None):
        """
        Args:
            config: StravaConfig instance
            log_callback: Optional callback function(message, level) for logging
        """
        self.config = config
        self.auth_code = None
        self.auth_error = None
        self.log = log_callback or self._default_log
    
    def _default_log(self, message: str, level: str = "info"):
        """Default logging to console if no callback provided."""
        print(f"[strava_auth] {message}")
    
    def authenticate(self) -> bool:
        """
        Run OAuth flow to get access token.
        
        Returns:
            True if authentication successful
        """
        # Check if we have valid saved tokens
        saved_tokens = self.config.load_tokens()
        if saved_tokens:
            # Check if token is still valid
            if not self.config.is_token_expired(saved_tokens["expires_at"]):
                log.info("[strava_auth] Using cached valid token")
                return True
            
            # Try to refresh expired token
            log.info("[strava_auth] Token expired, attempting refresh...")
            if self._refresh_token(saved_tokens["refresh_token"]):
                return True
            
            log.warning("[strava_auth] Token refresh failed, starting new auth flow")
        
        # Start fresh OAuth flow
        return self._start_oauth_flow()
    
    def _start_oauth_flow(self) -> bool:
        """
        Start OAuth 2.0 flow with PKCE.
        
        Returns:
            True if successful
        """
        log.info("[strava_auth] Starting OAuth flow...")
        
        # Generate PKCE code verifier and challenge
        code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(code_verifier)
        state = secrets.token_urlsafe(32)
        
        # Build authorization URL
        auth_params = {
            "client_id": self.config.CLIENT_ID,
            "redirect_uri": self.config.REDIRECT_URI,
            "response_type": "code",
            "scope": ",".join(self.config.SCOPES),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "approval_prompt": "auto",
        }
        
        auth_url = f"{self.config.AUTHORIZE_URL}?{urlencode(auth_params)}"
        
        # Start local callback server
        server = self._start_callback_server()
        
        # Open browser for user authorization
        log.info("[strava_auth] Opening browser for authorization...")
        webbrowser.open(auth_url)
        
        # Wait for callback (blocks until user authorizes or timeout)
        server.handle_request()
        
        # Check if we got the authorization code
        if not self.auth_code:
            error_msg = self.auth_error or "Authorization cancelled by user"
            log.error(f"[strava_auth] {error_msg}")
            return False
        
        # Exchange authorization code for access token
        return self._exchange_code_for_token(self.auth_code, code_verifier)
    
    def _start_callback_server(self) -> HTTPServer:
        """
        Start local HTTP server to receive OAuth callback.
        
        Returns:
            HTTPServer instance
        """
        # Parse port from redirect URI
        port = 8888  # Default from REDIRECT_URI
        
        # Create handler that captures auth response
        parent = self
        
        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                # Parse query parameters
                query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                
                if "code" in query:
                    parent.auth_code = query["code"][0]
                    response = b"<html><body><h1>Success!</h1><p>Authorization successful. You can close this window.</p></body></html>"
                    self.send_response(200)
                elif "error" in query:
                    parent.auth_error = query["error"][0]
                    response = b"<html><body><h1>Error</h1><p>Authorization failed. Check the app.</p></body></html>"
                    self.send_response(400)
                else:
                    response = b"<html><body><h1>Invalid Request</h1></body></html>"
                    self.send_response(400)
                
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(response)
            
            def log_message(self, format, *args):
                # Suppress server logs
                pass
        
        server = HTTPServer(("localhost", port), CallbackHandler)
        log.debug(f"[strava_auth] Callback server listening on port {port}")
        return server
    
    def _exchange_code_for_token(self, auth_code: str, code_verifier: str) -> bool:
        """
        Exchange authorization code for access token.
        
        Args:
            auth_code: Authorization code from callback
            code_verifier: PKCE code verifier
            
        Returns:
            True if successful
        """
        log.info("[strava_auth] Exchanging code for access token...")
        
        try:
            response = requests.post(
                self.config.TOKEN_URL,
                data={
                    "client_id": self.config.CLIENT_ID,
                    "client_secret": self.config.CLIENT_SECRET,
                    "code": auth_code,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                }
            )
            
            response.raise_for_status()
            token_data = response.json()
            
            # Save tokens
            self.config.save_tokens(token_data)
            
            log.info("[strava_auth] ✓ Authentication successful")
            return True
            
        except requests.RequestException as e:
            log.error(f"[strava_auth] Token exchange failed: {e}")
            return False
    
    def _refresh_token(self, refresh_token: str) -> bool:
        """
        Refresh expired access token.
        
        Args:
            refresh_token: Refresh token from previous auth
            
        Returns:
            True if successful
        """
        log.info("[strava_auth] Refreshing access token...")
        
        try:
            response = requests.post(
                self.config.TOKEN_URL,
                data={
                    "client_id": self.config.CLIENT_ID,
                    "client_secret": self.config.CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                }
            )
            
            response.raise_for_status()
            token_data = response.json()
            
            # Save refreshed tokens
            self.config.save_tokens(token_data)
            
            log.info("[strava_auth] ✓ Token refreshed successfully")
            return True
            
        except requests.RequestException as e:
            log.error(f"[strava_auth] Token refresh failed: {e}")
            return False
    
    @staticmethod
    def _generate_code_verifier() -> str:
        """Generate PKCE code verifier (random 43-128 char string)."""
        return secrets.token_urlsafe(64)
    
    @staticmethod
    def _generate_code_challenge(verifier: str) -> str:
        """Generate PKCE code challenge from verifier."""
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        return challenge