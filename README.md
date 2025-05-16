# YouTuBoxd - YouTube Saved Videos Sync Platform

A full-stack web application where users can log in with their Google account using OAuth 2.0, and the app automatically fetches their "Watch Later" YouTube videos. Users can tag each video or add custom descriptions.

## Features

- Google OAuth 2.0 authentication
- Automatic sync of "Watch Later" YouTube playlist
- Tag and add descriptions to videos
- Secure token management and automatic refresh

## Setup Instructions

### Prerequisites

- Python 3.8+
- Google Developer account

### Step 1: Set up Google OAuth Credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Go to "APIs & Services" > "Credentials"
4. Create OAuth 2.0 Client ID
5. Set the authorized redirect URI to `http://localhost:8000/oauth/callback/`
6. Enable the YouTube Data API v3

### Step 2: Environment Setup

1. Clone this repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Copy the `.env.example` file to `.env` and update it with your credentials:
```
# Django Secret Key
SECRET_KEY=your-secret-key-here

# Google OAuth Settings
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/oauth/callback/

# Debug Settings
DEBUG=True
```

### Step 3: Database Setup

1. Apply migrations:
```
python manage.py migrate
```

### Step 4: Run the Application

1. Start the development server:
```
python manage.py runserver
```
2. Access the application at `http://localhost:8000`

## Usage

1. Log in with your Google account
2. Your "Watch Later" YouTube videos will automatically sync
3. Add tags and descriptions to videos
4. Refresh the page to update with the latest saved videos from YouTube 

## Pushing to GitHub

When pushing this project to GitHub, make sure to:

1. Never commit your `.env` file - it contains sensitive credentials
2. The `.gitignore` file already excludes the `.env` file
3. Make sure new contributors copy the `.env.example` file to `.env` and add their own credentials
4. If you add new environment variables, update the `.env.example` file without including actual secret values 