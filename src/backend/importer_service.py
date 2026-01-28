import asyncio
import datetime
import logging
import mimetypes
import os
import sys
import time
import re
import json
from pathlib import Path
from typing import List, Optional, Tuple

import mysql.connector
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import (
    Channel,
    Chat,
    User,
    MessageEntityMention,
    MessageEntityMentionName,
    MessageEntityUrl,
    MessageEntityTextUrl,
    ChannelParticipantsAdmins,
)

# =========================
# GESTIONE STATO GLOBALE (Per l'API)
# =========================
IMPORT_STATUS = {}

# =========================
# Logging
# =========================
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

file_handler = logging.FileHandler("telethon_import.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# =========================
# Percorsi cartelle
# =========================
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
PHOTOS_DIR = DOWNLOADS_DIR / "profile_photos"
MEDIA_DIR = DOWNLOADS_DIR / "media"
for d in (DOWNLOADS_DIR, PHOTOS_DIR, MEDIA_DIR):
    d.mkdir(parents=True, exist_ok=True)

# =========================
# Config .env
# =========================
def load_any_env() -> None:
    candidates = [
        BASE_DIR / ".env",
        BASE_DIR / "credenzialiDB.env",
        BASE_DIR.parent / "credenzialiDB.env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(dotenv_path=p)
            return

load_any_env()

def env_int(name: str, default: int = 0) -> int:
    v = os.getenv(name)
    try:
        return int(v) if v is not None else default
    except Exception:
        return default

def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "y")

# Credenziali API Telegram
API_ID = env_int("API_ID", 0)
API_HASH = os.getenv("API_HASH", "")

# Config DB
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "analisiutentitelegram")

# Parametri importazione
BATCH_SIZE = env_int("BATCH_SIZE", 2000)
MAX_MEDIA_CONCURRENCY = env_int("MAX_MEDIA_CONCURRENCY", 40)
PROGRESS_EVERY = env_int("PROGRESS_EVERY", 1000)
SKIP_MEDIA = env_bool("SKIP_MEDIA", False)
MAX_MSG = env_int("MAX_MSG", 30000)

# =====================================================
# CONFIGURAZIONE SESSIONE UNICA
# =====================================================
SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "telegram_session")
SESSION_FILE = BASE_DIR / SESSION_NAME

if not API_ID or not API_HASH:
    raise ValueError("API_ID o API_HASH mancanti nel file .env")

# =========================
# Helpers
# =========================
def get_connection():
    conn = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, charset="utf8mb4"
    )
    cur = conn.cursor()
    cur.execute("SET time_zone = '+00:00'")
    cur.close()
    return conn

def to_db_rel(path: Path) -> str:
    p = path.as_posix()
    if "downloads/" in p:
        return "downloads/" + p.split("downloads/", 1)[1]
    rel = path.relative_to(BASE_DIR).as_posix() if path.is_absolute() else p
    return rel if rel.startswith("downloads/") else f"downloads/{rel}"

def guess_ext_from_message(msg) -> str:
    ext = ""
    try:
        if getattr(msg, "file", None):
            mime = msg.file.mime_type
            if mime:
                ext = mimetypes.guess_extension(mime) or ""
                if ext == ".jpe": ext = ".jpg"
            if not ext and getattr(msg.file, "name", None):
                name = msg.file.name
                if isinstance(name, str) and "." in name:
                    ext = "." + name.rsplit(".", 1)[-1]
    except Exception: pass
    return ext or ""

def ensure_utc_naive(dt: datetime.datetime) -> datetime.datetime:
    from datetime import timezone
    if dt is None: return None
    if dt.tzinfo is None: dt_utc = dt.replace(tzinfo=timezone.utc)
    else: dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.replace(tzinfo=None)

def sanitize_filename(name: str, max_length: int = 150) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip().rstrip(".")
    if len(name) > max_length:
        base, ext = os.path.splitext(name)
        name = base[:max_length - len(ext)] + ext
    return name

