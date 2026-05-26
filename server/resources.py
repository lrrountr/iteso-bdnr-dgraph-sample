#!/usr/bin/env python3
"""
Falcon resource classes for the Dgraph REST API.
"""
import logging

import falcon

import model

log = logging.getLogger(__name__)


class HealthResource:

    def __init__(self, connection):
        self.connection = connection

    async def on_get(self, req, resp):
        """GET /health"""
        if self.connection.is_connected():
            resp.media = {'status': 'healthy', 'database': 'connected'}
        else:
            resp.media = {'status': 'unhealthy', 'database': 'disconnected'}
            resp.status = falcon.HTTP_503


class SetupResource:
    """Admin — set the graph schema (types and predicates only, no data)."""

    def __init__(self, connection):
        self.connection = connection

    async def on_post(self, req, resp):
        """POST /setup — apply schema"""
        try:
            model.set_schema(self.connection.client)
            resp.media = {
                'status': 'success',
                'message': 'Schema applied',
                'types': ['Person', 'School'],
                'predicates': [
                    'username: string @index(exact)',
                    'name: string @index(exact)',
                    'friend: [uid] @reverse',
                    'attended: [uid] @reverse',
                    'married: bool',
                    'location: geo',
                    'dob: datetime',
                ],
            }
            resp.status = falcon.HTTP_201
        except Exception as e:
            log.exception("Setup failed")
            resp.media = {'status': 'error', 'message': str(e)}
            resp.status = falcon.HTTP_500


class SeedResource:
    """Admin — load sample data from CSV files using real business operations."""

    def __init__(self, connection):
        self.connection = connection

    async def on_post(self, req, resp):
        """POST /seed — load persons, schools, friendships, attendance from CSV"""
        try:
            result = model.seed_data(self.connection.client)
            resp.media = {'status': 'success', 'summary': result}
            resp.status = falcon.HTTP_201
        except Exception as e:
            log.exception("Seed failed")
            resp.media = {'status': 'error', 'message': str(e)}
            resp.status = falcon.HTTP_500


class DropResource:
    """Admin — drop all data and schema."""

    def __init__(self, connection):
        self.connection = connection

    async def on_post(self, req, resp):
        """POST /drop"""
        try:
            model.drop_all(self.connection.client)
            resp.media = {'status': 'success', 'message': 'All data and schema dropped'}
        except Exception as e:
            log.exception("Drop failed")
            resp.media = {'status': 'error', 'message': str(e)}
            resp.status = falcon.HTTP_500


class PersonsResource:

    def __init__(self, connection):
        self.connection = connection

    async def on_get(self, req, resp):
        """GET /persons — list all persons"""
        try:
            persons = model.get_all_persons(self.connection.client)
            resp.media = {'persons': persons, 'count': len(persons)}
        except Exception as e:
            log.exception("Failed to list persons")
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_500

    async def on_post(self, req, resp):
        """
        POST /persons — add a new person node to the graph.

        Body: { "username": "alice", "name": "Alice", "married": false,
                "dob": "1990-01-15", "lat": 20.67, "lon": -103.35 }
        """
        try:
            body = await req.get_media()
            username = (body.get('username') or '').strip()
            name = (body.get('name') or '').strip()
            if not username or not name:
                resp.media = {'error': 'username and name are required'}
                resp.status = falcon.HTTP_400
                return

            uid = model.create_person(
                self.connection.client,
                username=username,
                name=name,
                married=body.get('married'),
                dob=body.get('dob'),
                lat=body.get('lat'),
                lon=body.get('lon'),
            )
            resp.media = {'uid': uid, 'username': username, 'name': name}
            resp.status = falcon.HTTP_201
        except ValueError as e:
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_409
        except Exception as e:
            log.exception("Failed to create person")
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_500


