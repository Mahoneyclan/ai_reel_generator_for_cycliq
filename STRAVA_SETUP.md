# Strava Integration Setup Guide

Complete guide to setting up Strava GPX import for Velo Films AI.

---

## 🎯 Overview

The Strava integration allows you to:
- ✅ Authenticate with your Strava account (OAuth 2.0)
- ✅ Browse recent cycling activities
- ✅ Search activities by date
- ✅ Download GPX directly into project folders
- ✅ Automatic token refresh (no re-login needed)

**Security:** Tokens stored locally in `~/.velo_films/strava_tokens.json` with 600 permissions.

---

## 📋 Prerequisites

1. **Strava Account** - Free or paid
2. **Python packages** - Install with:
   ```bash
   pip install requests
   ```

---

## 🔧 Setup Steps

### 1. Create Strava API Application

1. **Go to Strava API Settings:**
   - Visit: https://www.strava.com/settings/api
   - Log in with your Strava account

2. **Create Application:**
   - Click **"Create App"** or **"My API Application"**
   - Fill in details:
     - **Application Name:** `Velo Films AI` (or your choice)
     - **Category:** `Data Importer`
     - **Club:** Leave blank
     - **Website:** `http://localhost:8888` (for development)
     - **Authorization Callback Domain:** `localhost`
     - **Application Description:** `Automated cycling highlight reel generator`
     - **Icon:** Upload logo (optional)

3. **Save Application**

4. **Copy Credentials:**
   - You'll see:
     - **Client ID:** `12345` (example)
     - **Client Secret:** `abcdef123456...` (long string)
   - **⚠️ Keep these secret!** Don't commit to git.

### 2. Configure Velo Films

Edit `source/strava/strava_config.py`:

```python
class StravaConfig:
    # ...existing code...
    
    # REPLACE THESE with your credentials:
    CLIENT_ID = "12345"  # Your actual Client ID
    CLIENT_SECRET = "abcdef123456789..."  # Your actual Client Secret
    REDIRECT_URI = "http://localhost:8888/callback"  # Keep as-is
```

**⚠️ Security Best Practice:**

Never commit credentials to git. Instead, use environment variables:

```python
import os

class StravaConfig:
    CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "YOUR_CLIENT_ID")
    CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
```

Then set in your shell:
```bash
export STRAVA_CLIENT_ID="12345"
export STRAVA_CLIENT_SECRET="abcdef123456..."
```

### 3. Test Connection

1. **Launch Velo Films:**
   ```bash
   python main.py
   ```

2. **Select a Project** (or create new one)

3. **Click "Get Strava GPX"**

4. **Authorize:**
   - Browser opens to Strava
   - Click **"Authorize"**
   - Browser shows success message
   - Dialog shows "✓ Connected to Strava"

5. **Browse Activities:**
   - Recent 30 activities load automatically
   - Or search by date

6. **Download GPX:**
   - Select activity
   - Click **"Download GPX"**
   - File saved as `ride.gpx` in project folder

---

## 🔐 How OAuth Works

### Flow Diagram

```
┌─────────────┐                 ┌──────────────┐                ┌─────────────┐
│  Velo Films │                 │   Browser    │                │   Strava    │
└──────┬──────┘                 └──────┬───────┘                └──────┬──────┘
       │                               │                               │
       │ 1. Generate PKCE challenge    │                               │
       │───────────────────────────────>                               │
       │                               │                               │
       │ 2. Open auth URL              │                               │
       │───────────────────────────────>                               │
       │                               │                               │
       │                               │ 3. User clicks "Authorize"    │
       │                               │──────────────────────────────>│
       │                               │                               │
       │                               │ 4. Redirect with auth code    │
       │                               │<──────────────────────────────│
       │                               │                               │
       │ 5. Receive auth code          │                               │
       │<───────────────────────────────                               │
       │                               │                               │
       │ 6. Exchange code for token                                    │
       │──────────────────────────────────────────────────────────────>│
       │                               │                               │
       │ 7. Return access + refresh tokens                             │
       │<──────────────────────────────────────────────────────────────│
       │                               │                               │
       │ 8. Save tokens locally        │                               │
       │──────────────────┐            │                               │
       │                  │            │                               │
       │<─────────────────┘            │                               │
```

### Security Features

1. **PKCE (Proof Key for Code Exchange)**
   - Prevents authorization code interception
   - Required for public clients (desktop apps)

2. **Token Storage**
   - Stored in: `~/.velo_films/strava_tokens.json`
   - File permissions: `600` (user read/write only)
   - Never transmitted over network

3. **Automatic Refresh**
   - Access tokens expire after 6 hours
   - Refresh token valid for 60 days
   - Auto-refreshes before expiration

4. **Local Callback Server**
   - Starts on `localhost:8888`
   - Only accepts connections from localhost
   - Shuts down after receiving callback

---

## 📊 Usage Examples

### Import Recent Ride

```python
from source.strava import StravaClient

# Connect
client = StravaClient()
if client.connect():
    # Get recent activities
    activities = client.get_recent_activities(limit=10)
    
    # Download first activity's GPX
    if activities:
        activity_id = activities[0]["id"]
        client.download_gpx(activity_id, Path("ride.gpx"))
```

### Search by Date

```python
from datetime import datetime

# Search for rides on specific date
activities = client.search_activities_by_date(
    datetime(2024, 12, 6)
)

for activity in activities:
    print(client.format_activity_summary(activity))
```

---

## 🐛 Troubleshooting

### "Failed to authenticate"

**Cause:** Invalid credentials or network issue

