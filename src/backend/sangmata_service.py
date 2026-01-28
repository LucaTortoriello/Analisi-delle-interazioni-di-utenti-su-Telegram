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

SANGMATA_BOT = "SangMata_beta_bot"

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
        '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', 
        '%d %b %Y', '%d %B %Y', '%Y.%m.%d', 
        '%d.%m.%Y', '%b %d, %Y', '%B %d, %Y',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def parse_sangmata_response(text, user_id):
    """
    Parsing della risposta di SangMata dopo comando allhistory.
    """
    records = []
    if not text:
        return records
    
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or any(skip in line.lower() for skip in ['history', 'storico', 'record', '━', '─', 'id:']):
            continue
        
        # Pattern per username (es: 🔹 @username — 15 Jan 2024)
        username_patterns = [
            r'[🔹•\-\*]\s*@(\w+)\s*[—\-–]\s*([\d\w\s\-\/\.,]+)',
            r'@(\w+)\s*\(([\d\-\/\.]+)\)',
            r'@(\w+)\s*[—\-–]\s*([\d\w\s\-\/\.,]+)',
            r'[🔹•\-\*]\s*(\w+)\s*[—\-–]\s*([\d\w\s\-\/\.,]+)',
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
        
        # Pattern per nomi (es: 👤 Nome Cognome - 2024-01-15)
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
    """Salva i record nel database MySQL"""
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
                    r["user_id"], r["username"], r["first_name"],
                    r["last_name"], r["rilevato_il"], r["fonte"]
                ))
                saved += 1
            except Exception as e:
                logger.warning(f"Errore inserimento record: {e}")
        
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    
    return saved


async def query_sangmata(client, user_id):
    """Interroga SangMata usando il comando 'allhistory'"""
    try:
        bot = await client.get_entity(SANGMATA_BOT)
        
        # MODIFICA: Utilizzo del comando 'allhistory' come richiesto
        command = f"allhistory {user_id}"
        await client.send_message(bot, command)
        logger.info(f"Inviato '{command}' a SangMata")
        
        # Attesa per permettere al bot di elaborare lo storico
        await asyncio.sleep(6)
        
        # Legge le ultime risposte
        messages = await client.get_messages(bot, limit=5)
        
        for msg in messages:
            if msg.sender_id == bot.id and msg.text:
                text = msg.text
                if "no records" in text.lower() or "nessun record" in text.lower():
                    return None
                if any(k in text.lower() for k in ['@', 'history', 'storico', 'name']):
                    return text
        
        return None
    except Exception as e:
        logger.error(f"Errore query SangMata: {e}")
        return None


async def process_sangmata_request(user_id):
    """Gestisce l'intero processo di richiesta e salvataggio"""
    REQUEST_STATUS[user_id] = {"status": "processing", "message": "⏳ Interrogazione SangMata..."}
    client = None
    
    try:
        session_path = Path(str(SESSION_FILE) + ".session")
        if not session_path.exists():
            REQUEST_STATUS[user_id] = {"status": "error", "message": "❌ Sessione non trovata"}
            return
        
        client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            REQUEST_STATUS[user_id] = {"status": "error", "message": "❌ Sessione non autorizzata"}
            return
        
        response = await query_sangmata(client, user_id)
        
        if response:
            records = parse_sangmata_response(response, user_id)
            saved = save_records_to_db(records)
            
            if saved > 0:
                REQUEST_STATUS[user_id] = {
                    "status": "success", 
                    "message": f"✅ Salvati {saved} record", 
                    "count": saved
                }
            else:
                REQUEST_STATUS[user_id] = {"status": "not_found", "message": "📭 Nessun dato trovato"}
        else:
            REQUEST_STATUS[user_id] = {"status": "not_found", "message": "📭 Nessuna risposta dal bot"}
            
    except Exception as e:
        logger.error(f"Errore processo: {e}")
        REQUEST_STATUS[user_id] = {"status": "error", "message": f"❌ Errore: {str(e)}"}
    finally:
        if client:
            await client.disconnect()


def worker_thread():
    """Thread per processare la coda in background"""
    while True:
        try:
            user_id = request_queue.get(timeout=1)
            asyncio.run(process_sangmata_request(user_id))
            request_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Errore worker: {e}")


def queue_sangmata_request(user_id):
    REQUEST_STATUS[user_id] = {"status": "queued", "message": "⏳ In coda..."}
    request_queue.put(user_id)


def get_request_status(user_id):
    return REQUEST_STATUS.get(user_id, {"status": "unknown", "message": "Sconosciuto"})

# Avvio del thread worker
_worker = threading.Thread(target=worker_thread, daemon=True)
_worker.start()