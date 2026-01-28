"""
Servizio per interrogare SangMata Bot e salvare lo storico username.
Riutilizza la sessione Telegram già usata per lo scraping delle chats
"""

import asyncio
import re
import os
import threading
import queue
import mysql.connector
from datetime import datetime
from pathlib import Path
import logging
from dotenv import load_dotenv
from telethon import TelegramClient

logger = logging.getLogger(__name__)

# =========================
# Configurazione 
# =========================
BASE_DIR = Path(__file__).resolve().parent

def load_any_env():
    candidates = [
        BASE_DIR / ".env",
        BASE_DIR / "credenzialiDB.env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(dotenv_path=p)
            return

load_any_env()

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "telegram_session")
SESSION_FILE = BASE_DIR / SESSION_NAME

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "analisiutentitelegram")

SANGMATA_BOT = "SangMataInfo_bot"

# Coda e stato delle richieste
request_queue = queue.Queue()
REQUEST_STATUS = {}


def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4"
    )


def parse_date(date_str):
    """Prova a parsare una data in vari formati"""
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    formats = [
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%d-%m-%Y',
        '%d %b %Y',
        '%d %B %Y',
        '%Y.%m.%d',
        '%d.%m.%Y',
        '%b %d, %Y',
        '%B %d, %Y',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def parse_sangmata_response(text, user_id):
    """
    Parsing della risposta di SangMata.
    SangMata restituisce lo storico degli username e nomi in vari formati.
    """
    records = []
    
    if not text:
        return records
    
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Salta linee di intestazione
        if any(skip in line.lower() for skip in ['history', 'storico', 'record', '━', '─', 'id:']):
            continue
        
        # Pattern per username con data
        # Formato: 🔹 @username — 15 Jan 2024
        # Formato: • @username - 2024-01-15
        # Formato: @username (2024-01-15)
        username_patterns = [
            r'[🔹•\-\*]\s*@(\w+)\s*[—\-–]\s*([\d\w\s\-\/\.,]+)',
            r'@(\w+)\s*\(([\d\-\/\.]+)\)',
            r'@(\w+)\s*[—\-–]\s*([\d\w\s\-\/\.,]+)',
            r'[🔹•\-\*]\s*(\w+)\s*[—\-–]\s*([\d\w\s\-\/\.,]+)',  # senza @
        ]
        
        matched = False
        for pattern in username_patterns:
            match = re.search(pattern, line)
            if match:
                username = match.group(1)
                date_str = match.group(2).strip().rstrip(',.')
                parsed_date = parse_date(date_str)
                
                records.append({
                    "user_id": user_id,
                    "username": username,
                    "first_name": None,
                    "last_name": None,
                    "rilevato_il": parsed_date or datetime.now(),
                    "fonte": "sangmata"
                })
                matched = True
                break
        
        if matched:
            continue
        
        # Pattern per nomi
        # Formato: Name: Mario Rossi — 15 Jan 2024
        # Formato: 👤 Mario Rossi - 2024-01-15
        name_patterns = [
            r'[Nn]ame[:\s]+(.+?)\s*[—\-–]\s*([\d\w\s\-\/\.,]+)',
            r'[Nn]ome[:\s]+(.+?)\s*[—\-–]\s*([\d\w\s\-\/\.,]+)',
            r'👤\s*(.+?)\s*[—\-–]\s*([\d\w\s\-\/\.,]+)',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, line)
            if match:
                full_name = match.group(1).strip()
                date_str = match.group(2).strip().rstrip(',.')
                
                # Evita di catturare username come nomi
                if full_name.startswith('@'):
                    continue
                
                parts = full_name.split(' ', 1)
                first_name = parts[0] if parts else None
                last_name = parts[1] if len(parts) > 1 else None
                
                parsed_date = parse_date(date_str)
                
                records.append({
                    "user_id": user_id,
                    "username": None,
                    "first_name": first_name,
                    "last_name": last_name,
                    "rilevato_il": parsed_date or datetime.now(),
                    "fonte": "sangmata"
                })
                break
    
    return records


def save_records_to_db(records):
    """Salva i record nel database"""
    if not records:
        return 0
    
    conn = get_db_connection()
    cursor = conn.cursor()
    saved = 0
    
    try:
        for r in records:
            try:
                cursor.execute("""
                    INSERT INTO storico_username 
                    (user_id, username, first_name, last_name, rilevato_il, fonte)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE fonte = VALUES(fonte)
                """, (
                    r["user_id"],
                    r["username"],
                    r["first_name"],
                    r["last_name"],
                    r["rilevato_il"],
                    r["fonte"]
                ))
                saved += 1
            except Exception as e:
                logger.warning(f"Errore inserimento record: {e}")
        
        conn.commit()
        logger.info(f"Salvati {saved} record storico username per user {records[0]['user_id']}")
        
    finally:
        cursor.close()
        conn.close()
    
    return saved


async def query_sangmata(client, user_id):
    """Interroga SangMata per lo storico di un utente"""
    try:
        bot = await client.get_entity(SANGMATA_BOT)
        
        # Invia richiesta con l'ID utente
        await client.send_message(bot, str(user_id))
        logger.info(f"Inviata richiesta a SangMata per user {user_id}")
        
        # Attendi risposta (SangMata può essere lento)
        await asyncio.sleep(5)
        
        # Leggi le ultime risposte dal bot
        messages = await client.get_messages(bot, limit=10)
        
        for msg in messages:
            if msg.sender_id == bot.id and msg.text:
                text = msg.text
                # Verifica che sia la risposta giusta
                if (str(user_id) in text or 
                    '@' in text or 
                    'name' in text.lower() or
                    'history' in text.lower() or
                    'storico' in text.lower() or
                    'username' in text.lower()):
                    logger.info(f"Ricevuta risposta da SangMata: {len(text)} caratteri")
                    return text
        
        logger.warning(f"Nessuna risposta valida da SangMata per user {user_id}")
        return None
        
    except Exception as e:
        logger.error(f"Errore query SangMata per user {user_id}: {e}")
        return None


async def process_sangmata_request(user_id):
    """Processa una richiesta SangMata"""
    REQUEST_STATUS[user_id] = {
        "status": "processing", 
        "message": "⏳ Interrogazione SangMata in corso..."
    }
    
    client = None
    
    try:
        if not API_ID or not API_HASH:
            REQUEST_STATUS[user_id] = {
                "status": "error", 
                "message": "❌ Credenziali Telegram non configurate"
            }
            return
        
        # Verifica che esista il file di sessione
        session_path = Path(str(SESSION_FILE) + ".session")
        if not session_path.exists():
            REQUEST_STATUS[user_id] = {
                "status": "error", 
                "message": "❌ Sessione Telegram non trovata. Esegui prima: python importer_service.py --auth"
            }
            return
        
        # Crea client usando la sessione esistente
        client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            REQUEST_STATUS[user_id] = {
                "status": "error", 
                "message": "❌ Sessione non autorizzata. Esegui: python importer_service.py --auth"
            }
            return
        
        # Query a SangMata
        response = await query_sangmata(client, user_id)
        
        if response:
            records = parse_sangmata_response(response, user_id)
            saved = save_records_to_db(records)
            
            if saved > 0:
                REQUEST_STATUS[user_id] = {
                    "status": "success",
                    "message": f"✅ Trovati e salvati {saved} record",
                    "count": saved
                }
            else:
                REQUEST_STATUS[user_id] = {
                    "status": "not_found",
                    "message": "📭 Nessuno storico trovato su SangMata per questo utente"
                }
        else:
            REQUEST_STATUS[user_id] = {
                "status": "not_found",
                "message": "📭 Nessuna risposta da SangMata"
            }
            
    except Exception as e:
        logger.error(f"Errore processo SangMata: {e}", exc_info=True)
        REQUEST_STATUS[user_id] = {
            "status": "error",
            "message": f"❌ Errore: {str(e)}"
        }
    finally:
        if client:
            try:
                await client.disconnect()
            except:
                pass


def worker_thread():
    """Thread worker per processare le richieste in background"""
    while True:
        try:
            user_id = request_queue.get(timeout=1)
            logger.info(f"Worker: processo richiesta per user {user_id}")
            
            # Esegui la coroutine
            asyncio.run(process_sangmata_request(user_id))
            
            request_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Errore worker SangMata: {e}")


def queue_sangmata_request(user_id):
    """Aggiunge una richiesta alla coda"""
    REQUEST_STATUS[user_id] = {"status": "queued", "message": "⏳ In coda..."}
    request_queue.put(user_id)
    logger.info(f"Richiesta SangMata per user {user_id} aggiunta alla coda")


def get_request_status(user_id):
    """Ritorna lo stato di una richiesta"""
    return REQUEST_STATUS.get(user_id, {"status": "unknown", "message": "Stato sconosciuto"})


# =========================
# Avvia il worker thread all'import del modulo
# =========================
_worker = threading.Thread(target=worker_thread, daemon=True)
_worker.start()
logger.info("SangMata worker thread avviato")