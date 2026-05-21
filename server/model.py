#!/usr/bin/env python3
"""
Dgraph data model and operations.
"""
import csv
import datetime
import json
import logging
import os

import pydgraph

log = logging.getLogger(__name__)

# Data directory path (configurable via env var)
DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data'))


class DgraphConnection:
    """Manages Dgraph client connection."""

    def __init__(self, host='localhost', port=9080):
        self.host = host
        self.port = port
        self.stub = None
        self.client = None

    def connect(self):
        """Connect to Dgraph."""
        addr = f"{self.host}:{self.port}"
        log.info(f"Connecting to Dgraph at {addr}")
        self.stub = pydgraph.DgraphClientStub(addr)
        self.client = pydgraph.DgraphClient(self.stub)
        return True

    def close(self):
        """Close Dgraph connection."""
        if self.stub:
            self.stub.close()

    def is_connected(self):
        """Check if connected."""
        return self.client is not None


def create_person(client, username, name, married=None, dob=None, lat=None, lon=None):
    """
    Create a new person node in the graph.
    Returns the assigned UID.
    """
    username = username.strip().lower()

    existing = _get_existing_person_uid_by_username(client, username)
    if existing:
        raise ValueError(f"Person with username '{username}' already exists (uid: {existing})")

    node = {'dgraph.type': 'Person', 'username': username, 'name': name.strip()}
    if married is not None:
        node['married'] = bool(married)
    if dob:
        node['dob'] = dob
    if lat is not None and lon is not None:
        node['location'] = {'type': 'Point', 'coordinates': [float(lon), float(lat)]}

    txn = client.txn()
    try:
        resp = txn.mutate(set_obj=node, commit_now=True)
        uid = list(resp.uids.values())[0] if resp.uids else None
        log.info(f"Person created: {username} (uid: {uid})")
        return uid
    finally:
        txn.discard()


def create_school(client, name):
    """
    Create a new school node in the graph.
    Returns the assigned UID.
    """
    existing = _get_existing_school_uid(client, name)
    if existing:
        raise ValueError(f"School '{name}' already exists (uid: {existing})")

    node = {
        'dgraph.type': 'School',
        'name': name.strip(),
        'name_lower': name.strip().lower(),
    }
    txn = client.txn()
    try:
        resp = txn.mutate(set_obj=node, commit_now=True)
        uid = list(resp.uids.values())[0] if resp.uids else None
        log.info(f"School created: {name} (uid: {uid})")
        return uid
    finally:
        txn.discard()


def add_friendship(client, person_username, friend_username):
    """
    Add a friendship edge between two persons.
    The @reverse directive on 'friend' makes this bidirectional automatically.
    """
    person_uid = _get_existing_person_uid_by_username(client, person_username)
    if not person_uid:
        raise ValueError(f"Person '{person_username}' not found")

    friend_uid = _get_existing_person_uid_by_username(client, friend_username)
    if not friend_uid:
        raise ValueError(f"Person '{friend_username}' not found")

    txn = client.txn()
    try:
        txn.mutate(set_obj={'uid': person_uid, 'friend': [{'uid': friend_uid}]}, commit_now=True)
        log.info(f"Friendship added: {person_username} ↔ {friend_username}")
    finally:
        txn.discard()


def add_attendance(client, person_username, school_name):
    """
    Add an attendance edge from a person to a school.
    The @reverse directive on 'attended' makes it queryable from the school side too.
    """
    person_uid = _get_existing_person_uid_by_username(client, person_username)
    if not person_uid:
        raise ValueError(f"Person '{person_username}' not found")

    school_uid = _get_existing_school_uid(client, school_name)
    if not school_uid:
        raise ValueError(f"School '{school_name}' not found")

    txn = client.txn()
    try:
        txn.mutate(set_obj={'uid': person_uid, 'attended': [{'uid': school_uid}]}, commit_now=True)
        log.info(f"Attendance added: {person_username} → {school_name}")
    finally:
        txn.discard()


def seed_data(client):
    """Load all sample data from CSV files using real business operations."""
    persons_csv = os.path.join(DATA_DIR, 'persons.csv')
    schools_csv = os.path.join(DATA_DIR, 'schools.csv')
    attended_csv = os.path.join(DATA_DIR, 'attended.csv')
    friendships_csv = os.path.join(DATA_DIR, 'friendships.csv')

    return ingest_multi_csv(
        client,
        persons_path=persons_csv,
        schools_path=schools_csv,
        attended_path=attended_csv,
        friendships_path=friendships_csv,
    )


