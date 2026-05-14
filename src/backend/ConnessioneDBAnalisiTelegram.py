#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Importer Telegram -> MySQL (Telethon) per progetto '

- Modalità: "incrementale" o "storico"
- Storico = dall'inizio del canale, in ordine crescente 
- Incrementale = solo nuovi messaggi dopo l'ultimo salvato
- Concorrenza sui download media via asyncio
- Le menzioni (@username) e gli URL all'interno del testo vengono convertiti in link cliccabili
- Log progressivo ogni N messaggi
- Opzione SKIP_MEDIA per scansioni veloci senza scaricare media
- FIX: Gestione corretta dei nomi per "Canali collegati" (ID negativi) che scrivono nei gruppi.
- FIX: Salvataggio username della chat nel DB

"""

import asyncio
import datetime
import logging
import mimetypes
import os
import sys
import time
import re
from pathlib import Path
from typing import List, Optional, Tuple

import mysql.connector
from dotenv import load_dotenv
from telethon.sync import TelegramClient
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

async def get_admins_for_chat(client, entity):
    try:
        admins = await client.get_participants(entity, filter=ChannelParticipantsAdmins)
    except Exception:
        return []
    result = []
    for a in admins:
        nome = f"{(a.first_name or '')} {(a.last_name or '')}".strip()
        if not nome and a.username:
            nome = f"@{a.username}"
        result.append({
            "id": a.id,
            "nome": nome or None,
            "username": a.username or None
        })
    return result

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
    """Carica variabili d'ambiente da uno dei file configurati, se esistono."""
    candidates = [
        BASE_DIR / ".env",
        BASE_DIR / "credenzialiDB.env",
        BASE_DIR.parent / "credenzialiDB.env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(dotenv_path=p)
            logger.info(f"Configurazione caricata da: {p}")
            return
    logger.info("Nessun file .env trovato; uso variabili ambiente.")

load_any_env()

def env_int(name: str, default: int = 0) -> int:
    """Restituisce una variabile d'ambiente come intero."""
    v = os.getenv(name)
    try:
        return int(v) if v is not None else default
    except Exception:
        return default

def env_bool(name: str, default: bool = False) -> bool:
    """Restituisce una variabile d'ambiente come booleano."""
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
MAX_MEDIA_CONCURRENCY = env_int("MAX_MEDIA_CONCURRENCY", 40)  # limite download paralleli
PROGRESS_EVERY = env_int("PROGRESS_EVERY", 1000)
SKIP_MEDIA = env_bool("SKIP_MEDIA", True)

# Limite massimo messaggi per chat (parametrizzabile via MAX_MSG)
MAX_MSG = env_int("MAX_MSG", 30000)

# Verifica credenziali API
if not API_ID or not API_HASH:
    raise ValueError("API_ID o API_HASH mancanti. Impostali in .env / credenzialiDB.env.")

# =========================
# Helpers database e utility
# =========================
def get_connection():
    """Apre una connessione MySQL con fuso orario UTC."""
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
    )
    cur = conn.cursor()
    cur.execute("SET time_zone = '+00:00'")
    cur.close()
    return conn

def to_db_rel(path: Path) -> str:
    """Rende un path relativo alla cartella downloads/."""
    p = path.as_posix()
    if "downloads/" in p:
        return "downloads/" + p.split("downloads/", 1)[1]
    rel = path.relative_to(BASE_DIR).as_posix() if path.is_absolute() else p
    return rel if rel.startswith("downloads/") else f"downloads/{rel}"

def guess_ext_from_message(msg) -> str:
    """Prova a dedurre l'estensione file dal mime_type o dal nome."""
    ext = ""
    try:
        if getattr(msg, "file", None):
            mime = msg.file.mime_type
            if mime:
                ext = mimetypes.guess_extension(mime) or ""
                if ext == ".jpe":
                    ext = ".jpg"
            if not ext and getattr(msg.file, "name", None):
                name = msg.file.name
                if isinstance(name, str) and "." in name:
                    ext = "." + name.rsplit(".", 1)[-1]
    except Exception:
        pass
    return ext or ""

