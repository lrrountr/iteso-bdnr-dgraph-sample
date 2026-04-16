# iteso-bdnr-dgraph

A place to share dgraph app code

### Setup a python virtual env with python dgraph installed
```
# If pip is not present in you system
sudo apt update
sudo apt install python3-pip

# Install and activate virtual env (Linux/MacOS)
python3 -m pip install virtualenv
python3 -m venv ./venv
source ./venv/bin/activate

# Install and activate virtual env (Windows)
python3 -m pip install virtualenv
python3 -m venv ./venv
.\venv\Scripts\Activate.ps1

# Install project python requirements
pip install -r requirements.txt
```

### To load data
Ensure you have a running dgraph instance
i.e.:
```
docker run --name dgraph -d -p 8080:8080 -p 9080:9080  dgraph/standalone
```

### CLI usage
The repo now uses `argparse` instead of an interactive menu.

Create sample data from CSV files in `./data`:
```
python3 main.py create-data
```

Or specify a different sample directory:
```
python3 main.py create-data --data-dir ./data
```

Search for a person:
```
python3 main.py search-person --name Leo
```

Delete a person:
```
python3 main.py delete-person --name Leo
```

Drop all data and schema:
```
python3 main.py drop-all
```

Ingest using separate CSV files for people, schools, attendance, and friendships:
```
python3 main.py ingest-multi-csv \
  --people data/persons.csv \
  --schools data/schools.csv \
  --attended data/attended.csv \
  --friendships data/friendships.csv
```

If your attendance CSV uses `school_name` as the relationship key, the default arguments already match this format. Otherwise, customize the CSV field names with:
```
python3 main.py ingest-multi-csv \
  --people data/persons.csv \
  --schools data/schools.csv \
  --attended data/attended.csv \
  --friendships data/friendships.csv \
  --school-field name \
  --attendance-school-field school_name
```

### CSV format
The ingestion commands support CSV files with a header row. Useful headers include:
- `username` as the unique person key (recommended)
- `name` as the display name
- `married`
- `dob`
- `location_lat`, `location_lon`
- `location` (formatted as `lat,lon`)
- `person_username` and `school_name` for the attendance file
- `person_username` and `friend_username` for the friendships file

### Username normalization
Person usernames are stored in lowercase, so duplicates like `Leo` and `leo` will be treated the same.
School names are also normalized to lower-case for uniqueness, so `ITESO` and `iteso` will resolve to the same school.

### Sample data files
Sample files are available in `data/`:
- `data/persons.csv`
- `data/schools.csv`
- `data/attended.csv`
- `data/friendships.csv`