def set_schema(client):
    """Set the Dgraph schema."""
    schema = """
    type Person {
        username
        name
        friend
        married
        location
        dob
        attended
    }

    type School {
        name
    }

    username: string @index(exact) .
    name: string @index(exact) .
    name_lower: string @index(exact) .
    friend: [uid] @reverse .
    attended: [uid] @reverse .
    married: bool .
    location: geo .
    dob: datetime .
    """
    return client.alter(pydgraph.Operation(schema=schema))


def create_data(client, data_dir=None):
    """Load all sample data from CSV files."""
    if data_dir is None:
        data_dir = DATA_DIR

    persons_csv = os.path.join(data_dir, 'persons.csv')
    schools_csv = os.path.join(data_dir, 'schools.csv')
    attended_csv = os.path.join(data_dir, 'attended.csv')
    friendships_csv = os.path.join(data_dir, 'friendships.csv')

    return ingest_multi_csv(
        client,
        persons_path=persons_csv,
        schools_path=schools_csv,
        attended_path=attended_csv,
        friendships_path=friendships_csv,
    )


def search_person(client, name):
    """Search for a person by name."""
    query = '''query search_person($a: string) {
        all(func: eq(name, $a)) {
            uid
            username
            name
            married
            location
            dob
            friend {
                uid
                username
                name
            }
            attended {
                uid
                name
            }
        }
    }'''
    variables = {'$a': name}
    response = client.txn(read_only=True).query(query, variables=variables)
    return json.loads(response.json).get('all', [])


def get_all_persons(client):
    """Get all persons."""
    query = '''{
        all(func: type(Person)) {
            uid
            username
            name
            married
            dob
        }
    }'''
    response = client.txn(read_only=True).query(query)
    return json.loads(response.json).get('all', [])


def get_all_schools(client):
    """Get all schools."""
    query = '''{
        all(func: type(School)) {
            uid
            name
        }
    }'''
    response = client.txn(read_only=True).query(query)
    return json.loads(response.json).get('all', [])


def delete_person(client, name):
    """Delete a person by name."""
    query = '''query search_person($a: string) {
        all(func: eq(name, $a)) {
            uid
        }
    }'''
    variables = {'$a': name}

    txn = client.txn()
    try:
        response = txn.query(query, variables=variables)
        data = json.loads(response.json)
        uids = [item['uid'] for item in data.get('all', [])]

        if not uids:
            return {'deleted': 0, 'uids': []}

        delete_objects = [{'uid': uid} for uid in uids]
        txn.mutate(del_obj=delete_objects)
        txn.commit()
        return {'deleted': len(uids), 'uids': uids}
    finally:
        txn.discard()


def drop_all(client):
    """Drop all data and schema."""
    return client.alter(pydgraph.Operation(drop_all=True))


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    value = str(value).strip().lower()
    return value in {'true', 'yes', '1', 'y', 't'}


def _get_existing_person_uid_by_username(client, username):
    if not username:
        return None
    username = username.strip().lower()
    query = '''query ExistingPersonByUsername($a: string) {
        all(func: eq(username, $a)) { uid }
    }'''
    variables = {'$a': username}
    response = client.txn(read_only=True).query(query, variables=variables)
    matches = json.loads(response.json).get('all', [])
    return matches[0]['uid'] if matches else None


def _get_existing_person_uid(client, name):
    if not name:
        return None
    query = '''query ExistingPerson($a: string) {
        all(func: eq(name, $a)) { uid }
    }'''
    variables = {'$a': name}
    response = client.txn(read_only=True).query(query, variables=variables)
    matches = json.loads(response.json).get('all', [])
    return matches[0]['uid'] if matches else None


def _get_existing_school_uid(client, name):
    if not name:
        return None
    query = '''query ExistingSchool($a: string) {
        all(func: eq(name_lower, $a)) { uid }
    }'''
    variables = {'$a': name.strip().lower()}
    response = client.txn(read_only=True).query(query, variables=variables)
    matches = json.loads(response.json).get('all', [])
    return matches[0]['uid'] if matches else None


def _build_person_node(row, username_field):
    name_value = row.get('name', '').strip()
    fallback_name = row.get(username_field, '').strip() if username_field != 'name' else ''
    person = {
        'dgraph.type': 'Person',
        'name': name_value or fallback_name,
    }

    username_value = row.get('username') or row.get(username_field, '')
    if username_value:
        person['username'] = username_value.strip().lower()

    married_value = row.get('married')
    if married_value is not None and married_value != '':
        person['married'] = _parse_bool(married_value)

    dob_value = row.get('dob')
    if dob_value:
        try:
            parsed = datetime.datetime.fromisoformat(dob_value.strip())
            person['dob'] = parsed.isoformat()
        except ValueError:
            person['dob'] = dob_value.strip()

    lat = row.get('location_lat') or row.get('latitude')
    lon = row.get('location_lon') or row.get('longitude')
    if lat and lon:
        try:
            person['location'] = {
                'type': 'Point',
                'coordinates': [float(lon), float(lat)],
            }
        except ValueError:
            pass

    return person