async def get_channel_by_title(client: TelegramClient, title: str):
    """
    Cerca una chat nei dialoghi per titolo.
    Prova prima match esatto, poi match parziale.
    """
    title_lower = str(title).lower().strip()
    
    # Prima passata: match esatto
    async for dialog in client.iter_dialogs():
        if dialog.title and str(dialog.title).lower().strip() == title_lower:
            return dialog.entity
    
    # Seconda passata: match parziale (il titolo contiene la stringa cercata)
    async for dialog in client.iter_dialogs():
        if dialog.title and title_lower in str(dialog.title).lower():
            return dialog.entity
    
    # Terza passata: la stringa cercata contiene il titolo
    async for dialog in client.iter_dialogs():
        if dialog.title and str(dialog.title).lower() in title_lower:
            return dialog.entity
    
    return None


async def get_channel_by_username(client: TelegramClient, username: str):
    """
    Cerca una chat nei dialoghi per username.
    """
    username_lower = str(username).lower().strip().lstrip("@")
    
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        entity_username = getattr(entity, "username", None)
        if entity_username and entity_username.lower() == username_lower:
            return entity
    
    return None

async def get_admins_for_chat(client, entity):
    try:
        admins = await client.get_participants(entity, filter=ChannelParticipantsAdmins)
    except Exception:
        return []
    result = []
    for a in admins:
        nome = f"{(a.first_name or '')} {(a.last_name or '')}".strip()
        if not nome and a.username: nome = f"@{a.username}"
        result.append({"id": a.id, "nome": nome or None, "username": a.username or None})
    return result

async def convert_entities_to_clickable(text: str, entities: Optional[List] = None, client: Optional[TelegramClient] = None, utenti_batch: Optional[List] = None, foto_cache: Optional[set] = None) -> str:
    if not text or not entities: return text or ""
    result = text
    for entity in reversed(entities):
        start, end = entity.offset, entity.offset + entity.length
        try:
            if isinstance(entity, MessageEntityMention):
                username = result[start + 1:end]
                link = f'<a href="https://t.me/{username}">@{username}</a>'
                result = result[:start] + link + result[end:]
            elif isinstance(entity, MessageEntityMentionName):
                if client is not None:
                    try:
                        user = await client.get_entity(entity.user_id)
                        href = f'https://t.me/{user.username}' if user.username else f'tg://user?id={user.id}'
                        display = result[start:end]
                        link = f'<a href="{href}">{display}</a>'
                        result = result[:start] + link + result[end:]
                        if utenti_batch is not None and foto_cache is not None:
                            nome = f"{user.first_name or ''} {user.last_name or ''}".strip() or (f"@{user.username}" if user.username else None)
                            foto_path_db = None
                            if user.id not in foto_cache and not getattr(user, "bot", False) and getattr(user, "photo", None):
                                foto_filename = PHOTOS_DIR / f"{user.id}.jpg"
                                if not foto_filename.exists():
                                    await client.download_profile_photo(user, file=str(foto_filename))
                                if foto_filename.exists():
                                    foto_path_db = to_db_rel(foto_filename)
                                    foto_cache.add(user.id)
                            utenti_batch.append((user.id, nome, user.username, foto_path_db))
                    except Exception: pass
            elif isinstance(entity, MessageEntityUrl):
                url = result[start:end]
                link = f'<a href="{url}">{url}</a>'
                result = result[:start] + link + result[end:]
            elif isinstance(entity, MessageEntityTextUrl):
                url = entity.url
                display = result[start:end]
                link = f'<a href="{url}">{display}</a>'
                result = result[:start] + link + result[end:]
        except Exception: pass
    return result

async def download_media_by_id(client: TelegramClient, item: Tuple[int, int, Path], sem: asyncio.Semaphore) -> None:
    chat_id, msg_id, filename = item
    MAX_SIZE = 200 * 1024 * 1024
    ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".mp4"}
    async with sem:
        try:
            msg = await client.get_messages(chat_id, ids=msg_id)
            if not msg or not getattr(msg, "file", None): return
            ext = (Path(filename).suffix or "").lower()
            if ext not in ALLOWED_EXT: return
            size = getattr(msg.file, "size", 0) or 0
            if size > MAX_SIZE: return
            if not filename.exists():
                await client.download_media(msg, file=str(filename))
        except Exception: pass


