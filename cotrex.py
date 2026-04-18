#!/usr/bin/env python3

# Copyright 2026 Stephen Warren <swarren@wwwdotorg.org>
# SPDX-License-Identifier: MIT

import argparse
import glob
import json
import os
import requests
import sys
import time

api_key = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJhay1jamxieXB6Z2UwMDAwcTdjZzNkcXltazNhIiwiY29fYXBwIjoxLCJpYXQiOjE1MzUzNTQ5OTR9.iD306sLvoEW7ZPDT6OvcHKiPiygkakMPctFKIy-PmIA'
token_url = 'https://trails.colorado.gov/api/v1/oauth/token?api_key={api_key}'
trips_url = 'https://trails.colorado.gov/api/v1/users/{username}/trips?page=1&per_page=10'

def unlink(fn):
    try:
        os.remove(fn)
    except FileNotFoundError:
        pass

def load_creds():
    global creds
    if not os.path.exists(creds_filename):
        print(f'ERROR: credentials file {creds_filename} does not exist', file=sys.stderr)
        sys.exit(1)
    with open(creds_filename, 'r') as f:
        try:
            creds = json.load(f)
        except json.JSONDecodeError as e:
            print(f'ERROR: failed to parse credentials file as JSON: {e}', file=sys.stderr)
            sys.exit(1)

def save_creds():
    creds_dir = os.path.dirname(creds_filename)
    os.makedirs(creds_dir, exist_ok=True)
    with open(creds_filename, 'w') as f:
        json.dump(creds, f)

def cotrex_login(username, password):
    global creds
    payload = {
        'grant_type': 'password',
        'username': username,
        'password': password,
    }
    url = token_url.format(api_key=api_key)
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        print(f'ERROR: failed to authenticate: {response.status_code} {response.text}', file=sys.stderr)
        sys.exit(1)
    auth = response.json()
    creds = {
        'username': username,
        'access_token': auth['access_token'],
        'refresh_token': auth['refresh_token'],
        'expires_at': auth['expires_in'] + int(time.time()),
    }
    save_creds()

def cotrex_refresh_creds():
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': creds['refresh_token'],
    }
    url = token_url.format(api_key=api_key)
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        print(f'ERROR: failed to refresh token: {response.status_code} {response.text}', file=sys.stderr)
        sys.exit(1)
    auth = response.json()
    creds['access_token'] = auth['access_token']
    creds['refresh_token'] = auth['refresh_token']
    creds['expires_at'] = auth['expires_in'] + int(time.time())
    save_creds()

def cotrex_refresh_creds_if_needed():
    if creds['expires_at'] - int(time.time()) >= 60:
        return creds
    cotrex_refresh_creds()

def cotrex_stream_file(url, filename):
    cotrex_refresh_creds_if_needed()
    response = requests.get(url + f'&access_token={creds['access_token']}', stream=True)
    if response.status_code != 200:
        fn = os.path.basename(filename)
        print(f'ERROR: failed to stream file {fn}: {response.status_code} {response.text}', file=sys.stderr)
        sys.exit(1)
    try:
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=4096):
                f.write(chunk)
    except:
        unlink(filename)
        raise

def cmd_login(args):
    """Authenticate and obtain access token"""
    username = args.username or os.environ.get('COTREX_USERNAME')
    if not username:
        print('ERROR: username not provided and COTREX_USERNAME not set', file=sys.stderr)
        sys.exit(1)
    password = args.password or os.environ.get('COTREX_PASSWORD')
    if not password:
        print('ERROR: password not provided and COTREX_PASSWORD not set', file=sys.stderr)
        sys.exit(1)
    cotrex_login(username, password)

def cmd_refresh(args):
    """Refresh the access token"""
    load_creds()
    cotrex_refresh_creds()

def cmd_logout(args):
    """Logout and delete credentials"""
    # https://trails.colorado.gov/logout just clears the client-side cookie,
    # but doesn't invalidate either the access token or the refresh token.
    unlink(args.creds_filename)

def cmd_sync(args):
    """Sync trips from cotrex.org"""
    load_creds()

    # Delete existing trips-*.json files in the destination directory
    trips_pattern = os.path.join(args.directory, 'trips-page*.json')
    for trips_file in glob.glob(trips_pattern):
        unlink(trips_file)

    trips = []
    page_num = 1
    page_count = '?'
    page_url =  trips_url.format(username=creds.get('username'), page=page_num)
    while page_url is not None:
        print(f'Sync trips list page {page_num} of {page_count}')
        trips_fn = os.path.join(args.directory, f'trips-page{page_num}.json')
        cotrex_stream_file(page_url, trips_fn)
        with open(trips_fn, 'rb') as f:
            trips_page = json.load(f)
        trips.extend(trips_page.get('results', []))
        page_num += 1
        page_count = trips_page.get('meta', {}).get('pages', '?')
        page_url = trips_page.get('meta', {}).get('next_url', None)

    # Other download forms:
    # https://trails.colorado.gov/api/v1/trips/52160?include=trip.user,trip.associations,trip.object_tags
    # https://trails.colorado.gov/api/v1/trips/52160/extract.json?download=1
    # https://trails.colorado.gov/api/v1/trips/52160/extract.gpx?download=1

    trip_count = len(trips)
    for trip_num0, trip in enumerate(trips):
        trip_num = trip_num0 + 1
        trip_id = trip.get('id')
        print(f'Fetching trip {trip_num} of {trip_count} (id={trip_id})')
        gpx_url = f'https://trails.colorado.gov/api/v1/trips/{trip_id}/extract.gpx?download=1'
        trip_fn = os.path.join(args.directory, f'trip-{trip_id}.gpx')
        if os.path.exists(trip_fn):
            print('... already synced')
        else:
            cotrex_stream_file(gpx_url, trip_fn)
            print('... done')
        trip_num += 1

def main():
    parser = argparse.ArgumentParser(description='cotrex.org sync tool')
    parser.add_argument('-c', '--creds-filename',
        default=os.path.expanduser('~/.config/cotrex-sync/creds.txt'),
        help='Credentials file path')
    
    subparsers = parser.add_subparsers(dest='command',
        help='Command to execute')
    
    # Login command with username and password arguments
    login_parser = subparsers.add_parser('login',
        help='Authenticate and obtain access token')
    login_parser.add_argument('username', nargs='?',
        help='Username for authentication')
    login_parser.add_argument('password', nargs='?',
        help='Password for authentication')
    login_parser.set_defaults(func=cmd_login)
    
    # Refresh command
    refresh_parser = subparsers.add_parser('refresh',
        help='Refresh the access token')
    refresh_parser.set_defaults(func=cmd_refresh)

    # Logout command
    logout_parser = subparsers.add_parser('logout',
        help='Logout and delete credentials')
    logout_parser.set_defaults(func=cmd_logout)

    # Sync command
    sync_parser = subparsers.add_parser('sync',
        help='Sync trips from cotrex.org')
    sync_parser.add_argument('directory', nargs='?',
        default='.',
        help='Directory to save synced files')
    sync_parser.set_defaults(func=cmd_sync)
    
    args = parser.parse_args()
    global creds_filename
    creds_filename = args.creds_filename

    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)

if __name__ == '__main__':
    main()
