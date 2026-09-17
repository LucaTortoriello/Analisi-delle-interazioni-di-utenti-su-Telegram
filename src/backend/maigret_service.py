"""
Servizio per interrogare Maigret OSINT Bot (@osint_maigret_bot) e salvare i report HTML.
"""

import asyncio
import os
import threading
import queue
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

MAIGRET_BOT = "osint_maigret_bot"

# Cartella per salvare i report HTML
REPORTS_DIR = BASE_DIR / "osint_reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Coda e stato delle richieste
request_queue = queue.Queue()
REQUEST_STATUS = {}


async def query_maigret(client, username):
    """Interroga Maigret Bot per un username e salva il report HTML"""
    try:
        bot = await client.get_entity(MAIGRET_BOT)
        
        # Invia l'username al bot
        await client.send_message(bot, username)
        logger.info(f"Inviata richiesta a Maigret per username '{username}'")
        
        # Attesa iniziale - il bot deve elaborare
        await asyncio.sleep(30)
        
        # Parametri di attesa
        max_wait = 180  # 3 minuti max
        check_interval = 15  # controlla ogni 15 secondi
        elapsed = 0
        
        while elapsed < max_wait:
            # Leggi gli ultimi messaggi dal bot
            messages = await client.get_messages(bot, limit=10)
            
            for msg in messages:
                if msg.sender_id == bot.id and msg.document:
                    # Cerca il file HTML
                    file_name = None
                    for attr in msg.document.attributes:
                        if hasattr(attr, 'file_name'):
                            file_name = attr.file_name
                            break
                    
                    if file_name and file_name.endswith('.html'):
                        # Verifica che sia il report giusto (contiene l'username)
                        if username.lower() in file_name.lower():
                            # Salva il file nella cartella reports
                            report_path = REPORTS_DIR / file_name
                            await client.download_media(msg, str(report_path))
                            logger.info(f"Salvato report: {report_path}")
                            return str(report_path)
            
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            logger.info(f"Attesa Maigret... {elapsed}/{max_wait} secondi")
        
        logger.warning(f"Timeout attesa risposta Maigret per '{username}'")
        return None
        
    except Exception as e:
        logger.error(f"Errore query Maigret per username '{username}': {e}")
        return None


async def process_maigret_request(username):
    """Processa una richiesta Maigret"""
    REQUEST_STATUS[username] = {
        "status": "processing", 
        "message": "⏳ Interrogazione Maigret OSINT in corso (può richiedere 1-2 minuti)..."
    }
    
    client = None
    
    try:
        if not API_ID or not API_HASH:
            REQUEST_STATUS[username] = {
                "status": "error", 
                "message": "❌ Credenziali Telegram non configurate"
            }
            return
        
        session_path = Path(str(SESSION_FILE) + ".session")
        if not session_path.exists():
            REQUEST_STATUS[username] = {
                "status": "error", 
                "message": "❌ Sessione Telegram non trovata. Esegui prima: python importer_service.py --auth"
            }
            return
        
        client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            REQUEST_STATUS[username] = {
                "status": "error", 
                "message": "❌ Sessione non autorizzata. Esegui: python importer_service.py --auth"
            }
            return
        
        # Query a Maigret - ritorna il path del file salvato
        report_path = await query_maigret(client, username)
        
        if report_path:
            REQUEST_STATUS[username] = {
                "status": "success",
                "message": "✅ Report OSINT generato con successo",
                "report_file": os.path.basename(report_path)
            }
        else:
            REQUEST_STATUS[username] = {
                "status": "not_found",
                "message": "📭 Nessuna risposta da Maigret o timeout"
            }
            
    except Exception as e:
        logger.error(f"Errore processo Maigret: {e}", exc_info=True)
        REQUEST_STATUS[username] = {
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
            username = request_queue.get(timeout=1)
            logger.info(f"Worker: processo richiesta OSINT per username '{username}'")
            
            # Esegui la coroutine
            asyncio.run(process_maigret_request(username))
            
            request_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Errore worker Maigret: {e}")


def queue_maigret_request(username):
    """Aggiunge una richiesta alla coda"""
    REQUEST_STATUS[username] = {"status": "queued", "message": "⏳ In coda..."}
    request_queue.put(username)
    logger.info(f"Richiesta OSINT per username '{username}' aggiunta alla coda")


def get_request_status(username):
    """Ritorna lo stato di una richiesta"""
    return REQUEST_STATUS.get(username, {"status": "unknown", "message": "Stato sconosciuto"})


def get_report_path(username):
    """Ritorna il path del report se esiste"""
    # Cerca file che contengono l'username
    for f in REPORTS_DIR.glob(f"*{username}*.html"):
        return str(f)
    # Cerca anche con pattern report_username.html
    report_file = REPORTS_DIR / f"report_{username}.html"
    if report_file.exists():
        return str(report_file)
    return None


# =========================
# Avvia il worker thread all'import del modulo
# =========================
_worker = threading.Thread(target=worker_thread, daemon=True)
_worker.start()
logger.info("Maigret OSINT worker thread avviato")