# =====================================================
# FUNZIONE PER VERIFICARE SE LA SESSIONE È AUTENTICATA
# =====================================================
def is_session_authenticated() -> bool:
    """
    Verifica se esiste un file di sessione valido.
    Ritorna True se la sessione sembra esistere, False altrimenti.
    """
    session_path = Path(str(SESSION_FILE) + ".session")
    return session_path.exists()


# =====================================================
# SCRIPT DI AUTENTICAZIONE (da eseguire una sola volta)
# =====================================================
async def authenticate_session():
    """
    Esegui questo script UNA SOLA VOLTA da terminale per creare la sessione.
    Dopo l'autenticazione, la sessione sarà riutilizzabile per tutte le scansioni.
    
    Uso: python importer_service.py --auth
    """
    print("=" * 60)
    print("AUTENTICAZIONE TELEGRAM")
    print("=" * 60)
    print(f"File sessione: {SESSION_FILE}.session")
    print()
    
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    
    try:
        await client.connect()
        
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ Sessione già autenticata!")
            print(f"   Account: {me.first_name} {me.last_name or ''}")
            print(f"   Username: @{me.username}" if me.username else "   Username: (nessuno)")
            print(f"   ID: {me.id}")
            return True
        
        # Richiedi numero di telefono
        phone = input("Inserisci il numero di telefono (con prefisso, es: +39...): ").strip()
        
        if not phone:
            print("❌ Numero di telefono non inserito.")
            return False
        
        # Invia richiesta codice
        await client.send_code_request(phone)
        print(f"📱 Codice inviato a {phone}")
        
        # Richiedi codice
        code = input("Inserisci il codice ricevuto: ").strip()
        
        try:
            await client.sign_in(phone, code)
        except Exception as e:
            if "Two-step verification" in str(e) or "password" in str(e).lower():
                # 2FA abilitato
                password = input("Inserisci la password 2FA: ").strip()
                await client.sign_in(password=password)
            else:
                raise e
        
        me = await client.get_me()
        print()
        print("=" * 60)
        print("✅ AUTENTICAZIONE COMPLETATA!")
        print("=" * 60)
        print(f"   Account: {me.first_name} {me.last_name or ''}")
        print(f"   Username: @{me.username}" if me.username else "   Username: (nessuno)")
        print(f"   ID: {me.id}")
        print()
        print(f"📁 Sessione salvata in: {SESSION_FILE}.session")
        print("   Ora puoi avviare l'applicazione normalmente.")
        return True
        
    except Exception as e:
        print(f"❌ Errore durante l'autenticazione: {e}")
        return False
    finally:
        await client.disconnect()


# =====================================================
# CLIENT PER TASK (nuovo client per ogni import)
# =====================================================
# NOTA: Non usiamo più singleton perché Flask usa thread separati
# e asyncio.run() crea un nuovo event loop ogni volta.
# Ogni task crea il proprio client e lo disconnette alla fine.

async def create_telegram_client() -> Optional[TelegramClient]:
    """
    Crea un nuovo client Telegram autenticato.
    Ogni task deve creare il proprio client e disconnetterlo alla fine.
    """
    # Verifica che il file di sessione esista
    if not is_session_authenticated():
        logger.error("File di sessione non trovato. Esegui prima: python importer_service.py --auth")
        return None
    
    # Crea nuovo client
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            logger.error("Sessione non autorizzata. Esegui: python importer_service.py --auth")
            await client.disconnect()
            return None
        
        me = await client.get_me()
        logger.info(f"Client Telegram connesso come: {me.first_name} (@{me.username or 'N/A'})")
        return client
        
    except Exception as e:
        logger.error(f"Errore connessione Telegram: {e}")
        try:
            await client.disconnect()
        except:
            pass
        return None


# Mantieni questa funzione per compatibilità con check_session_status
async def get_telegram_client() -> Optional[TelegramClient]:
    """
    Wrapper per compatibilità. Crea un nuovo client.
    ATTENZIONE: Il chiamante deve disconnettere il client!
    """
    return await create_telegram_client()


