# ITESO BDNR - Dgraph Sample

A sample social network application demonstrating Dgraph graph database patterns with a REST API architecture.

## Architecture

```
┌────────────┐       ┌────────────┐       ┌────────────┐
│   Client   │ HTTP  │   Server   │ gRPC  │   Dgraph   │
│   (CLI)    │ ────► │ (REST API) │ ────► │  (Docker)  │
└────────────┘       └────────────┘       └────────────┘
     client/              server/           port 9080
```

## Project Structure

```
iteso-bdnr-dgraph-sample/
├── server/
│   ├── app.py          # Falcon application and routes
│   ├── resources.py    # REST endpoint handlers
│   └── model.py        # Dgraph mutations and queries
├── client/
│   └── cli.py          # Command-line client
├── data/
│   ├── persons.csv     # Person nodes
│   ├── schools.csv     # School nodes
│   ├── attended.csv    # Person → School edges
│   └── friendships.csv # Person ↔ Person edges
├── requirements.txt
└── README.md
```

## Data Model

```graphql
type Person {
    username    # Unique identifier (lowercase)
    name        # Display name
    friend      # Edge → Person  (@reverse: queryable from both sides)
    married     # bool
    location    # geo point
    dob         # datetime
    attended    # Edge → School  (@reverse: queryable from both sides)
}

type School {
    name
}
```

Relationships use Dgraph's `@reverse` directive — adding one edge automatically makes it traversable from both directions.

### Facets

Facets are key-value pairs stored on edges (not nodes). They capture metadata about a relationship without polluting the node itself.

| Edge | Facets |
|------|--------|
| `friend` | `since` (date string), `close` (bool) |
| `attended` | `year_start` (int), `year_end` (int), `degree` (string) |

Facets require no schema declaration — they are stored automatically when set on a mutation.

## Setup

You will need **2 terminal windows**: one for the server, one for the CLI.

### Step 1: Start Dgraph

```bash
docker run --name dgraph -p 8080:8080 -p 9080:9080 -d dgraph/standalone

# Dgraph takes ~10 seconds to start
# Port 8080: Ratel UI  (http://localhost:8080)
# Port 9080: gRPC endpoint (used by the API server)
```

### Step 2: Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate        # Linux/Mac
# .\venv\Scripts\Activate.ps1   # Windows

pip install -r requirements.txt
```

### Step 3: Start the API Server

```bash
cd server
uvicorn app:app --reload --port 8001
```

### Step 4: Apply Schema

```bash
cd client
source ../venv/bin/activate

python cli.py setup
```

### Step 5: (Optional) Load Demo Data

```bash
python cli.py seed
```

## CLI Commands

### Admin

| Command | Description |
|---------|-------------|
| `status` | Check if API is running |
| `setup` | Apply graph schema (types + predicates, no data) |
| `seed` | Load demo persons, schools and relationships from CSV |
| `drop` | Drop all data and schema (with confirmation) |

### Graph Operations

| Command | Description |
|---------|-------------|
| `add-person --username U --name N` | Add a person node |
| `add-school --name N` | Add a school node |
| `befriend --person U --friend U2 [--since DATE] [--close]` | Add friendship edge (bidirectional) |
| `enroll --person U --school S [--year-start Y] [--year-end Y] [--degree D]` | Add person→school attendance edge |
| `persons` | List all persons |
| `search --name N` | Search person — shows friends and schools |
| `delete --name N` | Delete a person |
| `schools` | List all schools |

### Typical Session

```bash
# Admin
python cli.py setup
python cli.py seed

# Or build the graph manually:
python cli.py add-school --name "ITESO"
python cli.py add-person --username alice --name "Alice" --dob "1995-03-10"
python cli.py add-person --username bob   --name "Bob"   --dob "1993-07-22"

# Add relationships (with facets)
python cli.py befriend --person alice --friend bob --since "2011-09-01"
python cli.py enroll   --person alice --school "ITESO" --year-start 2010 --year-end 2015 --degree "Computer Science"

# Explore
python cli.py persons
python cli.py search --name Alice     # shows friends + schools
python cli.py schools
```

## REST API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/setup` | Apply schema (no data) |
| POST | `/seed` | Load demo data |
| POST | `/drop` | Drop all data and schema |
| GET | `/persons` | List all persons |
| POST | `/persons` | Add a person node |
| GET | `/persons/{name}` | Search person (with friends + schools) |
| DELETE | `/persons/{name}` | Delete a person |
| POST | `/persons/{username}/friends` | Add friendship edge |
| POST | `/persons/{username}/schools` | Add attendance edge |
| GET | `/schools` | List all schools |
| POST | `/schools` | Add a school node |

### Example API Calls

```bash
curl http://localhost:8001/health
curl -X POST http://localhost:8001/setup
curl -X POST http://localhost:8001/persons \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "name": "Alice", "dob": "1995-03-10"}'
curl -X POST http://localhost:8001/schools \
  -H "Content-Type: application/json" \
  -d '{"name": "ITESO"}'
curl -X POST http://localhost:8001/persons/alice/friends \
  -H "Content-Type: application/json" \
  -d '{"friend_username": "bob", "since": "2011-09-01", "close": false}'
curl -X POST http://localhost:8001/persons/alice/schools \
  -H "Content-Type: application/json" \
  -d '{"school_name": "ITESO", "year_start": 2010, "year_end": 2015, "degree": "Computer Science"}'
curl http://localhost:8001/persons/Alice
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_URL` | `http://localhost:8001` | API URL (client) |
| `DGRAPH_HOST` | `localhost` | Dgraph host (server) |
| `DGRAPH_PORT` | `9080` | Dgraph gRPC port (server) |

## Troubleshooting

**"Cannot connect to API"** — make sure the server is running: `cd server && uvicorn app:app --reload --port 8001`

**"Failed to connect to Dgraph"** — wait ~10s after starting Docker, then check: `docker ps` or open http://localhost:8080

**"No persons found"** — run `setup` then `seed` (or `add-person`)

## Ratel UI

Dgraph includes a web UI for exploring data and running queries:
- Open http://localhost:8080 in your browser
- Use the Query tab to run DQL queries directly against the graph
