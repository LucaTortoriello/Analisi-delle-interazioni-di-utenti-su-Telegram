# Analisi delle interazioni degli utenti su Telegram

Applicazione Vue/Vite con API Flask, MySQL per i dati Telegram e Neo4j per le viste a grafo.

## Requisiti macOS

- Homebrew
- Node.js e npm
- Python 3
- MySQL
- Neo4j (necessario per gli endpoint del grafo)

Installazione degli strumenti:

```bash
brew install node mysql neo4j
```

## Installazione del progetto

```bash
npm install
python3 -m venv venv
source venv/bin/activate
pip install -r src/backend/requirements.txt
```

Non versionare `venv`, `node_modules`, credenziali, sessioni Telegram o i dati scaricati: sono gia esclusi da `.gitignore`.

## Configurazione

Copia il file di esempio e inserisci localmente i valori reali:

```bash
cp src/backend/credenzialiDB.env.example src/backend/credenzialiDB.env
```

Il file locale deve contenere almeno le credenziali MySQL e le chiavi Telegram necessarie all'importazione. Non pubblicarlo su GitHub.

## Ripartenza da zero

Il progetto puo ripartire senza recuperare i vecchi database: MySQL e Neo4j vengono popolati dalle nuove scansioni dei gruppi.

Inizializza lo schema MySQL vuoto:

```bash
mysql -u root < src/backend/schema.sql
```

Poi configura le credenziali Telegram nel file locale `src/backend/credenzialiDB.env` e autentica la sessione:

```bash
source venv/bin/activate
cd src/backend
python3 importer_service.py --auth
```

Se il codice non arriva, puoi usare l'autenticazione QR:

```bash
python3 importer_service.py --qr
```

Scansiona il QR dal telefono in **Telegram > Impostazioni > Dispositivi > Collega dispositivo desktop**.

La prima scansione salva chat, utenti e messaggi in MySQL. Dopo una o piu scansioni, ricostruisci nodi e relazioni nel database Neo4j con:

```bash
python3 SyncMySQLNeo4j2_0.py
```

Non versionare il file delle credenziali o la sessione Telegram.

## Avvio locale

Avvia MySQL e Neo4j, poi in due terminali separati:

```bash
source venv/bin/activate
cd src/backend
python3 API.py
```

```bash
npm run dev
```

Frontend: `http://localhost:5173`  
API: `http://127.0.0.1:5000`