# =====================================================
# CORE LOGIC (CORRETTO)
# =====================================================
async def run_import_task(target: str, mode: str = "incrementale"):
    """
    Funzione principale che esegue l'importazione per un singolo target.
    Usa la sessione unica già autenticata.
    """
    global IMPORT_STATUS

    target_key = str(target)
    original_target = str(target).strip()
    
    IMPORT_STATUS[target_key] = {"status": "running", "progress": "Avvio connessione Telegram..."}

    conn = None
    client = None
    
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        IS_STORICO = (mode == "storico")

        # =====================================================
        # SE IL TARGET È UN ID NUMERICO, RECUPERA IL NOME DAL DB
        # =====================================================
        search_target = original_target
        
        if re.match(r'^-?\d+$', original_target):
            chat_id_num = int(original_target)
            logger.info(f"Target è un ID numerico ({chat_id_num}), cerco il nome nel DB...")
            
            cursor.execute(
                "SELECT nome_chat, username FROM chat WHERE id_chat = %s OR id_chat = %s",
                (chat_id_num, -chat_id_num)
            )
            row = cursor.fetchone()
            
            if row:
                # Priorità: username > nome_chat
                if row.get("username"):
                    search_target = row["username"]
                    logger.info(f"Trovato username nel DB: '{search_target}' per ID {chat_id_num}")
                elif row.get("nome_chat"):
                    search_target = row["nome_chat"]
                    logger.info(f"Trovato nome nel DB: '{search_target}' per ID {chat_id_num}")
                IMPORT_STATUS[target_key]["progress"] = f"Cerco chat: {search_target}..."
            else:
                logger.warning(f"ID {chat_id_num} non trovato nel DB, uso ID come fallback")

        # =====================================================
        # CREA UN NUOVO CLIENT PER QUESTO TASK
        # =====================================================
        client = await create_telegram_client()
        
        if client is None:
            IMPORT_STATUS[target_key] = {
                "status": "error",
                "progress": "Sessione Telegram non autenticata. Esegui: python importer_service.py --auth"
            }
            logger.error("Impossibile creare client Telegram autenticato")
            return

        sem = asyncio.Semaphore(MAX_MEDIA_CONCURRENCY)

        IMPORT_STATUS[target_key]["progress"] = f"Ricerca chat: {search_target}..."

        # =====================================================
        # RICERCA ENTITÀ (per username/nome, NON per ID)
        # =====================================================
        entity = None
        target_str = str(search_target).strip()
        
        # Rimuovi eventuale @ iniziale
        if target_str.startswith("@"):
            target_str = target_str[1:]
        
        logger.info(f"Inizio ricerca per: '{target_str}'")
        
        # STRATEGIA 1: Cerca per username (es: "PsychonautWiki" o "psychonautwiki_music")
        if not re.match(r'^-?\d+$', target_str):
            try:
                # Prova come username diretto
                entity = await client.get_entity(target_str)
                logger.info(f"Trovato per username: {target_str}")
            except Exception as e:
                logger.warning(f"get_entity(username) fallito per '{target_str}': {e}")
        
        # STRATEGIA 2: Cerca nei dialoghi per titolo/nome
        if entity is None:
            logger.info(f"Cerco nei dialoghi per titolo: {target_str}")
            entity = await get_channel_by_title(client, target_str)
            if entity:
                logger.info(f"Trovato per titolo nei dialoghi: {getattr(entity, 'title', target_str)}")
        
        # STRATEGIA 3: Se il target originale era un ID numerico, cerca nei dialoghi per ID
        if entity is None and re.match(r'^-?\d+$', original_target):
            target_id = int(original_target)
            logger.info(f"Cerco nei dialoghi per ID: {target_id}")
            async for dialog in client.iter_dialogs():
                if dialog.entity.id == target_id or dialog.entity.id == -target_id or dialog.entity.id == abs(target_id):
                    entity = dialog.entity
                    logger.info(f"Trovato per ID nei dialoghi: {getattr(entity, 'title', target_id)}")
                    break
        
        # STRATEGIA 4: Ultimo tentativo con get_entity su ID (funziona solo se sei nel gruppo)
        if entity is None and re.match(r'^-?\d+$', original_target):
            try:
                target_id = int(original_target)
                # Prova vari formati di ID
                for test_id in [target_id, -target_id, -int(f"100{abs(target_id)}")]:
                    try:
                        entity = await client.get_entity(test_id)
                        logger.info(f"Trovato per ID diretto: {test_id}")
                        break
                    except Exception as e:
                        logger.debug(f"Tentativo con ID {test_id} fallito: {e}")
                        continue
            except Exception as e:
                logger.warning(f"get_entity(id) fallito: {e}")

        if not entity:
            # Costruisci messaggio di errore dettagliato
            if search_target != original_target:
                error_msg = (
                    f"Chat non trovata. Cercato: '{search_target}' (da ID {original_target}). "
                    f"Verifica di essere iscritto al gruppo/canale."
                )
            else:
                error_msg = (
                    f"Chat '{target_str}' non trovata. "
                    f"Assicurati di essere iscritto al gruppo/canale."
                )
            IMPORT_STATUS[target_key] = {"status": "error", "progress": error_msg}
            logger.error(f"Target '{original_target}' (search: '{search_target}') non trovato.")
            return

        chat_id = entity.id
        nome_chat = getattr(entity, "title", None) or getattr(entity, "username", str(chat_id))

        IMPORT_STATUS[target_key]["progress"] = f"Trovato: {nome_chat}. Scarico info admin..."

        admin_list = await get_admins_for_chat(client, entity)

        admin_json_path = os.path.join(BASE_DIR, "admins.json")
        data_admins = {}
        if os.path.exists(admin_json_path):
            try:
                with open(admin_json_path, "r", encoding="utf-8") as f:
                    data_admins = json.load(f)
            except:
                data_admins = {}
        data_admins[str(chat_id)] = admin_list
        with open(admin_json_path, "w", encoding="utf-8") as f:
            json.dump(data_admins, f, ensure_ascii=False, indent=2)

        # =====================================================
        # SALVA CHAT CON USERNAME
        # =====================================================
        ultima_scansione = ensure_utc_naive(datetime.datetime.now(datetime.timezone.utc))
        chat_username = getattr(entity, "username", None)
        
        cursor.execute("""
            INSERT INTO chat (id_chat, nome_chat, username, ultima_scansione) 
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                nome_chat=VALUES(nome_chat), 
                username=VALUES(username),
                ultima_scansione=VALUES(ultima_scansione)
        """, (chat_id, nome_chat, chat_username, ultima_scansione))
        conn.commit()

        processed = 0
        utenti_batch, messaggi_batch = [], []
        foto_cache = set()
        media_queue: List[Tuple[int, int, Path]] = []
        start_time = time.time()

        if not IS_STORICO:
            cursor.execute("SELECT MAX(id_messaggio) AS max_id FROM messaggi WHERE id_chat=%s", (chat_id,))
            res = cursor.fetchone()
            last_saved_id = res["max_id"] if res and res.get("max_id") is not None else 0

            IMPORT_STATUS[target_key]["progress"] = f"Incrementale da ID {last_saved_id}..."
        else:
            last_saved_id = 0
            IMPORT_STATUS[target_key]["progress"] = f"Storico completo (Max {MAX_MSG})..."

        async for message in client.iter_messages(entity, reverse=IS_STORICO, limit=MAX_MSG):

            if not IS_STORICO and isinstance(last_saved_id, int) and message.id <= last_saved_id:
                break

            if not message or (message.sender_id is None and not message.action):
                continue

            if message.sender_id:
                try:
                    cursor.execute("INSERT IGNORE INTO utenti (id,data_importazione) VALUES (%s,UTC_TIMESTAMP())",
                                   (message.sender_id,))
                except:
                    pass

            sender = message.sender
            nome_utente, username_u, foto_path_db = None, None, None

            if sender:
                if isinstance(sender, (Channel, Chat)):
                    nome_utente = getattr(sender, "title", None)
                    username_u = getattr(sender, "username", None)
                elif isinstance(sender, User):
                    first = getattr(sender, "first_name", "") or ""
                    last = getattr(sender, "last_name", "") or ""
                    nome_utente = (f"{first} {last}").strip()
                    username_u = getattr(sender, "username", None)

                if not nome_utente and username_u:
                    nome_utente = f"@{username_u}"

                if sender.id not in foto_cache and getattr(sender, "photo", None):
                    foto_filename = PHOTOS_DIR / f"{sender.id}.jpg"
                    if not foto_filename.exists():
                        try:
                            await client.download_profile_photo(sender, file=str(foto_filename))
                        except:
                            pass
                    if foto_filename.exists():
                        foto_path_db = to_db_rel(foto_filename)
                        foto_cache.add(sender.id)
                utenti_batch.append((sender.id, nome_utente, username_u, foto_path_db))

            elif getattr(message, "sender_id", None):
                utenti_batch.append((message.sender_id, None, None, None))

            file_path_db, media_type = None, None
            if message.media:
                media_type = type(message.media).__name__
                ext = (guess_ext_from_message(message) or ".bin").lower()
                allowed = {".pdf", ".jpg", ".jpeg", ".mp4"}
                size = getattr(message.file, "size", 0) or 0
                if ext in allowed and size <= 200 * 1024 * 1024:
                    base_name = sanitize_filename(f"{chat_id}_{message.id}{ext}")
                    media_filename = MEDIA_DIR / base_name
                    if media_filename.exists():
                        media_filename = MEDIA_DIR / f"{chat_id}_{message.id}_{int(time.time())}{ext}"
                    file_path_db = to_db_rel(media_filename)
                    if not SKIP_MEDIA:
                        media_queue.append((chat_id, message.id, media_filename))

            raw_text = message.text or ""
            clickable_text = await convert_entities_to_clickable(raw_text, message.entities, client, utenti_batch, foto_cache)
            dt_store = ensure_utc_naive(message.date)

            messaggi_batch.append((
                chat_id, message.id, message.sender_id, clickable_text, dt_store, file_path_db, media_type,
                message.reply_to.reply_to_msg_id if message.is_reply else None, None,
                type(message.action).__name__ if message.action else None
            ))

            processed += 1

            if processed % 50 == 0:
                IMPORT_STATUS[target_key]["progress"] = f"Scaricati {processed} messaggi..."

            if processed % BATCH_SIZE == 0:
                if utenti_batch:
                    cursor.executemany("""
                        INSERT INTO utenti (id, nome, username, foto_path, data_importazione)
                        VALUES (%s, %s, %s, %s, UTC_TIMESTAMP())
                        ON DUPLICATE KEY UPDATE nome=VALUES(nome), username=VALUES(username), foto_path=VALUES(foto_path)
                    """, utenti_batch)
                    utenti_batch.clear()

                if messaggi_batch:
                    cursor.executemany("""
                        INSERT INTO messaggi (id_chat,id_messaggio,id_autore,testo,data_invio,file_path,media_type,reply_to_msg_id,reply_to_user_id,tipo_evento)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE testo=VALUES(testo), file_path=VALUES(file_path)
                    """, messaggi_batch)
                    messaggi_batch.clear()

                conn.commit()

        if utenti_batch:
            cursor.executemany("""
                INSERT INTO utenti (id, nome, username, foto_path, data_importazione)
                VALUES (%s, %s, %s, %s, UTC_TIMESTAMP())
                ON DUPLICATE KEY UPDATE nome=VALUES(nome), username=VALUES(username), foto_path=VALUES(foto_path)
            """, utenti_batch)

        if messaggi_batch:
            cursor.executemany("""
                INSERT INTO messaggi (id_chat,id_messaggio,id_autore,testo,data_invio,file_path,media_type,reply_to_msg_id,reply_to_user_id,tipo_evento)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE testo=VALUES(testo), file_path=VALUES(file_path)
            """, messaggi_batch)

        conn.commit()

        if not SKIP_MEDIA and media_queue:
            IMPORT_STATUS[target_key]["progress"] = f"Download {len(media_queue)} media..."
            tasks = [asyncio.create_task(download_media_by_id(client, item, sem)) for item in media_queue]
            await asyncio.gather(*tasks)

        elapsed = time.time() - start_time
        IMPORT_STATUS[target_key] = {
            "status": "done", 
            "progress": f"✅ Completato! {processed} messaggi in {elapsed:.1f}s"
        }
        logger.info(f"Import completato per '{target}': {processed} messaggi in {elapsed:.1f}s")

    except Exception as e:
        logger.error(f"Errore Import: {e}", exc_info=True)
        IMPORT_STATUS[target_key] = {"status": "error", "progress": f"Errore: {str(e)}"}

    finally:
        if conn:
            conn.close()
        # Disconnetti il client Telegram
        if client:
            try:
                await client.disconnect()
                logger.info("Client Telegram disconnesso")
            except Exception as e:
                logger.warning(f"Errore disconnessione client: {e}")