**Solution:**
1. Double-check `CLIENT_ID` and `CLIENT_SECRET`
2. Verify Strava app status at https://www.strava.com/settings/api
3. Check internet connection
4. Try clearing tokens: `rm ~/.velo_films/strava_tokens.json`

### "Authorization callback failed"

**Cause:** Redirect URI mismatch

**Solution:**
1. Ensure Strava app has `localhost` in callback domain
2. Check `REDIRECT_URI` matches: `http://localhost:8888/callback`
3. Port 8888 not in use by another app

### "Port 8888 already in use"

**Cause:** Another app using port 8888

**Solution:**
1. Close other apps
2. Or change port in `strava_config.py`:
   ```python
   REDIRECT_URI = "http://localhost:9999/callback"
   ```
   And update `strava_auth.py` line 98:
   ```python
   port = 9999  # Match REDIRECT_URI
   ```

### "Token expired"

**Cause:** Refresh token expired (>60 days old)

**Solution:**
- Re-authenticate (automatic prompt)
- App will open browser for new authorization

### "No activities found"

**Cause:** Wrong date range or no cycling activities

**Solution:**
1. Check date selection
2. Verify activities exist on Strava
3. Try "Show Recent" instead of date search

---

## 🔒 Privacy & Data

### What Data is Accessed?

- **Read-only access** to your activities
- Activity metadata (date, name, distance, time)
- GPX track data (GPS coordinates, elevation)

**NOT accessed:**
- Private notes
- Training data (power, heart rate zones)
- Photos
- Other athletes' data

### What Data is Stored?

**Locally on your Mac:**
- OAuth tokens (encrypted by filesystem)
- GPX files you download

**Never stored:**
- Strava password
- Activity photos
- Private training metrics

### Revoking Access

To disconnect Velo Films from Strava:

1. **In Velo Films:**
   - Delete: `~/.velo_films/strava_tokens.json`

2. **On Strava:**
   - Go to: https://www.strava.com/settings/apps
   - Find "Velo Films AI"
   - Click **"Revoke Access"**

---

## 🚀 Advanced Usage

### Custom Scopes

Need more data? Edit `strava_config.py`:

```python
SCOPES = [
    "read",
    "activity:read",
    "activity:read_all",  # Include private activities
]
```

Available scopes:
- `read` - Read public profile
- `activity:read` - Read public activities
- `activity:read_all` - Read all activities (inc. private)
- `activity:write` - Upload activities (not needed)

### Batch Download

Download multiple GPX files:

```python
from pathlib import Path

client = StravaClient()
client.connect()

activities = client.get_recent_activities(limit=10)

for activity in activities:
    name = activity["name"].replace(" ", "_")
    output = Path(f"gpx_exports/{name}.gpx")
    client.download_gpx(activity["id"], output)
```

### Activity Filtering

Filter by type, distance, etc:

```python
activities = client.get_recent_activities(limit=50)

# Only long rides
long_rides = [
    a for a in activities 
    if a["distance"] > 50000  # 50+ km
]

# Only races
races = [
    a for a in activities
    if "race" in a["name"].lower()
]
```

---

## 📚 API Reference

### StravaClient Methods

```python
client = StravaClient()

# Authentication
client.connect() -> bool

# Activities
client.get_recent_activities(limit=30) -> List[Dict]
client.search_activities_by_date(date, end_date=None) -> List[Dict]
client.get_activity_details(activity_id) -> Dict

# GPX Download
client.download_gpx(activity_id, output_path) -> bool

# Utilities
client.format_activity_summary(activity) -> str
client.disconnect()
```

### Activity Dict Structure

```python
{
    "id": 123456789,
    "name": "Morning Ride",
    "type": "Ride",  # or "VirtualRide"
    "distance": 25300.0,  # meters
    "moving_time": 4980,  # seconds
    "elapsed_time": 5400,
    "total_elevation_gain": 350.0,  # meters
    "start_date": "2024-12-06T08:30:00Z",
    "start_latlng": [45.5236, -122.6750],
    "average_speed": 5.08,  # m/s
    "max_speed": 12.5,
    "has_heartrate": true,
    "map": {
        "summary_polyline": "..."  # Encoded polyline
    }
}
```

---

## 🔄 Token Lifecycle

```
┌──────────────────────────────────────────────────────────┐
│                    First Connection                      │
│  1. User authorizes in browser                          │
│  2. Velo Films receives tokens                          │
│  3. Tokens saved to ~/.velo_films/strava_tokens.json   │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│              Subsequent Connections (< 6hrs)             │
│  1. Load tokens from disk                               │
│  2. Use access_token for API calls                      │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│             Token Expired (> 6hrs, < 60 days)           │
│  1. Use refresh_token to get new access_token          │
│  2. Save updated tokens                                 │
│  3. Continue with new access_token                      │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│           Refresh Token Expired (> 60 days)             │
│  1. Prompt user to re-authorize                         │
│  2. Restart OAuth flow                                  │
└──────────────────────────────────────────────────────────┘
```

---

## 📝 Notes

- **Rate Limits:** Strava allows 100 requests per 15 minutes, 1000 per day
- **GPX Quality:** Same as manual export (full resolution GPS track)
- **Virtual Rides:** Supported (Zwift, TrainerRoad, etc.)
- **Private Activities:** Requires `activity:read_all` scope

---

## 🆘 Support

**Issues:**
- GitHub: https://github.com/yourusername/velo_films_ai/issues
- Tag with `strava-integration`

**Strava API Docs:**
- https://developers.strava.com/docs/reference/

**OAuth 2.0 Spec:**
- https://oauth.net/2/pkce/