#!/usr/bin/env python3
import csv
import datetime
import json
import os

import pydgraph


def set_schema(client):
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


def create_data(client, data_dir='data'):
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


def delete_person(client, name):
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
        mutation = txn.mutate(del_obj=delete_objects)
        commit_response = txn.commit()
        return {
            'deleted': len(uids),
            'uids': uids,
            'mutation_uids': dict(mutation.uids),
            'commit_response': str(commit_response),
        }
    finally:
        txn.discard()


def search_person(client, name):
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


def drop_all(client):
    return client.alter(pydgraph.Operation(drop_all=True))


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    value = str(value).strip().lower()
    return value in {'true', 'yes', '1', 'y', 't'}


def _get_existing_person_uid(client, name):
    if not name:
        return None
    query = '''query ExistingPerson($a: string) {
        all(func: eq(name, $a)) {
            uid
        }
    }'''
    variables = {'$a': name}
    response = client.txn(read_only=True).query(query, variables=variables)
    data = json.loads(response.json)
    matches = data.get('all', [])
    return matches[0]['uid'] if matches else None


def _get_existing_person_uid_by_username(client, username):
    if not username:
        return None
    username = username.strip().lower()
    query = '''query ExistingPersonByUsername($a: string) {
        all(func: eq(username, $a)) {
            uid
        }
    }'''
    variables = {'$a': username}
    response = client.txn(read_only=True).query(query, variables=variables)
    data = json.loads(response.json)
    matches = data.get('all', [])
    return matches[0]['uid'] if matches else None


def _find_person_uid(client, identifier):
    if not identifier:
        return None
    uid = _get_existing_person_uid_by_username(client, identifier)
    if uid:
        return uid
    return _get_existing_person_uid(client, identifier)


def _get_existing_school_uid(client, name):
    if not name:
        return None
    query = '''query ExistingSchool($a: string) {
        all(func: eq(name_lower, $a)) {
            uid
        }
    }'''
    variables = {'$a': name.strip().lower()}
    response = client.txn(read_only=True).query(query, variables=variables)
    data = json.loads(response.json)
    matches = data.get('all', [])
    return matches[0]['uid'] if matches else None


def _find_school_uid(client, name):
    if not name:
        return None
    return _get_existing_school_uid(client, name)


def _build_person_node(row, username_field):
    name_value = row.get('name', '').strip()
    fallback_name = row.get(username_field, '').strip() if username_field != 'name' else ''
    person = {
        'dgraph.type': 'Person',
        'name': name_value or fallback_name,
    }

    username_value = row.get('username') or row.get(username_field, '')
    if username_value:
        username_value = username_value.strip().lower()
        person['username'] = username_value

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
    else:
        location_value = row.get('location')
        if location_value and ',' in location_value:
            parts = [p.strip() for p in location_value.split(',')]
            if len(parts) == 2:
                try:
                    lat_value = float(parts[0])
                    lon_value = float(parts[1])
                    person['location'] = {
                        'type': 'Point',
                        'coordinates': [lon_value, lat_value],
                    }
                except ValueError:
                    pass

    return person




def ingest_persons_csv(client, csv_path, username_field='username'):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f'CSV file not found: {csv_path}')

    with open(csv_path, newline='', encoding='utf-8') as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    summary = {
        'rows': len(rows),
        'created': 0,
        'skipped': 0,
        'skipped_usernames': [],
        'errors': [],
    }

    for row in rows:
        username = row.get(username_field, '').strip()
        if not username:
            summary['errors'].append({'row': row, 'reason': f'missing {username_field}'})
            continue

        username = row.get('username') or username
        lookup_value = username.strip() if username else username
        existing = _get_existing_person_uid_by_username(client, lookup_value) if username else _get_existing_person_uid(client, lookup_value)
        if existing:
            summary['skipped'] += 1
            summary['skipped_usernames'].append(lookup_value)
            continue

        person_node = _build_person_node(row, username_field)
        if not person_node.get('name'):
            summary['errors'].append({'row': row, 'reason': f'invalid {username_field}'})
            continue

        txn = client.txn()
        try:
            txn.mutate(set_obj=person_node)
            txn.commit()
            summary['created'] += 1
        except Exception as exc:
            summary['errors'].append({'row': row, 'error': str(exc)})
        finally:
            txn.discard()

    return summary