def ingest_persons_csv(client, csv_path, username_field='username'):
    """Ingest persons from CSV."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f'CSV file not found: {csv_path}')

    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    summary = {'rows': len(rows), 'created': 0, 'skipped': 0, 'errors': []}

    for row in rows:
        username = row.get(username_field, '').strip()
        if not username:
            continue

        existing = _get_existing_person_uid_by_username(client, username)
        if existing:
            summary['skipped'] += 1
            continue

        person_node = _build_person_node(row, username_field)
        txn = client.txn()
        try:
            txn.mutate(set_obj=person_node)
            txn.commit()
            summary['created'] += 1
        except Exception as e:
            summary['errors'].append(str(e))
        finally:
            txn.discard()

    return summary


def ingest_schools_csv(client, csv_path, school_field='name'):
    """Ingest schools from CSV."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f'CSV file not found: {csv_path}')

    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    summary = {'rows': len(rows), 'created': 0, 'skipped': 0, 'errors': []}

    for row in rows:
        school_name = row.get(school_field, '').strip()
        if not school_name:
            continue

        existing = _get_existing_school_uid(client, school_name)
        if existing:
            summary['skipped'] += 1
            continue

        school_node = {
            'dgraph.type': 'School',
            'name': school_name,
            'name_lower': school_name.lower(),
        }

        txn = client.txn()
        try:
            txn.mutate(set_obj=school_node)
            txn.commit()
            summary['created'] += 1
        except Exception as e:
            summary['errors'].append(str(e))
        finally:
            txn.discard()

    return summary


def ingest_attendance_csv(client, csv_path, person_field='person_username', school_field='school_name'):
    """Ingest attendance relationships from CSV."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f'CSV file not found: {csv_path}')

    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    summary = {'rows': len(rows), 'processed': 0, 'skipped': 0, 'errors': []}

    for row in rows:
        person_username = row.get(person_field, '').strip()
        school_name = row.get(school_field, '').strip()

        person_uid = _get_existing_person_uid_by_username(client, person_username)
        school_uid = _get_existing_school_uid(client, school_name)

        if not person_uid or not school_uid:
            summary['skipped'] += 1
            continue

        txn = client.txn()
        try:
            mutation = {'uid': person_uid, 'attended': [{'uid': school_uid}]}
            txn.mutate(set_obj=mutation)
            txn.commit()
            summary['processed'] += 1
        except Exception as e:
            summary['errors'].append(str(e))
        finally:
            txn.discard()

    return summary


def ingest_friendships_csv(client, csv_path, person_field='person_username', friend_field='friend_username'):
    """Ingest friendship relationships from CSV."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f'CSV file not found: {csv_path}')

    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    summary = {'rows': len(rows), 'processed': 0, 'skipped': 0, 'errors': []}

    for row in rows:
        person_username = row.get(person_field, '').strip()
        friend_username = row.get(friend_field, '').strip()

        person_uid = _get_existing_person_uid_by_username(client, person_username)
        friend_uid = _get_existing_person_uid_by_username(client, friend_username)

        if not person_uid:
            summary['skipped'] += 1
            continue

        if friend_uid:
            friend_ref = {'uid': friend_uid}
        else:
            friend_ref = {
                'dgraph.type': 'Person',
                'username': friend_username.strip().lower(),
                'name': friend_username,
            }

        txn = client.txn()
        try:
            mutation = {'uid': person_uid, 'friend': [friend_ref]}
            txn.mutate(set_obj=mutation)
            txn.commit()
            summary['processed'] += 1
        except Exception as e:
            summary['errors'].append(str(e))
        finally:
            txn.discard()

    return summary


def ingest_multi_csv(client, persons_path, schools_path, attended_path=None, friendships_path=None):
    """Ingest all CSV files."""
    result = {
        'persons': ingest_persons_csv(client, persons_path),
        'schools': ingest_schools_csv(client, schools_path),
    }

    if attended_path:
        result['attended'] = ingest_attendance_csv(client, attended_path)

    if friendships_path:
        result['friendships'] = ingest_friendships_csv(client, friendships_path)

    return result
