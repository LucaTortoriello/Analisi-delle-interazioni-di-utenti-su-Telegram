# Telegram User Interaction Analysis

A full-stack application for collecting, exploring, and analysing interactions between users in Telegram groups and channels.

The project combines a Vue 3 frontend with a Flask API, MySQL for Telegram data, and Neo4j for graph-based analysis. It was developed as part of Luca Tortoriello's bachelor's thesis.

## Features

- Import Telegram chats, users, messages, replies, and attachments.
- Browse dashboards with message, user, and chat statistics.
- Search messages, chats, and users.
- Inspect user profiles, activity, chat participation, and interaction history.
- Visualise user interactions as an interactive network graph.
- Analyse graph communities and filter graphs by keywords or selected users.
- Translate messages when needed.
- Run optional OSINT searches for public usernames using Maigret and SangMata integrations.

## Technology stack

- **Frontend:** Vue 3, Vite, Vue Router, Bootstrap, Chart.js, and vis-network.
- **Backend:** Python, Flask, Flask-CORS, and Flask-Caching.
- **Data storage:** MySQL for imported Telegram data and Neo4j for interaction graphs.
- **Telegram integration:** Telethon.
- **Analysis:** NetworkX and Neo4j graph queries.
- **Optional enrichment:** deep-translator, Maigret, and SangMata.

## Requirements

Install the following software before setting up the project:

- Node.js and npm
- Python 3
- MySQL
- Neo4j (required for graph endpoints)

On macOS, the dependencies can be installed with Homebrew:

```bash
brew install node mysql neo4j
```

On other operating systems, install the same tools using their official installers or your system package manager.

## Run with Docker (recommended)

Docker is the easiest way to run the application on a new machine. Install
[Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker
Engine with the Compose plugin, then create a personal environment file:

```bash
cp .env.example .env
```

Open `.env` and replace every placeholder password and the Telegram
`API_ID`/`API_HASH` with your own values. These credentials are read only when
the containers start; they are not copied into either Docker image or shared
by this repository. Each user therefore has their own Telegram account,
database credentials, and persistent Telegram session.

Start MySQL, Neo4j, the Flask API, and the Vue development server with:

```bash
docker compose up --build
```

Open `http://localhost:5173`. The API is exposed at
`http://localhost:5000`.

The first Telegram authentication is interactive and must be run once for
each user. In another terminal, choose either phone-code authentication:

```bash
docker compose run --rm backend python importer_service.py --auth
```

or QR-code authentication:

```bash
docker compose run --rm backend python importer_service.py --qr
```

The Telegram session and downloaded files are stored in Docker volumes and
survive container restarts. After importing data, synchronise the graph:

```bash
docker compose run --rm backend python SyncMySQLNeo4j2_0.py
```

Stop the application with:

```bash
docker compose down
```

To remove the local database data as well, use `docker compose down -v`.
This permanently deletes the MySQL, Neo4j, Telegram-session, and download
volumes.

## Installation

From the project root:

```bash
npm install
python3 -m venv venv
source venv/bin/activate
pip install -r src/backend/requirements.txt
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.\venv\Scripts\Activate.ps1
```

## Configuration

Create a local environment file from the provided example:

```bash
cp src/backend/credenzialiDB.env.example src/backend/credenzialiDB.env
```

Set at least the following values in `src/backend/credenzialiDB.env`:

```dotenv
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=
DB_NAME=analisiutentitelegram

API_ID=
API_HASH=
TELEGRAM_SESSION_NAME=telegram_session

NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
```

`API_ID` and `API_HASH` are Telegram API credentials. They can be obtained from [my.telegram.org](https://my.telegram.org/). Do not commit credentials, Telegram sessions, downloaded data, or OSINT reports. These files are excluded by `.gitignore`.

## Initial database setup

Start MySQL and initialise the relational schema:

```bash
mysql -u root < src/backend/schema.sql
```

Make sure Neo4j is running and that its credentials match the values in `credenzialiDB.env`.

## Importing Telegram data

Authenticate the Telegram client and import a chat:

```bash
source venv/bin/activate
cd src/backend
python3 importer_service.py --auth
```

If required, authenticate using a QR code:

```bash
python3 importer_service.py --qr
```

Scan the QR code from **Telegram > Settings > Devices > Link Desktop Device**.

After one or more chats have been imported, synchronise the MySQL data with Neo4j:

```bash
python3 SyncMySQLNeo4j2_0.py
```

The importer stores Telegram data in MySQL. The synchronisation step rebuilds the nodes and relationships used by the graph views.

## Running the application

Start the backend and frontend in two separate terminals.

### Backend

```bash
source venv/bin/activate
cd src/backend
python3 API.py
```

The API is available at `http://127.0.0.1:5000`.

### Frontend

From the project root:

```bash
npm run dev
```

The development interface is available at `http://localhost:5173`.

For a production build:

```bash
npm run build
npm run preview
```

## API overview

The Flask API exposes endpoints for:

- Statistics and recent activity (`/api/statistiche`, `/api/attivita`)
- Users, chats, messages, and attachments
- Message and chat search
- Graph data, focused graphs, keyword graphs, and community analysis
- Telegram import status
- Message translation
- Optional OSINT and username-history searches

The complete endpoint implementation is available in [`src/backend/API.py`](src/backend/API.py).

## Project structure

```text
.
├── src/
│   ├── components/       # Vue views and reusable UI components
│   ├── router/           # Frontend routes
│   ├── backend/          # Flask API, importer, synchronisation, and schema
│   ├── App.vue
│   └── main.js
├── public/               # Static frontend assets
├── Tortoriello_Luca.pdf  # Bachelor's thesis
├── package.json
└── vite.config.js
```

## Thesis

The accompanying bachelor's thesis is available in [`Tortoriello_Luca.pdf`](Tortoriello_Luca.pdf).

## Privacy, ethics, and responsible use

This project can process personal messages, usernames, and interaction data. Use it only with the appropriate authorisation and in compliance with Telegram's terms, applicable data-protection laws, and your institution's research-ethics requirements.

- Do not publish private messages or personally identifiable information without a lawful basis and informed consent where required.
- Keep API credentials, Telegram sessions, database dumps, and generated reports private.
- Use OSINT integrations only for legitimate, documented research purposes.

## License

No license has been specified for this repository yet. Until a license is added, all rights are reserved by the copyright holder.