def ensure_utc_naive(dt: datetime.datetime) -> datetime.datetime:
    """Converte datetime in UTC naive."""
    from datetime import timezone
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt_utc = dt.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.replace(tzinfo=None)

def sanitize_filename(name: str, max_length: int = 150) -> str:
    """Rimuove caratteri non validi e tronca nomi troppo lunghi."""
    # sostituisce caratteri vietati con "_"
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    # rimuove spazi e punti finali
    name = name.strip().rstrip(".")
    # limita la lunghezza
    if len(name) > max_length:
        base, ext = os.path.splitext(name)
        name = base[:max_length - len(ext)] + ext
    return name

# =========================
# Funzioni utili
# =========================
async def get_channel_by_title(client: TelegramClient, title: str):
    """
    Cerca un canale o gruppo per titolo, utile quando non ha username.
    """
    async for dialog in client.iter_dialogs():
        if dialog.title and dialog.title.lower() == title.lower():
            return dialog.entity
    return None

async def convert_entities_to_clickable(
    text: str,
    entities: Optional[List] = None,
    client: Optional[TelegramClient] = None,
    utenti_batch: Optional[List] = None,
    foto_cache: Optional[set] = None,
) -> str:
    """
    Converte menzioni e link in HTML cliccabili.
    Se trova menzioni dirette, può anche aggiungere utenti al batch.
    """
    if not text or not entities:
        return text or ""

    result = text
    for entity in reversed(entities):
        start, end = entity.offset, entity.offset + entity.length
        try:
            # menzione @username
            if isinstance(entity, MessageEntityMention):
                username = result[start + 1:end]
                link = f'<a href="https://t.me/{username}">@{username}</a>'
                result = result[:start] + link + result[end:]
            # menzione tramite ID
            elif isinstance(entity, MessageEntityMentionName):
                if client is not None:
                    try:
                        user = await client.get_entity(entity.user_id)
                        href = f'https://t.me/{user.username}' if user.username else f'tg://user?id={user.id}'
                        display = result[start:end]
                        link = f'<a href="{href}">{display}</a>'
                        result = result[:start] + link + result[end:]

                        # aggiorna batch utenti con foto profilo se necessario
                        if utenti_batch is not None and foto_cache is not None:
                            nome = f"{user.first_name or ''} {user.last_name or ''}".strip() or (
                                f"@{user.username}" if user.username else None
                            )
                            foto_path_db = None
                            if user.id not in foto_cache and not getattr(user, "bot", False) and getattr(user, "photo", None):
                                foto_filename = PHOTOS_DIR / f"{user.id}.jpg"
                                if not foto_filename.exists():
                                    await client.download_profile_photo(user, file=str(foto_filename))
                                if foto_filename.exists():
                                    foto_path_db = to_db_rel(foto_filename)
                                    foto_cache.add(user.id)
                            utenti_batch.append((user.id, nome, user.username, foto_path_db))
                    except Exception:
                        pass
            # URL semplice
            elif isinstance(entity, MessageEntityUrl):
                url = result[start:end]
                link = f'<a href="{url}">{url}</a>'
                result = result[:start] + link + result[end:]
            # URL con testo
            elif isinstance(entity, MessageEntityTextUrl):
                url = entity.url
                display = result[start:end]
                link = f'<a href="{url}">{display}</a>'
                result = result[:start] + link + result[end:]
        except Exception:
            # eventuali errori vengono ignorati per non bloccare l'import
            pass
    return result

async def download_media_by_id(client: TelegramClient, item: Tuple[int, int, Path], sem: asyncio.Semaphore) -> None:
    """
    Scarica un singolo media se rispetta i criteri di formato e dimensione massima.
    Ammessi: .pdf, .jpg/.jpeg, .mp4. Max size: 200 MB.
    """
    chat_id, msg_id, filename = item
    MAX_SIZE = 200 * 1024 * 1024  # 200 MB in byte
    ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".mp4"}

    async with sem:
        try:
            msg = await client.get_messages(chat_id, ids=msg_id)
            if not msg or not getattr(msg, "file", None):
                return

            # Estensione effettiva
            ext = (Path(filename).suffix or "").lower()
            if ext not in ALLOWED_EXT:
                logger.info(f"[MEDIA] Saltato {filename.name}: estensione non ammessa ({ext})")
                return

            # Dimensione file (se nota)
            size = getattr(msg.file, "size", 0) or 0
            if size > MAX_SIZE:
                size_mb = size / (1024 * 1024)
                logger.info(f"[MEDIA] Saltato {filename.name}: file troppo grande ({size_mb:.1f} MB)")
                return

            # Scarica solo se il file non esiste già
            if not filename.exists():
                await client.download_media(msg, file=str(filename))
                logger.info(f"[MEDIA] Scaricato {filename.name}")
        except Exception as e:
            logger.warning(f"[MEDIA] Download fallito per {filename}: {e}")

