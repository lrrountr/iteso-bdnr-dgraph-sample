#!/usr/bin/env python3
import argparse
import json
import os
import sys

import pydgraph

import model

DGRAPH_URI = os.getenv('DGRAPH_URI', 'localhost:9080')


def create_client_stub():
    return pydgraph.DgraphClientStub(DGRAPH_URI)


def create_client(client_stub):
    return pydgraph.DgraphClient(client_stub)


def close_client_stub(client_stub):
    client_stub.close()


def parse_args():
    parser = argparse.ArgumentParser(description='Dgraph sample CLI')
    subparsers = parser.add_subparsers(dest='command', required=True)

    create_data_parser = subparsers.add_parser('create-data', help='Create sample data from CSV files')
    create_data_parser.add_argument('--data-dir', default='data', help='Directory containing CSV sample files')

    search_parser = subparsers.add_parser('search-person', help='Search a person by exact name')
    search_parser.add_argument('--name', '-n', required=True, help='Exact name to search')

    delete_parser = subparsers.add_parser('delete-person', help='Delete a person by exact name')
    delete_parser.add_argument('--name', '-n', required=True, help='Exact name to delete')

    subparsers.add_parser('drop-all', help='Drop all data and schema')

    ingest_multi_parser = subparsers.add_parser('ingest-multi-csv', help='Ingest people, schools, and relationships from separate CSV files')
    ingest_multi_parser.add_argument('--persons', '--people', required=True, help='Path to people CSV file')
    ingest_multi_parser.add_argument('--schools', required=True, help='Path to schools CSV file')
    ingest_multi_parser.add_argument('--attended', required=False, help='Path to attendance CSV file')
    ingest_multi_parser.add_argument('--friendships', required=False, help='Path to friendships CSV file')
    ingest_multi_parser.add_argument('--person-field', default='person_username', help='Person field name in relationship CSV files')
    ingest_multi_parser.add_argument('--friend-field', default='friend_username', help='Friend field name in friendships CSV file')
    ingest_multi_parser.add_argument('--school-field', default='name', help='Field name for school unique key in the schools CSV file')
    ingest_multi_parser.add_argument('--attendance-school-field', default='school_name', help='Field name for school unique key in the attendance CSV file')
    ingest_multi_parser.add_argument('--username-field', default='username', help='Field name for person unique key')

    return parser.parse_args()


def main():
    args = parse_args()
    client_stub = create_client_stub()
    client = create_client(client_stub)

    try:
        model.set_schema(client)

        if args.command == 'create-data':
            result = model.create_data(client, data_dir=args.data_dir)
            print(json.dumps(result, indent=2))
        elif args.command == 'search-person':
            people = model.search_person(client, args.name)
            print(json.dumps({'count': len(people), 'people': people}, indent=2))
        elif args.command == 'delete-person':
            summary = model.delete_person(client, args.name)
            print(json.dumps(summary, indent=2))
        elif args.command == 'drop-all':
            result = model.drop_all(client)
            print(json.dumps({'dropped': True, 'result': str(result)}, indent=2))
        elif args.command == 'ingest-multi-csv':
            summary = model.ingest_multi_csv(
                client,
                persons_path=args.persons,
                schools_path=args.schools,
                attended_path=args.attended,
                friendships_path=args.friendships,
                username_field=args.username_field,
                school_field=args.school_field,
                attendance_school_field=args.attendance_school_field,
                person_field=args.person_field,
                friend_field=args.friend_field,
            )
            print(json.dumps(summary, indent=2))
        else:
            raise ValueError(f'Unknown command: {args.command}')
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)
    finally:
        close_client_stub(client_stub)


if __name__ == '__main__':
    main()
