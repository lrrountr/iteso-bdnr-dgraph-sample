#!/usr/bin/env python3
"""
Social Network CLI — Dgraph graph database client.

Admin (run once):
  setup   — apply graph schema (types and predicates)
  seed    — load demo persons, schools and relationships from CSV
  drop    — drop all data and schema

Graph operations:
  add-person   — add a person node
  add-school   — add a school node
  befriend     — add a friendship edge between two persons
  enroll       — add a person-to-school attendance edge
  persons      — list all persons
  search       — search for a person (shows friends and schools)
  delete       — delete a person by name
  schools      — list all schools
"""
import argparse
import os
import sys

import requests
from tabulate import tabulate

API_URL = os.getenv('API_URL', 'http://localhost:8001')


def _err(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _get(path, timeout=30):
    try:
        return requests.get(f"{API_URL}{path}", timeout=timeout)
    except requests.exceptions.ConnectionError:
        _err(f"Cannot connect to API at {API_URL}")


def _post(path, body=None, timeout=120):
    try:
        return requests.post(f"{API_URL}{path}", json=body, timeout=timeout)
    except requests.exceptions.ConnectionError:
        _err(f"Cannot connect to API at {API_URL}")


def _delete(path, timeout=30):
    try:
        return requests.delete(f"{API_URL}{path}", timeout=timeout)
    except requests.exceptions.ConnectionError:
        _err(f"Cannot connect to API at {API_URL}")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

def cmd_status():
    r = _get('/health')
    if r.ok:
        d = r.json()
        print(f"API:      {d.get('status')}")
        print(f"Database: {d.get('database')}")
    else:
        _err(f"HTTP {r.status_code}")


def cmd_setup():
    """Apply the graph schema — types and predicates only, no data."""
    r = _post('/setup')
    if not r.ok:
        _err(f"Setup failed: {r.text}")

    d = r.json()
    print(f"OK: {d['message']}\n")
    print("Types:      " + ', '.join(d.get('types', [])))
    print("\nPredicates:")
    for p in d.get('predicates', []):
        print(f"  {p}")


def cmd_seed():
    """Load demo data from CSV files using real business operations."""
    print("Loading demo data from CSV files …")
    r = _post('/seed', timeout=300)
    if not r.ok:
        _err(f"Seed failed: {r.text}")

    d = r.json()
    s = d.get('summary', {})
    print(f"OK: data loaded\n")
    persons = s.get('persons', {})
    schools = s.get('schools', {})
    attended = s.get('attended', {})
    friends = s.get('friendships', {})
    print(f"  Persons:     {persons.get('created', 0)} created, {persons.get('skipped', 0)} skipped")
    print(f"  Schools:     {schools.get('created', 0)} created, {schools.get('skipped', 0)} skipped")
    if attended:
        print(f"  Attendance:  {attended.get('processed', 0)} relationships")
    if friends:
        print(f"  Friendships: {friends.get('processed', 0)} relationships")


def cmd_drop():
    confirm = input("Drop ALL data and schema? This cannot be undone. Type 'yes' to confirm: ")
    if confirm.strip().lower() != 'yes':
        print("Aborted.")
        return
    r = _post('/drop')
    if r.ok:
        print("OK: all data and schema dropped")
    else:
        _err(f"Drop failed: {r.text}")


# ---------------------------------------------------------------------------
# Graph operations
# ---------------------------------------------------------------------------

def cmd_add_person(username, name, married=None, dob=None, lat=None, lon=None):
    """Add a person node to the graph."""
    body = {'username': username, 'name': name}
    if married is not None:
        body['married'] = married
    if dob:
        body['dob'] = dob
    if lat is not None:
        body['lat'] = lat
    if lon is not None:
        body['lon'] = lon

    r = _post('/persons', body)
    if not r.ok:
        _err(f"Failed: {r.json().get('error', r.text)}")

    d = r.json()
    print(f"Person added!\n  UID:      {d['uid']}\n  Username: {d['username']}\n  Name:     {d['name']}")


def cmd_add_school(name):
    """Add a school node to the graph."""
    r = _post('/schools', {'name': name})
    if not r.ok:
        _err(f"Failed: {r.json().get('error', r.text)}")

    d = r.json()
    print(f"School added!\n  UID:  {d['uid']}\n  Name: {d['name']}")


def cmd_befriend(person, friend, since=None, close=None):
    """
    Add a friendship edge between two persons.
    The @reverse directive makes it queryable from both sides automatically.
    """
    body = {'friend_username': friend}
    if since:
        body['since'] = since
    if close is not None:
        body['close'] = close

    r = _post(f'/persons/{person}/friends', body)
    if not r.ok:
        _err(f"Failed: {r.json().get('error', r.text)}")

    d = r.json()
    print(f"OK: {d['message']}")
    print(f"Note: {d.get('note', '')}")


def cmd_enroll(person, school, year_start=None, year_end=None, degree=None):
    """Add a person-to-school attendance edge."""
    body = {'school_name': school}
    if year_start is not None:
        body['year_start'] = year_start
    if year_end is not None:
        body['year_end'] = year_end
    if degree:
        body['degree'] = degree

    r = _post(f'/persons/{person}/schools', body)
    if not r.ok:
        _err(f"Failed: {r.json().get('error', r.text)}")

    print(f"OK: {r.json()['message']}")


def cmd_persons():
    r = _get('/persons')
    if not r.ok:
        _err(f"Failed: {r.text}")

    persons = r.json().get('persons', [])
    if not persons:
        print("No persons found.")
        return

    table = [
        [
            p.get('uid', ''),
            p.get('username', ''),
            p.get('name', ''),
            'Yes' if p.get('married') else 'No',
            (p.get('dob') or '')[:10],
        ]
        for p in persons
    ]
    print(tabulate(table, headers=['UID', 'Username', 'Name', 'Married', 'DOB'], tablefmt='github'))
    print(f"\n{len(persons)} person(s)")


def cmd_search(name):
    r = _get(f'/persons/{name}')
    if not r.ok:
        if r.status_code == 404:
            print(f"No person found with name '{name}'")
            return
        _err(f"Failed: {r.text}")

    for person in r.json().get('persons', []):
        print(f"\n{'='*50}")
        print(f"UID:      {person.get('uid')}")
        print(f"Username: {person.get('username')}")
        print(f"Name:     {person.get('name')}")
        print(f"Married:  {'Yes' if person.get('married') else 'No'}")
        print(f"DOB:      {(person.get('dob') or 'N/A')[:10]}")

        loc = person.get('location')
        if loc and 'coordinates' in loc:
            c = loc['coordinates']
            print(f"Location: {c[1]:.4f}, {c[0]:.4f}  (lat, lon)")

        friends = person.get('friend', [])
        if friends:
            print(f"\nFriends ({len(friends)}):")
            for f in friends:
                since = f.get('friend|since', '')
                close = f.get('friend|close')
                facets = ', '.join(filter(None, [
                    f"since {since}" if since else '',
                    'close friend' if close else '',
                ]))
                suffix = f"  [{facets}]" if facets else ''
                print(f"  - {f.get('name')} ({f.get('username')}){suffix}")

        schools = person.get('attended', [])
        if schools:
            print(f"\nSchools ({len(schools)}):")
            for s in schools:
                year_start = s.get('attended|year_start', '')
                year_end   = s.get('attended|year_end', '')
                degree     = s.get('attended|degree', '')
                parts = ', '.join(filter(None, [
                    f"{year_start}–{year_end}" if year_start or year_end else '',
                    degree,
                ]))
                suffix = f"  [{parts}]" if parts else ''
                print(f"  - {s.get('name')}{suffix}")

    print(f"\n{'='*50}")


def cmd_delete(name):
    r = _delete(f'/persons/{name}')
    if not r.ok:
        if r.status_code == 404:
            print(f"No person found with name '{name}'")
            return
        _err(f"Failed: {r.text}")
    print(f"OK: {r.json().get('message')}")


def cmd_schools():
    r = _get('/schools')
    if not r.ok:
        _err(f"Failed: {r.text}")

    schools = r.json().get('schools', [])
    if not schools:
        print("No schools found.")
        return

    table = [[s.get('uid', ''), s.get('name', '')] for s in schools]
    print(tabulate(table, headers=['UID', 'Name'], tablefmt='github'))
    print(f"\n{len(schools)} school(s)")


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Social Network CLI — Dgraph graph database client',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Admin (run once):
  python cli.py setup
  python cli.py seed

Build the graph:
  python cli.py add-person --username alice --name "Alice"
  python cli.py add-school --name "ITESO"
  python cli.py befriend --person alice --friend bob
  python cli.py enroll   --person alice --school "ITESO"

Explore:
  python cli.py persons
  python cli.py search --name Alice
  python cli.py schools

Cleanup:
  python cli.py delete --name Alice
  python cli.py drop
        """
    )
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('status', help='Check API health')
    sub.add_parser('setup',  help='Apply graph schema (types + predicates, no data)')
    sub.add_parser('seed',   help='Load demo data from CSV files')
    sub.add_parser('drop',   help='Drop all data and schema (with confirmation)')

    p = sub.add_parser('add-person', help='Add a person node')
    p.add_argument('--username', '-u', required=True)
    p.add_argument('--name',     '-n', required=True)
    p.add_argument('--married',  action='store_true', default=None)
    p.add_argument('--dob',      help='Date of birth YYYY-MM-DD')
    p.add_argument('--lat',      type=float)
    p.add_argument('--lon',      type=float)

    p = sub.add_parser('add-school', help='Add a school node')
    p.add_argument('--name', '-n', required=True)

    p = sub.add_parser('befriend', help='Add a friendship edge (bidirectional via @reverse)')
    p.add_argument('--person', required=True, help='Username of first person')
    p.add_argument('--friend', required=True, help='Username of second person')
    p.add_argument('--since',  help='Date the friendship started (YYYY-MM-DD)')
    p.add_argument('--close',  action='store_true', default=None, help='Mark as a close friendship')

    p = sub.add_parser('enroll', help='Add a person-to-school attendance edge')
    p.add_argument('--person',      required=True, help='Person username')
    p.add_argument('--school',      required=True, help='School name')
    p.add_argument('--year-start',  type=int, dest='year_start', help='Year enrollment started')
    p.add_argument('--year-end',    type=int, dest='year_end',   help='Year enrollment ended')
    p.add_argument('--degree',      help='Degree or program name')

    sub.add_parser('persons', help='List all persons')

    p = sub.add_parser('search', help='Search for a person (shows friends and schools)')
    p.add_argument('--name', '-n', required=True)

    p = sub.add_parser('delete', help='Delete a person by name')
    p.add_argument('--name', '-n', required=True)

    sub.add_parser('schools', help='List all schools')

    args = parser.parse_args()

    if   args.command == 'status':     cmd_status()
    elif args.command == 'setup':      cmd_setup()
    elif args.command == 'seed':       cmd_seed()
    elif args.command == 'drop':       cmd_drop()
    elif args.command == 'add-person': cmd_add_person(args.username, args.name,
                                                       args.married, args.dob,
                                                       args.lat, args.lon)
    elif args.command == 'add-school': cmd_add_school(args.name)
    elif args.command == 'befriend':   cmd_befriend(args.person, args.friend, args.since, args.close)
    elif args.command == 'enroll':     cmd_enroll(args.person, args.school, args.year_start, args.year_end, args.degree)
    elif args.command == 'persons':    cmd_persons()
    elif args.command == 'search':     cmd_search(args.name)
    elif args.command == 'delete':     cmd_delete(args.name)
    elif args.command == 'schools':    cmd_schools()


if __name__ == '__main__':
    main()