async def get_admins_for_chat(client, entity):
    """
    Restituisce gli admin del gruppo/canale come lista di dict:
    [{ id, nome, username }, ...]
    """
    try:
        admins = await client.get_participants(
            entity,
            filter=ChannelParticipantsAdmins
        )
    except Exception:
        return []

    result = []
    for a in admins:
        nome = f"{(a.first_name or '')} {(a.last_name or '')}".strip()
        if not nome and a.username:
            nome = f"@{a.username}"

        result.append({
            "id": a.id,
            "nome": nome or None,
            "username": a.username or None
        })

    return result

# =========================
# Target da scansionare
# =========================
# È possibile modificare questo elenco a seconda dei gruppi/canali da monitorare.
targets = [
"zelenogradskij",
"zelenograd_chat_moskva",
"moskva_zelenograd_ish_kor_rabota",
"moskva_zelenograd_ish_kor_rabota",
"imkarinamorozovaa",
"moskva_ish_xaltura_zelenograd"
]

# =========================
# Import principale
# =========================
async def import_telegram() -> None:
    """
    Punto di ingresso principale: importa messaggi dai target configurati in base alla modalità scelta.
    """
    conn = get_connection()
    cursor = conn.cursor()
    any_success = False

    # scelta modalità
    scelta = input("Come vuoi importare i messaggi? [storico/incrementale]: ").strip().lower()
    if scelta not in ("storico", "incrementale"):
        scelta = "incrementale"
    IS_STORICO = (scelta == "storico")

    logger.info(f"Modalità di importazione scelta: {scelta}")
    logger.info(f"SKIP_MEDIA = {SKIP_MEDIA} | PROGRESS_EVERY = {PROGRESS_EVERY} | MAX_MSG = {MAX_MSG}")

    async with TelegramClient("sessione_telethon", API_ID, API_HASH) as client:
        # semaforo per download media finale
        sem = asyncio.Semaphore(MAX_MEDIA_CONCURRENCY)

        # loop su tutti i target
        for target in targets:
            try:
                # Ottiene l'entità del gruppo/canale
                try:
                    entity = await client.get_entity(target)
                except Exception:
                    entity = await get_channel_by_title(client, target)
                    if not entity:
                        logger.error(f"Target '{target}' non trovato.")
                        continue

                chat_id = entity.id

                # nome_chat deve essere definito PRIMA dell'uso
                nome_chat = getattr(entity, "title", None) or getattr(entity, "username", str(chat_id))
                
                # Recupera lo username della chat (se esiste)
                chat_username = getattr(entity, "username", None)

                # ---- ADMIN EXTRACTION ----
                admin_list = await get_admins_for_chat(client, entity)

                # Save admins into a consolidated JSON file (Option B)
                import json, os

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

                logger.info(f"Admin trovati per {nome_chat}: {len(admin_list)}")

                ultima_scansione = ensure_utc_naive(datetime.datetime.now(datetime.timezone.utc))

                # Inserisce o aggiorna la chat nel DB (con username)
                cursor.execute(
                    """
                    INSERT INTO chat (id_chat, nome_chat, username, ultima_scansione)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        nome_chat = VALUES(nome_chat),
                        username = VALUES(username),
                        ultima_scansione = VALUES(ultima_scansione)
                    """,
                    (chat_id, nome_chat, chat_username, ultima_scansione),
                )
                conn.commit()
                logger.info(f"Scansione in corso: '{nome_chat}' (id={chat_id}, username={chat_username or 'N/A'})")

                processed = 0
                utenti_batch, messaggi_batch = [], []
                foto_cache = set()
                media_queue: List[Tuple[int, int, Path]] = []
                start_time = time.time()

                # recupera ultimo id salvato (incrementale)
                if not IS_STORICO:
                    cursor.execute("SELECT MAX(id_messaggio) FROM messaggi WHERE id_chat=%s", (chat_id,))
                    last_saved_id = cursor.fetchone()[0] or 0
                    logger.info(f"Incrementale: ultimo id salvato = {last_saved_id}")
                else:
                    last_saved_id = 0
                    logger.info(f"Storico: scarico TUTTI i messaggi dall'inizio (max {MAX_MSG}).")

                # iterazione messaggi (con limite MAX_MSG)
                async for message in client.iter_messages(entity, reverse=IS_STORICO, limit=MAX_MSG):
                    if not IS_STORICO and message.id <= last_saved_id:
                        break
                    if not message or (message.sender_id is None and not message.action):
                        continue

                    # =========================
                    # PATCH placeholder utente
                    # =========================
                    if message.sender_id:
                        try:
                            cursor.execute(
                                """
                                INSERT IGNORE INTO utenti (id, nome, username, foto_path, data_importazione)
                                VALUES (%s, NULL, NULL, NULL, UTC_TIMESTAMP())
                                """,
                                (message.sender_id,),
                            )
                            conn.commit()
                        except Exception as e:
                            logger.error(f"Errore inserimento placeholder utente {message.sender_id}: {e}")

                    # =========================
                    # Autore (MODIFICATO per gestire Canali/ID Negativi)
                    # =========================
                    sender = message.sender
                    nome_utente, username_u, foto_path_db = None, None, None
                    
                    if sender:
                        # CASO 1: Canale o Chat (hanno un title)
                        if isinstance(sender, (Channel, Chat)):
                            nome_utente = getattr(sender, "title", None)
                            username_u = getattr(sender, "username", None)
                        
                        # CASO 2: Utente (ha first_name/last_name)
                        elif isinstance(sender, User):
                            first = getattr(sender, "first_name", "") or ""
                            last = getattr(sender, "last_name", "") or ""
                            nome_utente = (f"{first} {last}").strip()
                            username_u = getattr(sender, "username", None)

                        # Fallback per nome vuoto
                        if not nome_utente and username_u:
                            nome_utente = f"@{username_u}"

                        # scarica foto profilo se non già presente (valido per tutti)
                        if sender.id not in foto_cache and getattr(sender, "photo", None):
                            foto_filename = PHOTOS_DIR / f"{sender.id}.jpg"
                            if not foto_filename.exists():
                                try:
                                    await client.download_profile_photo(sender, file=str(foto_filename))
                                except Exception:
                                    pass
                            if foto_filename.exists():
                                foto_path_db = to_db_rel(foto_filename)
                                foto_cache.add(sender.id)

                        utenti_batch.append((sender.id, nome_utente, username_u, foto_path_db))
                    else:
                        # Mittente nullo o sconosciuto
                        if getattr(message, "sender_id", None):
                            utenti_batch.append((message.sender_id, None, None, None))

                    # =========================
                    # Media
                    # =========================
                    file_path_db, media_type = None, None
                    if message.media:
                        media_type = type(message.media).__name__
                        ext = (guess_ext_from_message(message) or ".bin").lower()
                        ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".mp4"}
                        MAX_SIZE = 200 * 1024 * 1024  # 200 MB

                        # Filtra subito i media non ammessi
                        size = getattr(message.file, "size", 0) or 0
                        if ext not in ALLOWED_EXT:
                            logger.debug(f"[SKIP] {ext} non ammesso per messaggio {message.id}")
                            continue
                        if size > MAX_SIZE:
                            logger.debug(f"[SKIP] file troppo grande ({size/1024/1024:.1f} MB) per messaggio {message.id}")
                            continue

                        # Costruisci il percorso sicuro e normalizzato
                        base_name = sanitize_filename(f"{chat_id}_{message.id}{ext}")
                        media_filename = MEDIA_DIR / base_name
                        
                        # Evita collisioni di nome
                        if media_filename.exists():
                            suffix = int(time.time() * 1000) % 100000
                            media_filename = MEDIA_DIR / f"{chat_id}_{message.id}_{suffix}{ext}"

                        file_path_db = to_db_rel(media_filename)

                        if not SKIP_MEDIA:
                            media_queue.append((chat_id, message.id, media_filename))

                        # Normalizza il percorso finale
                        media_filename = Path(str(media_filename).replace("\\", "/"))
                        

                    # =========================
                    # Testo + entità
                    # =========================
                    raw_text = message.text or ""
                    clickable_text = await convert_entities_to_clickable(
                        raw_text, message.entities, client, utenti_batch, foto_cache
                    )

                    dt_store = ensure_utc_naive(message.date)

                    messaggi_batch.append(
                        (
                            chat_id,
                            message.id,
                            message.sender_id,
                            clickable_text,
                            dt_store,
                            file_path_db,
                            media_type,
                            message.reply_to.reply_to_msg_id if message.is_reply else None,
                            None,
                            type(message.action).__name__ if message.action else None,
                        )
                    )

                    processed += 1

                    # =========================
                    # Log progressivo
                    # =========================
                    if processed % PROGRESS_EVERY == 0:
                        elapsed = time.time() - start_time
                        rate = processed / elapsed if elapsed > 0 else 0
                        logger.info(
                            f"[{nome_chat}] Progress: {processed} messaggi — ultimo id {message.id} — {dt_store} — ~{rate:.1f} msg/s"
                        )

                    # =========================
                    # Commit parziale
                    # =========================
                    if processed % BATCH_SIZE == 0:
                        # inserisci batch utenti
                        if utenti_batch:
                            try:
                                cursor.executemany(
                                    """
                                    INSERT INTO utenti (id, nome, username, foto_path, data_importazione)
                                    VALUES (%s, %s, %s, %s, UTC_TIMESTAMP())
                                    ON DUPLICATE KEY UPDATE
                                        nome=VALUES(nome),
                                        username=VALUES(username),
                                        foto_path=VALUES(foto_path)
                                    """,
                                    utenti_batch,
                                )
                                conn.commit()
                            except Exception as e:
                                logger.error(f"Errore inserimento utenti batch: {e}")
                            utenti_batch.clear()

                        # inserisci batch messaggi
                        if messaggi_batch:
                            try:
                                cursor.executemany(
                                    """
                                    INSERT INTO messaggi
                                    (id_chat,id_messaggio,id_autore,testo,data_invio,file_path,media_type,
                                     reply_to_msg_id,reply_to_user_id,tipo_evento)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                    ON DUPLICATE KEY UPDATE
                                        testo=VALUES(testo),
                                        file_path=VALUES(file_path),
                                        media_type=VALUES(media_type),
                                        reply_to_msg_id=VALUES(reply_to_msg_id),
                                        reply_to_user_id=VALUES(reply_to_user_id),
                                        tipo_evento=VALUES(tipo_evento)
                                    """,
                                    messaggi_batch,
                                )
                                conn.commit()
                            except mysql.connector.IntegrityError as e:
                                logger.error(f"IntegrityError batch messaggi — provo inserimenti singoli: {e}")
                                for m in messaggi_batch:
                                    try:
                                        cursor.execute(
                                            """
                                            INSERT INTO messaggi
                                            (id_chat,id_messaggio,id_autore,testo,data_invio,file_path,media_type,
                                             reply_to_msg_id,reply_to_user_id,tipo_evento)
                                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                            ON DUPLICATE KEY UPDATE
                                                testo=VALUES(testo),
                                                file_path=VALUES(file_path),
                                                media_type=VALUES(media_type),
                                                reply_to_msg_id=VALUES(reply_to_msg_id),
                                                reply_to_user_id=VALUES(reply_to_user_id),
                                                tipo_evento=VALUES(tipo_evento)
                                            """,
                                            m,
                                        )
                                        conn.commit()
                                    except mysql.connector.IntegrityError as ee:
                                        logger.error(f"Saltato messaggio {m[1]} per violazione FK: {ee}")
                                    except Exception as ee:
                                        logger.error(f"Errore inserimento singolo messaggio {m[1]}: {ee}")
                            except Exception as e:
                                logger.error(f"Errore inserimento messaggi batch: {e}")
                            messaggi_batch.clear()

                        logger.info(f"[{nome_chat}] Commit parziale — {processed} messaggi")

                # =========================
                # Flush finale
                # =========================
                # flush eventuali batch residui
                if utenti_batch:
                    try:
                        cursor.executemany(
                            """
                            INSERT INTO utenti (id, nome, username, foto_path, data_importazione)
                            VALUES (%s, %s, %s, %s, UTC_TIMESTAMP())
                            ON DUPLICATE KEY UPDATE
                                nome=VALUES(nome),
                                username=VALUES(username),
                                foto_path=VALUES(foto_path)
                            """,
                            utenti_batch,
                        )
                        conn.commit()
                    except Exception as e:
                        logger.error(f"Errore inserimento utenti (finale): {e}")
                    utenti_batch.clear()

                if messaggi_batch:
                    try:
                        cursor.executemany(
                            """
                            INSERT INTO messaggi
                            (id_chat,id_messaggio,id_autore,testo,data_invio,file_path,media_type,
                             reply_to_msg_id,reply_to_user_id,tipo_evento)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON DUPLICATE KEY UPDATE
                                testo=VALUES(testo),
                                file_path=VALUES(file_path),
                                media_type=VALUES(media_type),
                                reply_to_msg_id=VALUES(reply_to_msg_id),
                                reply_to_user_id=VALUES(reply_to_user_id),
                                tipo_evento=VALUES(tipo_evento)
                            """,
                            messaggi_batch,
                        )
                        conn.commit()
                    except mysql.connector.IntegrityError as e:
                        logger.error(f"IntegrityError messaggi (finale) — provo inserimenti singoli: {e}")
                        for m in messaggi_batch:
                            try:
                                cursor.execute(
                                    """
                                    INSERT INTO messaggi
                                    (id_chat,id_messaggio,id_autore,testo,data_invio,file_path,media_type,
                                     reply_to_msg_id,reply_to_user_id,tipo_evento)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                    ON DUPLICATE KEY UPDATE
                                        testo=VALUES(testo),
                                        file_path=VALUES(file_path),
                                        media_type=VALUES(media_type),
                                        reply_to_msg_id=VALUES(reply_to_msg_id),
                                        reply_to_user_id=VALUES(reply_to_user_id),
                                        tipo_evento=VALUES(tipo_evento)
                                    """,
                                    m,
                                )
                                conn.commit()
                            except mysql.connector.IntegrityError as ee:
                                logger.error(f"Saltato messaggio {m[1]} per violazione FK (finale): {ee}")
                            except Exception as ee:
                                logger.error(f"Errore inserimento singolo messaggio (finale) {m[1]}: {ee}")
                    except Exception as e:
                        logger.error(f"Errore inserimento messaggi (finale): {e}")
                    messaggi_batch.clear()

                # commit finale per eventuali dati rimasti
                conn.commit()

                elapsed_total = time.time() - start_time
                rate_total = processed / elapsed_total if elapsed_total > 0 else 0
                logger.info(
                    f"Scansione completata: '{nome_chat}' — nuovi: {processed} — durata {elapsed_total:.1f}s — ~{rate_total:.1f} msg/s"
                )

                # =========================
                # Download dei media accodati
                # =========================
                if not SKIP_MEDIA and media_queue:
                    logger.info(f"[{nome_chat}] Inizio download media: {len(media_queue)} file in coda")
                    # crea task per ogni item accodato
                    tasks = [asyncio.create_task(download_media_by_id(client, item, sem)) for item in media_queue]
                    await asyncio.gather(*tasks)
                    media_queue.clear()

                any_success = True

            except Exception as e:
                # gestione eccezioni generiche per il singolo target
                logger.error(f"❌ Scansione interrotta per '{target}' — {type(e).__name__}: {e}")
                logger.warning(f"Il gruppo '{target}' NON è stato completato, si passa al prossimo.")

        cursor.close()
        conn.close()

    if any_success:
        logger.info("✅ Importazione completata con successo (UTC)")
    else:
        logger.warning("⚠️ Nessun target importato.")

# =========================
# Main
# =========================
if __name__ == "__main__":
    asyncio.run(import_telegram())