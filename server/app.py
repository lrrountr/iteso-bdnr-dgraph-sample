#!/usr/bin/env python3
"""
Falcon ASGI application for the Dgraph social network REST API.
"""
import logging
import os

import falcon.asgi

from model import DgraphConnection
from resources import (
    HealthResource,
    SetupResource,
    SeedResource,
    DropResource,
    PersonsResource,
    PersonResource,
    FriendshipsResource,
    AttendanceResource,
    SchoolsResource,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger(__name__)

DGRAPH_HOST = os.getenv('DGRAPH_HOST', 'localhost')
DGRAPH_PORT = int(os.getenv('DGRAPH_PORT', '9080'))


class LoggingMiddleware:
    async def process_request(self, req, resp):
        log.info(f"Request: {req.method} {req.uri}")

    async def process_response(self, req, resp, resource, req_succeeded):
        log.info(f"Response: {resp.status} for {req.method} {req.uri}")


def create_app():
    connection = DgraphConnection(host=DGRAPH_HOST, port=DGRAPH_PORT)
    try:
        connection.connect()
        log.info(f"Connected to Dgraph at {DGRAPH_HOST}:{DGRAPH_PORT}")
    except Exception as e:
        log.error(f"Failed to connect to Dgraph: {e}")
        raise

    app = falcon.asgi.App(middleware=[LoggingMiddleware()])

    app.add_route('/health',                        HealthResource(connection))
    app.add_route('/setup',                         SetupResource(connection))
    app.add_route('/seed',                          SeedResource(connection))
    app.add_route('/drop',                          DropResource(connection))
    app.add_route('/persons',                       PersonsResource(connection))
    app.add_route('/persons/{username}',            PersonResource(connection))
    app.add_route('/persons/{username}/friends',    FriendshipsResource(connection))
    app.add_route('/persons/{username}/schools',    AttendanceResource(connection))
    app.add_route('/schools',                       SchoolsResource(connection))

    log.info("Routes:")
    log.info("  GET    /health")
    log.info("  POST   /setup                        — apply schema (DDL only)")
    log.info("  POST   /seed                         — load demo data")
    log.info("  POST   /drop                         — drop all data and schema")
    log.info("  GET    /persons                      — list all persons")
    log.info("  POST   /persons                      — add a person node")
    log.info("  GET    /persons/{username}            — search person (includes friends + schools)")
    log.info("  DELETE /persons/{username}            — delete a person")
    log.info("  POST   /persons/{username}/friends   — add friendship edge")
    log.info("  POST   /persons/{username}/schools   — add attendance edge")
    log.info("  GET    /schools                      — list all schools")
    log.info("  POST   /schools                      — add a school node")

    return app


app = create_app()
