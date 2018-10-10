import sys
import os
from enum import Enum

import spotipy
import spotipy.util as util
from spotipy.oauth2 import SpotifyOAuth

from flask import Flask, request, redirect, g, render_template, url_for, session
from flask_session import Session

# Playlist counts
LIMIT_SHORT = 20
LIMIT_MEDIUM = 50
LIMIT_LONG = 100

# Spotify API variables
CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID', None)
CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET', None)
REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI', None)
SCOPE = 'user-library-read user-read-recently-played user-top-read ' \
        'playlist-modify-private playlist-read-private ' \
        'playlist-read-collaborative user-read-private user-read-birthdate ' \
        'user-read-email'

sp_oauth = SpotifyOAuth(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, scope=SCOPE)
auth_url = sp_oauth.get_authorize_url()


# Flask setup
PORT = os.getenv('SPOTIPY_PORT', 8888)
SESSION_TYPE = 'filesystem'

app = Flask(__name__)
app.config.from_object(__name__)
Session(app)


@app.route("/")
def index():
    return 'My Spotipy App!'


@app.route("/signin")
def signin():
    return redirect(auth_url)


@app.route("/callback")
def callback():
    try:
        url = request.url
        code = sp_oauth.parse_response_code(url)
        token_info = sp_oauth.get_access_token(code)
        token = token_info['access_token']
        print(token)
        spotify = SpotipyApp(token)
        message = spotify.create_top_track_playlists()
        session['message'] = message
        return redirect(url_for('results'))
    except:
        session['message'] = 'Please sign in!'
        return redirect(url_for('results'))


@app.route("/results")
def results():
    message = session.get('message', '')
    session.pop('message', None)
    return message


class Timeframe(Enum):
    '''
    The 3 options spotify gives over API for top tracks result time frame.
    Tuple values are time frame name, spotify API term length, song limit, description

    '''
    short = ('Short', 'short_term', LIMIT_SHORT,
             'Top {} Songs from last ~4 weeks.'.format(LIMIT_SHORT))
    medium = ('Medium', 'medium_term', LIMIT_MEDIUM,
              'Top {} Songs from last ~6 months.'.format(LIMIT_MEDIUM))
    long = ('Long', 'long_term', LIMIT_LONG,
            'Top {} Songs dating back a few years.'.format(LIMIT_LONG))


class Playlist():
    def __init__(self, track_list, track_list_text, name, description):
        self.track_list = track_list
        self.track_list_text = track_list_text
        self.name = name
        self.description = description


class SpotipyApp():
    def __init__(self, token):
        self.sp = spotipy.Spotify(auth=token)
        self.username = self.sp.current_user()['id']

    def get_top_tracks(self):
        # returns dictionary with Enum as key, tuple as value ( list, header, body )
        top_tracks = []
        for timeframe in Timeframe:
            name = timeframe.value[0]
            time_range = timeframe.value[1]
            limit = timeframe.value[2]

            results = self.sp.current_user_top_tracks(
                limit=limit, time_range=time_range)

            playlist_name = '{} - Top {}'.format(name, limit)
            playlist_description = timeframe.value[3] + '  Created over API.'

            top_tracks_text = ''
            top_tracks_list = []
            for item in results['items']:
                artist = item['artists'][0]['name']
                track = item['name']
                uri = item['uri']
                top_tracks_list.append(uri)
                top_tracks_text += '\n\t' + uri + \
                    ' - ' + artist + ' - ' + track[:50]

            playlist = Playlist(
                top_tracks_list, top_tracks_text, playlist_name, playlist_description)

            top_tracks.append(playlist)

        return top_tracks

    def get_existing_playlists(self, limit=50):
        playlists = {}
        results = self.sp.user_playlists(self.username, limit=limit)
        for item in results['items']:
            name = item['name']
            _id = item['id']
            playlists.update({name: _id})
        return playlists

    def create_playlist(self, playlist):
        playlist_name = playlist.name
        playlist_description = playlist.description
        tracks = playlist.track_list

        if playlist_name in self.existing_playlists:
            self.sp.user_playlist_replace_tracks(
                self.username, self.existing_playlists[playlist_name], tracks)
        else:
            new_playlist = self.sp.user_playlist_create(user=self.username,
                                                        name=playlist_name,
                                                        public=False,
                                                        description=playlist_description)
            self.sp.user_playlist_add_tracks(
                self.username, new_playlist['id'], tracks)

    def generate_playlist_message(self, playlists):
        # Simple output of tracks updated into playlists
        title = 'Updating playlists for ' + self.username
        message = title + '\nThe following playlists were created!'

        for playlist in playlists:
            message = message + '\n' + playlist.name + playlist.track_list_text

        message = message.replace('\n', '<br>')
        message = message.replace('\t', '&nbsp;&nbsp;&nbsp;&nbsp;')

        return message

    def create_top_track_playlists(self):
        # Returns list of playlist objects containing top tracks for each Spotify Time Frame
        playlists = self.get_top_tracks()

        # Gets current playlists for the user, so we can either create new or
        # update track list
        self.existing_playlists = self.get_existing_playlists()

        for playlist in playlists:
            self.create_playlist(playlist)

        # Generate html output of all updates made
        message = self.generate_playlist_message(playlists)

        return str(message)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=PORT)