def start_import_process(target, mode="incrementale"):
    """Entry point sincrono per il thread Flask"""
    asyncio.run(run_import_task(target, mode))


# =====================================================
# VERIFICA STATO SESSIONE (per API)
# =====================================================
async def check_session_status() -> dict:
    """
    Verifica lo stato della sessione Telegram.
    Restituisce un dizionario con lo stato.
    """
    if not is_session_authenticated():
        return {
            "authenticated": False,
            "message": "Nessuna sessione trovata. Esegui: python importer_service.py --auth"
        }
    
    client = await create_telegram_client()
    if client is None:
        return {
            "authenticated": False,
            "message": "Sessione non valida o scaduta. Esegui: python importer_service.py --auth"
        }
    
    try:
        me = await client.get_me()
        return {
            "authenticated": True,
            "user": {
                "id": me.id,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "username": me.username,
                "phone": me.phone
            },
            "message": f"Connesso come {me.first_name}"
        }
    except Exception as e:
        return {
            "authenticated": False,
            "message": f"Errore verifica sessione: {str(e)}"
        }
    finally:
        # Disconnetti sempre il client
        try:
            await client.disconnect()
        except:
            pass


def get_session_status_sync() -> dict:
    """Versione sincrona per Flask"""
    return asyncio.run(check_session_status())