def ingest_schools_csv(client, csv_path, school_field='name'):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f'CSV file not found: {csv_path}')

    with open(csv_path, newline='', encoding='utf-8') as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    summary = {
        'rows': len(rows),
        'created': 0,
        'skipped': 0,
        'skipped_schools': [],
        'errors': [],
    }

    for row in rows:
        school_name = row.get(school_field, '').strip()
        if not school_name:
            summary['errors'].append({'row': row, 'reason': f'missing {school_field}'})
            continue

        existing = _get_existing_school_uid(client, school_name)
        if existing:
            summary['skipped'] += 1
            summary['skipped_schools'].append(school_name)
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
        except Exception as exc:
            summary['errors'].append({'row': row, 'error': str(exc)})
        finally:
            txn.discard()

    return summary


def ingest_attendance_csv(client, csv_path, person_field='person_username', school_field='name'):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f'CSV file not found: {csv_path}')

    with open(csv_path, newline='', encoding='utf-8') as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    summary = {
        'rows': len(rows),
        'processed': 0,
        'skipped': 0,
        'errors': [],
    }

    for row in rows:
        person_username = row.get(person_field, '').strip()
        school_name = row.get(school_field, '').strip()
        if not person_username or not school_name:
            summary['errors'].append({'row': row, 'reason': 'missing person username or school name field'})
            continue

        person_uid = _get_existing_person_uid_by_username(client, person_username)
        school_uid = _find_school_uid(client, school_name)

        if not person_uid or not school_uid:
            summary['skipped'] += 1
            summary['errors'].append({'row': row, 'reason': 'missing person or school node'})
            continue

        txn = client.txn()
        try:
            mutation = {
                'uid': person_uid,
                'attended': [{'uid': school_uid}],
            }
            txn.mutate(set_obj=mutation)
            txn.commit()
            summary['processed'] += 1
        except Exception as exc:
            summary['errors'].append({'row': row, 'error': str(exc)})
        finally:
            txn.discard()

    return summary


def ingest_friendships_csv(client, csv_path, person_field='person_username', friend_field='friend_username'):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f'CSV file not found: {csv_path}')

    with open(csv_path, newline='', encoding='utf-8') as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)

    summary = {
        'rows': len(rows),
        'processed': 0,
        'skipped': 0,
        'errors': [],
    }

    for row in rows:
        person_username = row.get(person_field, '').strip()
        friend_username = row.get(friend_field, '').strip()
        if not person_username or not friend_username:
            summary['errors'].append({'row': row, 'reason': 'missing person username or friend username field'})
            continue

        person_uid = _get_existing_person_uid_by_username(client, person_username)
        friend_uid = _get_existing_person_uid_by_username(client, friend_username)

        if not person_uid:
            summary['skipped'] += 1
            summary['errors'].append({'row': row, 'reason': 'missing person node'})
            continue

        if friend_uid:
            friend_ref = {'uid': friend_uid}
        else:
            normalized_friend_username = friend_username.strip().lower().replace(' ', '_')
            friend_ref = {
                'uid': f'_:friend_{summary["rows"]}_{summary["processed"]}',
                'dgraph.type': 'Person',
                'username': normalized_friend_username,
                'name': friend_username,
            }

        txn = client.txn()
        try:
            mutation = {
                'uid': person_uid,
                'friend': [friend_ref],
            }
            txn.mutate(set_obj=mutation)
            txn.commit()
            summary['processed'] += 1
        except Exception as exc:
            summary['errors'].append({'row': row, 'error': str(exc)})
        finally:
            txn.discard()

    return summary


def ingest_multi_csv(
    client,
    persons_path,
    schools_path,
    attended_path=None,
    friendships_path=None,
    username_field='username',
    school_field='name',
    attendance_school_field='school_name',
    person_field='person_username',
    friend_field='friend_username',
):
    result = {
        'people': ingest_persons_csv(client, persons_path, username_field=username_field),
        'schools': ingest_schools_csv(client, schools_path, school_field=school_field),
    }

    if attended_path:
        result['attended'] = ingest_attendance_csv(
            client,
            attended_path,
            person_field=person_field,
            school_field=attendance_school_field,
        )

    if friendships_path:
        result['friendships'] = ingest_friendships_csv(
            client,
            friendships_path,
            person_field=person_field,
            friend_field=friend_field,
        )

    return result