class PersonResource:

    def __init__(self, connection):
        self.connection = connection

    async def on_get(self, req, resp, username):
        """GET /persons/{username} — search for a person (includes friends and schools)"""
        try:
            persons = model.search_person(self.connection.client, username)
            if not persons:
                resp.media = {'error': f"No person found with name '{username}'"}
                resp.status = falcon.HTTP_404
                return
            resp.media = {'persons': persons, 'count': len(persons)}
        except Exception as e:
            log.exception(f"Failed to search person '{username}'")
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_500

    async def on_delete(self, req, resp, username):
        """DELETE /persons/{username}"""
        try:
            result = model.delete_person(self.connection.client, username)
            if result['deleted'] == 0:
                resp.media = {'error': f"No person found with name '{username}'"}
                resp.status = falcon.HTTP_404
                return
            resp.media = {'status': 'success', 'message': f"Deleted {result['deleted']} person(s)"}
        except Exception as e:
            log.exception(f"Failed to delete person '{username}'")
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_500


class FriendshipsResource:

    def __init__(self, connection):
        self.connection = connection

    async def on_post(self, req, resp, username):
        """
        POST /persons/{username}/friends — add a friendship edge.

        Body: { "friend_username": "bob", "since": "2010-01-01", "close": true }

        In Dgraph, the @reverse directive on the 'friend' predicate means
        this single write makes the relationship queryable from both sides.
        Facets (since, close) are stored on the edge itself.
        """
        try:
            body = await req.get_media()
            friend_username = (body.get('friend_username') or '').strip()
            if not friend_username:
                resp.media = {'error': 'friend_username is required'}
                resp.status = falcon.HTTP_400
                return

            since = body.get('since')
            close = body.get('close')

            model.add_friendship(self.connection.client, username, friend_username,
                                 since=since, close=close)
            resp.media = {
                'status': 'success',
                'message': f"Friendship added: {username} ↔ {friend_username}",
                'note': '@reverse makes this queryable from both sides automatically',
            }
            resp.status = falcon.HTTP_201
        except ValueError as e:
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_404
        except Exception as e:
            log.exception("Failed to add friendship")
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_500


class AttendanceResource:

    def __init__(self, connection):
        self.connection = connection

    async def on_post(self, req, resp, username):
        """
        POST /persons/{username}/schools — enroll a person in a school.

        Body: { "school_name": "ITESO", "year_start": 2005, "year_end": 2010, "degree": "Computer Science" }

        Facets (year_start, year_end, degree) are stored on the edge itself, not on the school node.
        """
        try:
            body = await req.get_media()
            school_name = (body.get('school_name') or '').strip()
            if not school_name:
                resp.media = {'error': 'school_name is required'}
                resp.status = falcon.HTTP_400
                return

            model.add_attendance(
                self.connection.client, username, school_name,
                year_start=body.get('year_start'),
                year_end=body.get('year_end'),
                degree=body.get('degree'),
            )
            resp.media = {
                'status': 'success',
                'message': f"{username} enrolled in {school_name}",
            }
            resp.status = falcon.HTTP_201
        except ValueError as e:
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_404
        except Exception as e:
            log.exception("Failed to add attendance")
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_500


class SchoolsResource:

    def __init__(self, connection):
        self.connection = connection

    async def on_get(self, req, resp):
        """GET /schools — list all schools"""
        try:
            schools = model.get_all_schools(self.connection.client)
            resp.media = {'schools': schools, 'count': len(schools)}
        except Exception as e:
            log.exception("Failed to list schools")
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_500

    async def on_post(self, req, resp):
        """POST /schools — add a new school node to the graph."""
        try:
            body = await req.get_media()
            name = (body.get('name') or '').strip()
            if not name:
                resp.media = {'error': 'name is required'}
                resp.status = falcon.HTTP_400
                return

            uid = model.create_school(self.connection.client, name)
            resp.media = {'uid': uid, 'name': name}
            resp.status = falcon.HTTP_201
        except ValueError as e:
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_409
        except Exception as e:
            log.exception("Failed to create school")
            resp.media = {'error': str(e)}
            resp.status = falcon.HTTP_500