# =====================================================
# MAIN (per autenticazione da CLI)
# =====================================================
async def list_dialogs():
    """
    Lista tutti i dialoghi (chat/gruppi/canali) disponibili.
    Utile per debug e per trovare il nome corretto da usare.
    
    Uso: python importer_service.py --list
    """
    client = await create_telegram_client()
    if not client:
        print("❌ Sessione non autenticata. Esegui prima: python importer_service.py --auth")
        return
    
    try:
        print("=" * 80)
        print("ELENCO DIALOGHI DISPONIBILI")
        print("=" * 80)
        print(f"{'ID':<15} {'Tipo':<12} {'Username':<25} {'Nome'}")
        print("-" * 80)
        
        count = 0
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            entity_type = type(entity).__name__
            username = getattr(entity, "username", "") or ""
            title = dialog.title or getattr(entity, "first_name", "") or str(entity.id)
            
            # Formatta tipo
            if entity_type == "Channel":
                if getattr(entity, "megagroup", False):
                    entity_type = "Supergruppo"
                else:
                    entity_type = "Canale"
            elif entity_type == "Chat":
                entity_type = "Gruppo"
            elif entity_type == "User":
                entity_type = "Utente"
            
            print(f"{entity.id:<15} {entity_type:<12} @{username:<24} {title}")
            count += 1
            
            if count >= 100:  # Limita a 100 per non sovraccaricare
                print(f"\n... e altri dialoghi (mostrati i primi 100)")
                break
        
        print("-" * 80)
        print(f"Totale mostrati: {count}")
        print("\nUsa il NOME o lo USERNAME (senza @) per avviare la scansione.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--auth":
        # Modalità autenticazione
        asyncio.run(authenticate_session())
    elif len(sys.argv) > 1 and sys.argv[1] == "--status":
        # Verifica stato sessione
        status = asyncio.run(check_session_status())
        print(json.dumps(status, indent=2, ensure_ascii=False))
    elif len(sys.argv) > 1 and sys.argv[1] == "--list":
        # Lista tutti i dialoghi
        asyncio.run(list_dialogs())
    else:
        print("Uso:")
        print("  python importer_service.py --auth    # Autentica la sessione Telegram")
        print("  python importer_service.py --status  # Verifica stato sessione")
        print("  python importer_service.py --list    # Lista tutti i gruppi/canali disponibili")
        print()
        print("Dopo l'autenticazione, avvia l'applicazione Flask normalmente.")