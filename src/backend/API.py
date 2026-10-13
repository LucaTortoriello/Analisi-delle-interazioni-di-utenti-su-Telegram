from flask import Flask, jsonify, request, send_from_directory, url_for
from flask_cors import CORS
import mysql.connector
import threading
from importer_service import start_import_process, IMPORT_STATUS
from mysql.connector import Error
import os
import json  # Importato globalmente per comodità
import time
from functools import lru_cache
from flask import request
import logging
from dotenv import load_dotenv
from datetime import datetime
from deep_translator import GoogleTranslator, MyMemoryTranslator
from deep_translator.exceptions import TooManyRequests
from pathlib import Path
from sangmata_service import queue_sangmata_request, get_request_status as get_sangmata_status

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "credenzialiDB.env")

# Il driver Neo4j legge le credenziali durante l'import.
from Neo4jConnector2_0 import run_query
from graph_analysis_service import get_community_analysis

_translation_lock = threading.Lock()
_last_translation_at = 0.0
_community_labels_lock = threading.Lock()
_community_labels_cache = {"created_at": 0.0, "key": None, "value": None}
MYMEMORY_LANGUAGES = {
    "rus": "ru-RU", "ukr": "uk-UA", "eng": "en-US", "spa": "es-ES",
    "fra": "fr-FR", "deu": "de-DE", "por": "pt-PT", "nld": "nl-NL",
    "pol": "pl-PL", "tur": "tr-TR", "ara": "ar-SA", "heb": "he-IL",
    "ell": "el-GR", "zho": "zh-CN", "jpn": "ja-JP", "kor": "ko-KR",
    "hin": "hi-IN", "ron": "ro-RO", "ces": "cs-CZ", "bul": "bg-BG",
}


@lru_cache(maxsize=5000)
def translate_if_needed(text: str, source_language: str = "und") -> str:
    """Traduce una volta sola ogni testo e limita le richieste al provider."""
    global _last_translation_at
    if not text:
        return text

    with _translation_lock:
        elapsed = time.monotonic() - _last_translation_at
        if elapsed < 0.35:
            time.sleep(0.35 - elapsed)
        try:
            try:
                translated = GoogleTranslator(source="auto", target="it").translate(text)
            except TooManyRequests:
                source = MYMEMORY_LANGUAGES.get(source_language)
                if not source:
                    raise
                translated = MyMemoryTranslator(
                    source=source,
                    target="it-IT",
                ).translate(text)
        finally:
            _last_translation_at = time.monotonic()

    if not translated:
        raise RuntimeError("Il servizio di traduzione non ha restituito un risultato")
    return translated


# =========================
# Configurazione base
# =========================
app = Flask(__name__)
frontend_origin = os.getenv("FRONTEND_ORIGIN", "*")
CORS(app, resources={r"/api/*": {"origins": frontend_origin}})

# =========================
# Cache temporanea (RAM)
# =========================
from flask_caching import Cache

cache = Cache(app, config={
    "CACHE_TYPE": "SimpleCache",     # cache in memoria del processo
    "CACHE_DEFAULT_TIMEOUT": 60      # durata 60 secondi
})


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("app.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def get_connection():
    """Connessione a MySQL."""
    # Proviamo prima il connettore nativo (C-ext). Se si verifica l'errore
    # relativo al plugin di autenticazione (es. "mysql_native_password"
    # cannot be loaded: it is already loaded) facciamo fallback al driver
    # Python puro per evitare conflitti di plugin su Windows.
    conn_args = dict(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "analisiutentitelegram"),
        charset="utf8mb4"
    )
    try:
        return mysql.connector.connect(**conn_args)
    except Exception as e:
        msg = str(e)
        if "mysql_native_password" in msg or "cannot be loaded" in msg:
            logger.warning(
                "Errore plugin autenticazione MySQL rilevato; ri-provo con use_pure=True"
            )
            # Forziamo il driver Python puro come fallback
            conn_args["use_pure"] = True
            return mysql.connector.connect(**conn_args)
        # Se è un altro errore, rilanciamo per essere gestito a monte
        raise


def enrich_community_labels(communities):
    """Aggiunge etichette basate sulle chat che generano più reply."""
    enriched = [dict(community) for community in communities]
    cache_key = tuple(
        (
            community.get("id"),
            community.get("size"),
            tuple(community.get("top_chat_ids", [])),
        )
        for community in enriched
    )
    with _community_labels_lock:
        cached = _community_labels_cache["value"]
        if (
            cached is not None
            and _community_labels_cache["key"] == cache_key
            and time.monotonic() - _community_labels_cache["created_at"] < 300
        ):
            return [dict(community) for community in cached]

    chat_ids = {
        int(chat_id)
        for community in enriched
        for chat_id in community.get("top_chat_ids", [])
        if chat_id is not None
    }
    chats_by_id = {}
    conn = cursor = None

    if chat_ids:
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            placeholders = ",".join(["%s"] * len(chat_ids))
            cursor.execute(f"""
                SELECT id_chat, nome_chat, nome_chat_tradotto, categoria_chat
                FROM chat
                WHERE id_chat IN ({placeholders})
            """, tuple(chat_ids))
            chats_by_id = {int(row["id_chat"]): row for row in cursor.fetchall()}
        except Exception as exc:
            logger.warning("Impossibile creare le etichette delle comunità: %s", exc)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    for community in enriched:
        top_chats = []
        names = []
        seen_names = set()
        for chat_id in community.get("top_chat_ids", []):
            chat = chats_by_id.get(int(chat_id))
            if not chat:
                continue
            name = (chat.get("nome_chat_tradotto") or chat.get("nome_chat") or "").strip()
            if not name:
                continue
            normalized_name = name.casefold()
            if normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)
            short_name = name if len(name) <= 42 else f"{name[:39].rstrip()}…"
            names.append(short_name)
            top_chats.append({
                "id": int(chat_id),
                "name": name,
                "category": chat.get("categoria_chat") or "",
            })

        community["top_chats"] = top_chats
        community["label"] = " · ".join(names[:2]) or (
            f"Gruppo di {community.get('size', 0)} utenti"
        )

    with _community_labels_lock:
        _community_labels_cache.update({
            "created_at": time.monotonic(),
            "key": cache_key,
            "value": enriched,
        })
    return enriched


def pag_params():
    """Legge limit/offset da query string con limiti di sicurezza."""
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 200))
    except Exception:
        limit = 50
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except Exception:
        offset = 0
    return limit, offset


def to_download_url(path: str | None) -> str | None:
    """Converte un percorso disco in URL servito da /downloads/<rel>."""
    if not path:
        return None
    p = str(path).replace("\\", "/").lstrip("/")
    if "downloads/" in p:
        rel = p.split("downloads/", 1)[1]
    else:
        rel = p
    return url_for("serve_downloads", filename=rel, _external=True)


def to_iso_utc(dt):
    """Restituisce la datetime MySQL come stringa 'YYYY-MM-DD HH:MM:SS' senza fuso."""
    if not dt:
        return ""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)

# =========================
# Pulizia nomi
# =========================
def clean_nome(nome, username=None):
    """Rimuove 'None' e spazi doppi. Fallback: @username o stringa vuota."""
    if not nome:
        return f"@{username}" if username else ""
    s = str(nome).replace("None", "").strip()
    while "  " in s:
        s = s.replace("  ", " ")
    return s or (f"@{username}" if username else "")


def apply_fallback(rows):
    """Applica fallback al testo dei messaggi (ma non mostra nulla se non serve)."""
    for r in rows:
        if not r.get("testo"):
            if r.get("media_type"):
                r["testo"] = "📎 Allegato"
            else:
                r["testo"] = ""   # 👈 invece di "(nessun testo)"
    return rows



# =========================
# Static: /downloads/*
# =========================
@app.route("/downloads/<path:filename>")
def serve_downloads(filename):
    base_dir = os.path.join(os.path.dirname(__file__), "downloads")
    return send_from_directory(base_dir, filename)


# =========================
# Statistiche
# =========================
@app.route("/api/statistiche", methods=["GET"])
def get_statistiche():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS utenti_totali FROM utenti")
        utenti = cursor.fetchone()["utenti_totali"]
        cursor.execute("SELECT COUNT(*) AS messaggi_totali FROM messaggi")
        messaggi = cursor.fetchone()["messaggi_totali"]
        cursor.execute("SELECT COUNT(*) AS chat_totali FROM chat")
        chat = cursor.fetchone()["chat_totali"]
        return jsonify({
            "status": "success",
            "utenti_totali": utenti,
            "messaggi_totali": messaggi,
            "chat_totali": chat
        })
    except Error as e:
        logger.error(f"Errore DB in get_statistiche: {e}")
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

# =========================
# Attività (OTTIMIZZATA)
# =========================
@app.route("/api/attivita", methods=["GET"])
@cache.cached(timeout=60, key_prefix="attivita")
def get_attivita():
    try:
        days = int(request.args.get("days", 7))
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # 1️⃣ Trova la data più recente
        cursor.execute("SELECT MAX(data_invio) AS ultima FROM messaggi")
        ultima = cursor.fetchone()["ultima"]

        if not ultima:
            return jsonify({
                "status": "success",
                "labels": [],
                "counts": [],
                "active_users": []
            })

        # 2️⃣ Calcola data limite FUORI dalla query
        from datetime import timedelta
        data_limite = ultima - timedelta(days=days)

        # 3️⃣ Query ottimizzata (usa indice su data_invio)
        cursor.execute("""
            SELECT DATE(m.data_invio) AS giorno,
                   COUNT(*) AS n_messaggi,
                   COUNT(DISTINCT m.id_autore) AS utenti_attivi
            FROM messaggi m
            WHERE m.data_invio >= %s
            GROUP BY giorno
            ORDER BY giorno ASC
        """, (data_limite,))

        rows = cursor.fetchall()

        labels = [r["giorno"].strftime("%Y-%m-%d") for r in rows]
        counts = [r["n_messaggi"] for r in rows]
        active_users = [r["utenti_attivi"] for r in rows]

        return jsonify({
            "status": "success",
            "labels": labels,
            "counts": counts,
            "active_users": active_users
        })

    except Exception as e:
        logger.error(f"Errore in get_attivita: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass



# =========================
# Utenti (lista)
# =========================
@app.route("/api/utenti", methods=["GET"])
def get_utenti():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        limit, offset = pag_params()

        cursor.execute("SELECT COUNT(*) AS total FROM utenti")
        total = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT id, nome, username, foto_path, data_importazione
            FROM utenti
            ORDER BY data_importazione DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))
        rows = cursor.fetchall()

        for r in rows:
            r["nome"] = clean_nome(r.get("nome"), r.get("username"))
            r["data_importazione"] = to_iso_utc(r.get("data_importazione"))
            r["avatar_url"] = to_download_url(r.get("foto_path"))

        return jsonify({
            "status": "success",
            "total": total,
            "count": len(rows),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < total,
            "data": rows
        })
    except Error as e:
        logger.error(f"Errore DB in get_utenti: {e}")
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


# =========================
# Dettaglio utente (con ultima attività + chat)
# =========================
@app.route("/api/utente/<int:user_id>", methods=["GET"])
def get_utente(user_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Cerca prima nella tabella UTENTI
        cursor.execute("SELECT id, nome, username, foto_path, data_importazione FROM utenti WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        # 2. Se non trovato, cerca nella tabella CHAT (es. Canale che scrive come utente)
        if not user:
            cursor.execute("""
                SELECT id_chat AS id, nome_chat AS nome, NULL as username,
                       NULL as foto_path, data_importazione
                FROM chat WHERE id_chat = %s
            """, (user_id,))
            chat_row = cursor.fetchone()

            if chat_row:
                user = chat_row
                user["nome"] = (user["nome"] or "Canale senza nome") + " (Canale)"
            else:
                # 3. CASO FANTASMA (L'ID esiste nei messaggi ma non abbiamo l'anagrafica)
                label = "Canale Esterno" if user_id < 0 else "Utente Sconosciuto"
                user = {
                    "id": user_id,
                    "nome": f"{label} {user_id}",
                    "username": None,
                    "foto_path": None,
                    "data_importazione": None
                }

        # Pulizia e formattazione dati
        user["nome"] = clean_nome(user.get("nome"), user.get("username"))
        user["data_importazione"] = to_iso_utc(user.get("data_importazione"))
        user["avatar_url"] = to_download_url(user.get("foto_path"))

        # Statistiche messaggi
        cursor.execute("SELECT COUNT(*) AS n FROM messaggi WHERE id_autore = %s", (user_id,))
        user["messaggi_totali"] = cursor.fetchone()["n"]

        # Ultima attività
        cursor.execute("SELECT MAX(data_invio) AS ultima FROM messaggi WHERE id_autore = %s", (user_id,))
        row = cursor.fetchone()
        user["ultima_attivita"] = to_iso_utc(row.get("ultima")) if row else None

        # Chat frequentate
        cursor.execute("""
            SELECT c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo,
                   COUNT(m.id_messaggio) AS messaggi_utente,
                   MIN(m.data_invio) AS prima_interazione,
                   MAX(m.data_invio) AS ultima_interazione
            FROM messaggi m
            JOIN chat c ON c.id_chat = m.id_chat
            WHERE m.id_autore = %s
            GROUP BY c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo
            ORDER BY messaggi_utente DESC
        """, (user_id,))
        chats = cursor.fetchall()

        for c in chats:
            c["prima_interazione"] = to_iso_utc(c.get("prima_interazione"))
            c["ultima_interazione"] = to_iso_utc(c.get("ultima_interazione"))

        return jsonify({"status": "success", "user": user, "chats": chats})

    except Exception as e:
        logger.error(f"Errore DB in get_utente: {e}")
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try: cursor.close(); conn.close()
        except: pass


# =========================
# Allegati di un utente
# =========================
@app.route("/api/allegati_utente/<int:user_id>", methods=["GET"])
def get_allegati_utente(user_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        limit, offset = pag_params()

        cursor.execute("SELECT COUNT(*) AS total FROM messaggi WHERE id_autore=%s AND file_path IS NOT NULL", (user_id,))
        total = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT m.id_messaggio, m.id_chat, c.nome_chat, c.nome_chat_tradotto ,
                   m.file_path, m.media_type, m.data_invio
            FROM messaggi m
            JOIN chat c ON c.id_chat = m.id_chat
            WHERE m.id_autore = %s AND m.file_path IS NOT NULL
            ORDER BY m.data_invio DESC
            LIMIT %s OFFSET %s
        """, (user_id, limit, offset))
        rows = cursor.fetchall()

        for r in rows:
            r["data_invio"] = to_iso_utc(r["data_invio"])
            r["file_url"] = to_download_url(r["file_path"])


        return jsonify({
            "status": "success",
            "total": total,
            "count": len(rows),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < total,
            "data": rows
        })
    except Exception as e:
        logger.error(f"Errore DB in get_allegati_utente: {e}")
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


# =========================
# Messaggi di un utente
# =========================
@app.route("/api/messaggi_utente/<int:user_id>", methods=["GET"])
def get_messaggi_utente(user_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        limit, offset = pag_params()

        cursor.execute("SELECT COUNT(*) AS total FROM messaggi WHERE id_autore=%s", (user_id,))
        total = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT m.id_messaggio, m.id_chat, m.testo, m.data_invio,
                   m.file_path, m.media_type, m.tipo_evento,
                   c.nome_chat AS provenienza,
                   c.nome_chat_tradotto AS provenienza_tradotta,
                   u.nome, u.username, u.foto_path
            FROM messaggi m
            JOIN chat c ON c.id_chat = m.id_chat
            LEFT JOIN utenti u ON m.id_autore = u.id
            WHERE m.id_autore = %s
            ORDER BY m.data_invio DESC
            LIMIT %s OFFSET %s
        """, (user_id, limit, offset))

        rows = cursor.fetchall()
        for r in rows:
            r["data_invio"] = to_iso_utc(r.get("data_invio"))
            r["file_url"] = to_download_url(r.get("file_path"))
            r["avatar_url"] = to_download_url(r.get("foto_path"))

            # Nome pulito (fallback su username se manca nome)
            r["nome"] = clean_nome(r.get("nome"), r.get("username"))


        rows = apply_fallback(rows)

        return jsonify({
            "status": "success",
            "total": total,
            "count": len(rows),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < total,
            "data": rows
        })
    except Error as e:
        logger.error(f"Errore DB in get_messaggi_utente: {e}")
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


# =========================
# Chat (lista) - CON ADMINS.JSON
# =========================
@app.route("/api/chats", methods=["GET"])
def get_chats():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        limit, offset = pag_params()
        categoria = request.args.get("categoria")

        # Seleziona tutte le colonne da chat (c) E il foto_path da utenti (u)
        select_clause = "c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo, c.ultima_scansione, c.data_importazione, c.categoria_chat, u.foto_path"

        # LEFT JOIN: unisci chat.id_chat con utenti.id.
        join_clause = "LEFT JOIN utenti u ON c.id_chat = u.id"

        where_clause = ""
        count_params = []
        select_params = []

        if categoria:
            where_clause = "WHERE c.categoria_chat = %s"
            count_params.append(categoria)
            select_params.append(categoria)

            # Conta totale con filtro
            cursor.execute(f"SELECT COUNT(*) AS total FROM chat c {where_clause}", tuple(count_params))
            total = cursor.fetchone()["total"]

        else:
            cursor.execute("SELECT COUNT(*) AS total FROM chat")
            total = cursor.fetchone()["total"]

        # Aggiunge i parametri di paginazione
        select_params.extend([limit, offset])

        # Query principale
        query = f"""
            SELECT {select_clause}
            FROM chat c
            {join_clause}
            {where_clause}
            ORDER BY c.ultima_scansione DESC
            LIMIT %s OFFSET %s
        """

        cursor.execute(query, tuple(select_params))
        rows = cursor.fetchall()

        # ==================================================================
        # CARICAMENTO ADMIN DA JSON E INIEZIONE NELLE CHAT
        # ==================================================================
        admins_data = {}
        try:
            json_path = os.path.join(os.path.dirname(__file__), "admins.json")

            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    admins_data = json.load(f)
        except Exception as e:
            logger.error(f"Errore lettura admins.json in get_chats: {e}")

        for r in rows:
            r["ultima_scansione"] = to_iso_utc(r.get("ultima_scansione"))
            r["data_importazione"] = to_iso_utc(r.get("data_importazione"))
            r["avatar_url"] = to_download_url(r.get("foto_path"))

            # --- INIEZIONE ADMIN ---
            chat_id_str = str(r["id_chat"])
            r["admins"] = admins_data.get(chat_id_str, [])

            # Opzionale: Stringa riassuntiva
            if r["admins"]:
                names = [a.get("nome") or a.get("username") or "Sconosciuto" for a in r["admins"]]
                r["admin_summary"] = ", ".join(names[:3])
        # ==================================================================

        return jsonify({
            "status": "success",
            "total": total,
            "count": len(rows),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < total,
            "data": rows
        })
    except Exception as e:
        logger.error(f"Errore DB in get_chats: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass



# =========================
# Info chat (Dettaglio) - CON ADMINS.JSON
# =========================
@app.route("/api/chat_info/<int:chat_id>", methods=["GET"])
def get_chat_info(chat_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id_chat, nome_chat, nome_chat_tradotto, tipo, ultima_scansione, categoria_chat
            FROM chat
            WHERE id_chat=%s
        """, (chat_id,))
        info = cursor.fetchone() or {}

        cursor.execute("SELECT COUNT(*) AS n_msg FROM messaggi WHERE id_chat=%s", (chat_id,))
        row = cursor.fetchone()
        info["messaggi_totali"] = row["n_msg"] if row else 0

        cursor.execute("SELECT COUNT(DISTINCT id_autore) AS n_users FROM messaggi WHERE id_chat=%s", (chat_id,))
        row = cursor.fetchone()
        info["utenti_attivi"] = row["n_users"] if row else 0

        cursor.execute("""
            SELECT MIN(data_invio) AS prima, MAX(data_invio) AS ultima
            FROM messaggi WHERE id_chat=%s
        """, (chat_id,))
        row = cursor.fetchone() or {}
        info["prima_data"] = to_iso_utc(row.get("prima"))
        info["ultima_data"] = to_iso_utc(row.get("ultima"))

        # =========================================================
        # RECUPERO ADMIN DA JSON PER DETTAGLIO
        # =========================================================
        admins_data = {}
        try:
            json_path = os.path.join(os.path.dirname(__file__), "admins.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    admins_data = json.load(f)

            # Recupera gli admin per questo specifico ID
            info["admins"] = admins_data.get(str(chat_id), [])
        except Exception as e:
            logger.error(f"Errore lettura admins in chat_info: {e}")
            info["admins"] = []
        # =========================================================

        return jsonify({"status": "success", "data": info})
    except Error as e:
        logger.error(f"Errore DB in get_chat_info: {e}")
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

# =========================
# Messaggi per chat
# =========================
@app.route("/api/messaggi/<int:chat_id>", methods=["GET"])
def get_messaggi(chat_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        limit, offset = pag_params()

        # Conta totale messaggi della chat
        cursor.execute("SELECT COUNT(*) AS total FROM messaggi WHERE id_chat=%s", (chat_id,))
        total = cursor.fetchone()["total"]

        # ✅ Query aggiornata con identificazione tipo autore
        cursor.execute("""
            SELECT
                m.id_messaggio,
                m.id_chat,
                m.id_autore,
                m.reply_to_msg_id,

                -- ✅ IDENTIFICA TIPO AUTORE (canale ufficiale, canale esterno, utente)
                CASE
                    WHEN m.id_autore = m.id_chat AND m.id_autore < 0 THEN 'channel_official'
                    WHEN m.id_autore < 0 THEN 'channel_external'
                    WHEN m.id_autore > 0 THEN 'user'
                    ELSE 'unknown'
                END AS author_type,

                -- Dati utente normale
                u1.nome AS autore_nome,
                u1.username AS autore_username,
                u1.foto_path,

                -- Dati messaggio
                m.testo,
                m.data_invio,
                m.tipo_evento,
                m.file_path,
                m.media_type,

                -- Dati chat (per nome del canale)
                c.nome_chat AS provenienza,
                c.nome_chat_tradotto AS provenienza_tradotta,

                -- Campi reply
                m2.id_messaggio AS replied_msg_id,
                u2.id AS reply_to_id,
                u2.nome AS reply_to_nome,
                u2.username AS reply_to_username,
                m2.testo AS reply_to_testo

            FROM messaggi m
            LEFT JOIN utenti u1 ON m.id_autore = u1.id
            LEFT JOIN chat c ON m.id_chat = c.id_chat
            LEFT JOIN messaggi m2
                ON CAST(TRIM(m.reply_to_msg_id) AS CHAR) = CAST(m2.id_messaggio AS CHAR)
                AND m.id_chat = m2.id_chat
            LEFT JOIN utenti u2 ON m2.id_autore = u2.id
            WHERE m.id_chat = %s
            ORDER BY m.data_invio DESC
            LIMIT %s OFFSET %s
        """, (chat_id, limit, offset))

        rows = cursor.fetchall()

        # ✅ Post-processing aggiornato con gestione canale/utente
        for r in rows:
            # 🔹 GESTIONE NOME BASATA SUL TIPO DI AUTORE
            if r["author_type"] == "channel_official":
                # È il canale stesso che scrive (post ufficiale)
                r["nome"] = r["provenienza_tradotta"] or r["provenienza"]
                r["autore_nome"] = r["nome"]
                r["autore_username"] = None
                r["is_channel_post"] = True

                r["avatar_url"] = to_download_url(r.get("foto_path_chat") or r.get("foto_path"))

            elif r["author_type"] == "channel_external":
                # È un altro canale che scrive
                r["nome"] = f"Canale Esterno {abs(r['id_autore'])}"
                r["autore_nome"] = r["nome"]
                r["autore_username"] = None
                r["is_channel_post"] = False

            else:
                # È un utente normale
                r["autore_nome"] = clean_nome(r.get("autore_nome"), r.get("autore_username"))
                r["nome"] = r["autore_nome"]
                r["is_channel_post"] = False

            # Nome utente a cui si risponde
            r["reply_to_nome"] = clean_nome(r.get("reply_to_nome"), r.get("reply_to_username"))

            # Pulizia e fallback
            r["reply_to_id"] = r.get("reply_to_id") or None
            r["reply_to_username"] = r.get("reply_to_username") or ""
            r["data_invio"] = to_iso_utc(r.get("data_invio"))
            r["file_url"] = to_download_url(r.get("file_path"))
            r["avatar_url"] = to_download_url(r.get("foto_path"))

            # Limita la preview a 120 caratteri max (evita testi lunghi)
            if r.get("reply_to_testo"):
                txt = r["reply_to_testo"].strip().replace("\n", " ")
                if len(txt) > 120:
                    txt = txt[:117] + "..."
                r["reply_to_testo"] = txt

        rows = apply_fallback(rows)

        return jsonify({
            "status": "success",
            "total": total,
            "count": len(rows),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < total,
            "data": rows
        })

    except Error as e:
        logger.error(f"Errore DB in get_messaggi: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500

    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass





# =========================
# Reply di un utente
# =========================
@app.route("/api/reply_utente/<int:user_id>", methods=["GET"])
def get_reply_utente(user_id: int):
    try:
        keyword = request.args.get("keyword", "").strip().lower()
        mode = request.args.get("mode", "all").lower()

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # ✅ Query corretta con verifiche aggiuntive
        cursor.execute("""
            SELECT
                m.id_messaggio,
                m.testo AS reply_text,
                m.data_invio,
                m.tipo_evento,
                m.id_chat,
                c.nome_chat,
                c.nome_chat_tradotto,

                -- AUTORE (Chi risponde - sempre l'utente richiesto)
                m.id_autore AS autore_id,
                u1.nome AS u1_nome,
                u1.username AS u1_user,
                u1.foto_path AS u1_foto,
                c1.nome_chat AS c1_nome,

                -- DESTINATARIO (A chi si risponde)
                m2.id_messaggio AS original_msg_id,
                m2.testo AS original_text,
                m2.id_autore AS reply_to_user_id,
                u2.nome AS u2_nome,
                u2.username AS u2_user,
                u2.foto_path AS u2_foto,
                c2.nome_chat AS c2_nome

            FROM messaggi m
            INNER JOIN chat c ON c.id_chat = m.id_chat

            -- Join Autore
            LEFT JOIN utenti u1 ON m.id_autore = u1.id
            LEFT JOIN chat c1 ON m.id_autore = c1.id_chat

            -- 🔥 FIX CRITICO: Join solo messaggi nella STESSA CHAT
            LEFT JOIN messaggi m2
                ON m.reply_to_msg_id = m2.id_messaggio
                AND m.id_chat = m2.id_chat
            LEFT JOIN utenti u2 ON m2.id_autore = u2.id
            LEFT JOIN chat c2 ON m2.id_autore = c2.id_chat

            WHERE m.id_autore = %s
              AND m.reply_to_msg_id IS NOT NULL
              AND TRIM(m.reply_to_msg_id) != ''  -- 🔥 Escludi stringhe vuote
              AND m.reply_to_msg_id != '0'        -- 🔥 Escludi ID zero
            ORDER BY m.data_invio DESC
        """, (user_id,))

        rows = cursor.fetchall()

        # 🔥 FILTRO POST-QUERY: Rimuovi reply senza messaggio originale valido
        valid_replies = []
        general = []
        kw_rels = []

        for r in rows:
            # Salta se non c'è messaggio originale valido
            if not r.get("original_msg_id"):
                continue

            r["data_invio"] = to_iso_utc(r["data_invio"])

            # LOGICA NOME AUTORE (Priorità: Utente -> Chat -> Fallback ID)
            if r["u1_nome"] or r["u1_user"]:
                r["autore_nome"] = clean_nome(r["u1_nome"], r["u1_user"])
                r["autore_foto"] = r["u1_foto"]
            elif r["c1_nome"]:
                r["autore_nome"] = r["c1_nome"] + " (Canale)"
                r["autore_foto"] = None
            else:
                r["autore_nome"] = f"Canale Esterno {r['autore_id']}" if r['autore_id'] < 0 else f"Utente {r['autore_id']}"
                r["autore_foto"] = None

            # LOGICA NOME DESTINATARIO (Priorità: Utente -> Chat -> Fallback ID)
            dest_id = r["reply_to_user_id"]
            if dest_id is None:
                # Reply a messaggio cancellato - VALIDO ma segnalato
                r["reply_to_nome"] = "Messaggio Cancellato"
                r["reply_to_username"] = ""
                r["reply_to_foto"] = None
            elif r["u2_nome"] or r["u2_user"]:
                r["reply_to_nome"] = clean_nome(r["u2_nome"], r["u2_user"])
                r["reply_to_username"] = r["u2_user"]
                r["reply_to_foto"] = r["u2_foto"]
            elif r["c2_nome"]:
                r["reply_to_nome"] = r["c2_nome"] + " (Canale)"
                r["reply_to_username"] = ""
                r["reply_to_foto"] = None
            else:
                label = "Canale Esterno" if (dest_id and dest_id < 0) else "Utente"
                r["reply_to_nome"] = f"{label} {dest_id}" if dest_id else "Sconosciuto"
                r["reply_to_username"] = ""
                r["reply_to_foto"] = None

            # Avatar URLs
            r["avatar_from"] = to_download_url(r.get("autore_foto"))
            r["avatar_to"] = to_download_url(r.get("reply_to_foto"))

            # Keyword Detection
            reply_txt = r.get("reply_text") or ""
            orig_txt = r.get("original_text") or ""

            r["keyword_count_reply"] = 0
            r["keyword_count_original"] = 0
            r["keyword_context"] = None
            has_kw = False

            if keyword:
                k1 = reply_txt.lower().count(keyword)
                k2 = orig_txt.lower().count(keyword)
                r["keyword_count_reply"] = k1
                r["keyword_count_original"] = k2

                if k1 > 0:
                    idx = reply_txt.lower().find(keyword)
                    start = max(0, idx - 40)
                    end = min(len(reply_txt), idx + len(keyword) + 40)
                    r["keyword_context"] = reply_txt[start:end]
                    has_kw = True
                if k2 > 0:
                    has_kw = True

            valid_replies.append(r)
            general.append(r)
            if has_kw:
                kw_rels.append(r)

        if mode == "keyword":
            return jsonify({"status": "success", "data": kw_rels})
        if mode == "both":
            return jsonify({
                "status": "success",
                "keyword": keyword,
                "general_relations": general,
                "keyword_relations": kw_rels,
                "keyword_relations_count": len(kw_rels)
            })

        return jsonify({"status": "success", "data": general})

    except Exception as e:
        logger.error(f"Errore DB reply_utente: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


@app.route("/api/graph/edge/<int:from_id>/<int:to_id>", methods=["GET"])
@cache.cached(timeout=60)
def get_graph_edge_details(from_id: int, to_id: int):
    """Dettaglio verificabile di un arco con una sola richiesta frontend."""
    if from_id == to_id:
        return jsonify({"status": "error", "message": "Gli utenti devono essere distinti"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT m.id_autore AS source_id,
                   original.id_autore AS target_id,
                   COUNT(*) AS reply_count
            FROM messaggi m
            INNER JOIN messaggi original
              ON original.id_chat = m.id_chat
             AND original.id_messaggio = m.reply_to_msg_id
            WHERE m.id_autore IN (%s, %s)
              AND original.id_autore IN (%s, %s)
              AND m.id_autore <> original.id_autore
              AND m.reply_to_msg_id IS NOT NULL
              AND TRIM(m.reply_to_msg_id) <> ''
              AND m.reply_to_msg_id <> '0'
            GROUP BY m.id_autore, original.id_autore
        """, (from_id, to_id, from_id, to_id))
        counts = {
            (int(row["source_id"]), int(row["target_id"])): int(row["reply_count"])
            for row in cursor.fetchall()
        }
        forward = counts.get((from_id, to_id), 0)
        reverse = counts.get((to_id, from_id), 0)
        total = forward + reverse

        cursor.execute("""
            SELECT u.id, u.nome, u.username, u.foto_path
            FROM utenti u
            WHERE u.id IN (%s, %s)
        """, (from_id, to_id))
        users = {}
        for row in cursor.fetchall():
            row["nome"] = clean_nome(row.get("nome"), row.get("username"))
            row["avatar_url"] = to_download_url(row.get("foto_path"))
            row.pop("foto_path", None)
            users[int(row["id"])] = row

        cursor.execute("""
            SELECT m.id_messaggio,
                   m.id_chat,
                   m.testo AS reply_text,
                   m.data_invio,
                   m.tipo_evento,
                   m.id_autore AS autore_id,
                   original.id_messaggio AS original_msg_id,
                   original.testo AS original_text,
                   original.id_autore AS reply_to_user_id,
                   c.nome_chat,
                   c.nome_chat_tradotto,
                   c.username AS chat_username,
                   author.nome AS autore_nome,
                   author.username AS autore_username,
                   author.foto_path AS autore_foto,
                   recipient.nome AS reply_to_nome,
                   recipient.username AS reply_to_username,
                   recipient.foto_path AS reply_to_foto
            FROM messaggi m
            INNER JOIN messaggi original
              ON original.id_chat = m.id_chat
             AND original.id_messaggio = m.reply_to_msg_id
            INNER JOIN chat c ON c.id_chat = m.id_chat
            LEFT JOIN utenti author ON author.id = m.id_autore
            LEFT JOIN utenti recipient ON recipient.id = original.id_autore
            WHERE m.id_autore IN (%s, %s)
              AND original.id_autore IN (%s, %s)
              AND m.id_autore <> original.id_autore
              AND m.reply_to_msg_id IS NOT NULL
              AND TRIM(m.reply_to_msg_id) <> ''
              AND m.reply_to_msg_id <> '0'
            ORDER BY m.data_invio DESC
            LIMIT 5
        """, (from_id, to_id, from_id, to_id))
        messages = cursor.fetchall()
        for message in messages:
            message["data_invio"] = to_iso_utc(message.get("data_invio"))
            message["autore_nome"] = clean_nome(
                message.get("autore_nome"), message.get("autore_username")
            )
            message["reply_to_nome"] = clean_nome(
                message.get("reply_to_nome"), message.get("reply_to_username")
            )
            message["avatar_from"] = to_download_url(message.pop("autore_foto", None))
            message["avatar_to"] = to_download_url(message.pop("reply_to_foto", None))

        reciprocity = round((2 * min(forward, reverse)) / total, 3) if total else 0
        return jsonify({
            "status": "success",
            "from_user": users.get(from_id, {"id": from_id, "nome": str(from_id)}),
            "to_user": users.get(to_id, {"id": to_id, "nome": str(to_id)}),
            "stats": {
                "forward": forward,
                "reverse": reverse,
                "total": total,
                "reciprocal": forward > 0 and reverse > 0,
                "reciprocity": reciprocity,
            },
            "messages": messages,
        })
    except Exception as exc:
        logger.error("Errore dettaglio arco %s-%s: %s", from_id, to_id, exc, exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/api/reply_summary/<int:user_id>", methods=["GET"])
@cache.cached(timeout=120)
def get_reply_summary(user_id: int):
    """Riepilogo aggregato dei reply inviati e ricevuti, senza query N+1."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT original.id_autore AS id,
                   COALESCE(NULLIF(u.nome, ''), NULLIF(u.username, ''),
                            CONCAT('Utente ', original.id_autore)) AS nome,
                   COUNT(*) AS count
            FROM messaggi reply
            JOIN messaggi original
              ON original.id_chat = reply.id_chat
             AND original.id_messaggio = reply.reply_to_msg_id
            LEFT JOIN utenti u ON u.id = original.id_autore
            WHERE reply.id_autore = %s
              AND original.id_autore > 0
              AND original.id_autore <> reply.id_autore
            GROUP BY original.id_autore, u.nome, u.username
            ORDER BY count DESC
        """, (user_id,))
        sent = cursor.fetchall()

        cursor.execute("""
            SELECT reply.id_autore AS id,
                   COALESCE(NULLIF(u.nome, ''), NULLIF(u.username, ''),
                            CONCAT('Utente ', reply.id_autore)) AS nome,
                   COUNT(*) AS count
            FROM messaggi reply
            JOIN messaggi original
              ON original.id_chat = reply.id_chat
             AND original.id_messaggio = reply.reply_to_msg_id
            LEFT JOIN utenti u ON u.id = reply.id_autore
            WHERE original.id_autore = %s
              AND reply.id_autore > 0
              AND reply.id_autore <> original.id_autore
            GROUP BY reply.id_autore, u.nome, u.username
            ORDER BY count DESC
        """, (user_id,))
        received = cursor.fetchall()

        return jsonify({
            "sent": sent,
            "received": received,
            "totalSent": sum(row["count"] for row in sent),
            "totalReceived": sum(row["count"] for row in received),
        })
    except Exception as exc:
        logger.error(f"Errore riepilogo reply per {user_id}: {exc}", exc_info=True)
        return jsonify({"error": "Errore nel riepilogo reply"}), 500
    finally:
        cursor.close()
        conn.close()


# =========================
# Ricerca messaggi
# =========================
@app.route("/api/cerca_messaggi", methods=["GET"])
def cerca_messaggi():
    try:
        # Parametri
        keyword = request.args.get("q", "").strip()
        chat_id = request.args.get("chat_id")
        id_autore = request.args.get("id_autore")
        categoria = request.args.get("categoria") # <--- NUOVO PARAMETRO
        data_inizio = request.args.get("data_inizio")
        data_fine = request.args.get("data_fine")
        keywords_raw = request.args.get("keywords", "").strip()
        limit, offset = pag_params()

        keywords = []
        if keywords_raw:
            keywords = [k.strip().lower() for k in keywords_raw.split(",") if k.strip()]

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Costruzione Query
        conditions = []
        params = []

        if keyword:
            conditions.append("LOWER(m.testo) LIKE LOWER(%s)")
            params.append(f"%{keyword}%")

        if chat_id and chat_id.isdigit():
            conditions.append("m.id_chat = %s")
            params.append(int(chat_id))

        # --- NUOVA LOGICA CATEGORIA ---
        if categoria:
            conditions.append("c.categoria_chat = %s")
            params.append(categoria)
        # ------------------------------

        if id_autore:
            conditions.append("m.id_autore = %s")
            params.append(int(id_autore))

        if data_inizio:
            conditions.append("m.data_invio >= %s")
            params.append(data_inizio)
        if data_fine:
            conditions.append("m.data_invio <= %s")
            params.append(data_fine)

        for kw in keywords:
            conditions.append("LOWER(m.testo) LIKE LOWER(%s)")
            params.append(f"%{kw}%")

        if not conditions:
            return jsonify({"status": "error", "message": "Nessun parametro"}), 400

        where_clause = " AND ".join(conditions)

        # Conta (nota che serve la join con chat c per filtrare la categoria)
        count_query = f"""
            SELECT COUNT(*) AS total
            FROM messaggi m
            LEFT JOIN chat c ON m.id_chat = c.id_chat
            WHERE {where_clause}
        """
        cursor.execute(count_query, tuple(params))
        total = cursor.fetchone()["total"]

        # Query Principale
        query = f"""
            SELECT m.id_messaggio, m.id_chat, m.id_autore, m.testo, m.data_invio, m.tipo_evento,
                   m.file_path, m.media_type,
                   u.nome AS u_nome, u.username AS u_user, u.foto_path,
                   c.nome_chat AS provenienza, c.nome_chat_tradotto AS provenienza_tradotta,
                   c.categoria_chat,
                   c_auth.nome_chat AS c_auth_nome
            FROM messaggi m
            LEFT JOIN utenti u ON m.id_autore = u.id
            LEFT JOIN chat c ON m.id_chat = c.id_chat
            LEFT JOIN chat c_auth ON m.id_autore = c_auth.id_chat
            WHERE {where_clause}
            ORDER BY m.data_invio DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(query, tuple(params + [limit, offset]))
        rows = cursor.fetchall()

        # ... (resto della funzione invariato: post-processing nomi e fallback) ...
        for r in rows:
            # Logica nome: Utente -> Canale noto -> Fallback
            if r["u_nome"] or r["u_user"]:
                r["nome"] = clean_nome(r["u_nome"], r["u_user"])
            elif r["c_auth_nome"]:
                r["nome"] = r["c_auth_nome"] + " (Canale)"
            else:
                r["nome"] = f"Canale Esterno {r['id_autore']}" if r['id_autore'] < 0 else f"Utente {r['id_autore']}"

            r["data_invio"] = to_iso_utc(r.get("data_invio"))
            r["file_url"] = to_download_url(r.get("file_path"))
            r["avatar_url"] = to_download_url(r.get("foto_path"))

        rows = apply_fallback(rows)

        return jsonify({
            "status": "success",
            "total": total,
            "count": len(rows),
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < total,
            "data": rows
        })

    except Exception as e:
        logger.error(f"Errore DB in cerca_messaggi: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try: cursor.close(); conn.close()
        except: pass



# =========================
# Ultimi messaggi (AGGIORNATO con gestione ID negativi)
# =========================
@app.route("/api/ultimi_messaggi", methods=["GET"])
def ultimi_messaggi():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        limit = 50

        cursor.execute("""
            SELECT
                m.id_messaggio,
                m.id_chat,
                m.id_autore,

                -- Identifica tipo autore (stessa logica di /api/messaggi)
                CASE
                    WHEN m.id_autore = m.id_chat AND m.id_autore < 0 THEN 'channel_official'
                    WHEN m.id_autore < 0 THEN 'channel_external'
                    WHEN m.id_autore > 0 THEN 'user'
                    ELSE 'unknown'
                END AS author_type,

                -- Dati utente
                u.nome AS u_nome,
                u.username AS u_user,
                u.foto_path,

                -- Dati canale (se l'autore è un canale)
                c_auth.nome_chat AS c_auth_nome,
                c_auth.nome_chat_tradotto AS c_auth_nome_tradotto,

                -- Dati messaggio
                m.testo,
                m.data_invio,
                m.tipo_evento,
                m.file_path,
                m.media_type,

                -- Provenienza
                c.nome_chat AS provenienza,
                c.nome_chat_tradotto AS provenienza_tradotta

            FROM messaggi m
            LEFT JOIN utenti u ON m.id_autore = u.id
            LEFT JOIN chat c ON m.id_chat = c.id_chat
            LEFT JOIN chat c_auth ON m.id_autore = c_auth.id_chat
            ORDER BY m.data_invio DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()

        for r in rows:
            author_type = r.get("author_type", "unknown")

            # 🔹 GESTIONE NOME BASATA SUL TIPO DI AUTORE (stessa logica di /api/messaggi)
            if author_type == "channel_official":
                # È il canale stesso che scrive (post ufficiale)
                r["nome"] = r["provenienza_tradotta"] or r["provenienza"]
                r["is_channel_post"] = True
            elif author_type == "channel_external":
                # È un altro canale che scrive
                if r["c_auth_nome"]:
                    r["nome"] = (r["c_auth_nome_tradotto"] or r["c_auth_nome"]) + " (Canale)"
                else:
                    r["nome"] = f"Canale Esterno {abs(r['id_autore'])}"
                r["is_channel_post"] = False
            else:
                # È un utente normale
                r["nome"] = clean_nome(r.get("u_nome"), r.get("u_user"))
                r["is_channel_post"] = False

            r["data_invio"] = to_iso_utc(r.get("data_invio"))
            r["file_url"] = to_download_url(r.get("file_path"))
            r["avatar_url"] = to_download_url(r.get("foto_path"))

        rows = apply_fallback(rows)

        return jsonify(rows)
    except Error as e:
        logger.error(f"Errore DB in ultimi_messaggi: {e}")
        return jsonify([]), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


# =========================
# Interazioni utente
# =========================
@app.route("/api/interazioni_utente/<int:user_id>", methods=["GET"])
def get_interazioni_utente(user_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Chat in cui scrive
        cursor.execute("""
            SELECT c.id_chat, c.nome_chat, c.nome_chat_tradotto, COUNT(*) AS n_messaggi
            FROM messaggi m
            JOIN chat c ON c.id_chat = m.id_chat
            WHERE m.id_autore = %s
            GROUP BY c.id_chat, c.nome_chat, c.nome_chat_tradotto
            ORDER BY n_messaggi DESC
        """, (user_id,))
        chats = cursor.fetchall()

        # Risposte dirette ad altri utenti
        cursor.execute("""
            SELECT m.reply_to_msg_id, m.id_autore, u.username, COUNT(*) AS n_risposte
            FROM messaggi m
            JOIN utenti u ON u.id = m.id_autore
            WHERE m.reply_to_msg_id IS NOT NULL
              AND m.id_autore = %s
            GROUP BY m.reply_to_msg_id, m.id_autore, u.username
            ORDER BY n_risposte DESC
        """, (user_id,))
        risposte = cursor.fetchall()

        return jsonify({
            "status": "success",
            "chats": chats,
            "risposte": risposte
        })
    except Exception as e:
        logger.error(f"Errore DB in get_interazioni_utente: {e}")
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass


# =========================
# Traduzione singola
# =========================
@app.route("/api/traduci", methods=["POST"])
def traduci():
    try:
        data = request.get_json(force=True)
        q = data.get("q", "").strip()
        source_language = data.get("source", "und").strip().lower()
        if not q:
            return jsonify({"error": "Parametro 'q' mancante"}), 400
        if len(q) > 5000:
            return jsonify({"error": "Testo troppo lungo (massimo 5000 caratteri)"}), 400

        tradotto = translate_if_needed(q, source_language)
        return jsonify({"translatedText": tradotto})
    except TooManyRequests:
        logger.warning("Limite temporaneo del servizio di traduzione raggiunto")
        return jsonify({
            "error": "Servizio di traduzione temporaneamente limitato. Riprova tra un minuto."
        }), 429
    except Exception as e:
        logger.error(f"Errore traduzione: {e}", exc_info=True)
        return jsonify({"error": "Traduzione non disponibile. Riprova più tardi."}), 502


# =========================
# Chat a cui appartiene un utente
# =========================
@app.route("/api/chat_utente/<int:user_id>", methods=["GET"])
def get_chat_utente(user_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            (
              SELECT c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo,
                      COUNT(m.id_messaggio) AS messaggi_utente,
                      MIN(m.data_invio) AS prima_interazione,
                      MAX(m.data_invio) AS ultima_interazione
              FROM utenti_presenza up
              JOIN chat c ON up.id_chat = c.id_chat
              LEFT JOIN messaggi m ON m.id_chat = c.id_chat AND m.id_autore = up.id_utente
              WHERE up.id_utente = %s
              GROUP BY c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo
            )
            UNION
            (
              SELECT c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo,
                      COUNT(m.id_messaggio) AS messaggi_utente,
                      MIN(m.data_invio) AS prima_interazione,
                      MAX(m.data_invio) AS ultima_interazione
              FROM messaggi m
              JOIN chat c ON c.id_chat = m.id_chat
              WHERE m.id_autore = %s
              GROUP BY c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo
            )
            ORDER BY (ultima_interazione IS NULL), ultima_interazione DESC, nome_chat

        """, (user_id, user_id))
        rows = cursor.fetchall()

        for r in rows:
            r["prima_interazione"] = to_iso_utc(r.get("prima_interazione"))
            r["ultima_interazione"] = to_iso_utc(r.get("ultima_interazione"))

        return jsonify({"status": "success", "data": rows})

    except Exception as e:
        logger.error(f"Errore DB in get_chat_utente: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


# =========================
# Ricerca chat per ID utente
# =========================
@app.route("/api/cerca_chat_per_utente/<int:user_id>", methods=["GET"])
def cerca_chat_per_utente(user_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            (
              SELECT c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo,
                      COUNT(m.id_messaggio) AS messaggi_utente,
                      MIN(m.data_invio) AS prima_interazione,
                      MAX(m.data_invio) AS ultima_interazione
              FROM utenti_presenza up
              JOIN chat c ON up.id_chat = c.id_chat
              LEFT JOIN messaggi m ON m.id_chat = c.id_chat AND m.id_autore = up.id_utente
              WHERE up.id_utente = %s
              GROUP BY c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo
            )
            UNION
            (
              SELECT c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo,
                      COUNT(m.id_messaggio) AS messaggi_utente,
                      MIN(m.data_invio) AS prima_interazione,
                      MAX(m.data_invio) AS ultima_interazione
              FROM messaggi m
              JOIN chat c ON c.id_chat = m.id_chat
              WHERE m.id_autore = %s
              GROUP BY c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo
            )
            ORDER BY (ultima_interazione IS NULL), ultima_interazione DESC, nome_chat

        """, (user_id, user_id))
        rows = cursor.fetchall()

        for r in rows:
            r["prima_interazione"] = to_iso_utc(r.get("prima_interazione"))
            r["ultima_interazione"] = to_iso_utc(r.get("ultima_interazione"))

        return jsonify({"status": "success", "data": rows})

    except Exception as e:
        logger.error(f"Errore DB in cerca_chat_per_utente: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


# =========================
# Ricerca in utenti.vue
# =========================
@app.route("/api/cerca", methods=["GET"])
def cerca():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        q = request.args.get("q", "").strip()
        user_id = request.args.get("id", "").strip()
        include_chats = request.args.get("include_chats", "false").lower() == "true"
        limit, offset = pag_params()

        result = {"users": []}

        # -------------------------
        # Ricerca per ID
        # -------------------------
        if user_id:
            if not user_id.isdigit():
                return jsonify({"status": "error", "message": "Parametro 'id' non valido"}), 400

            cursor.execute("""
                SELECT id, nome, username, foto_path, data_importazione
                FROM utenti WHERE id=%s
            """, (user_id,))
            user = cursor.fetchone()

            # 404 se l'utente NON esiste
            if not user:
                return jsonify({
                    "status": "error",
                    "message": f"Nessun utente trovato con ID {user_id}"
                }), 404

            # utente trovato
            user["nome"] = clean_nome(user.get("nome"), user.get("username"))
            user["data_importazione"] = to_iso_utc(user.get("data_importazione"))
            user["avatar_url"] = to_download_url(user.get("foto_path"))
            result["users"] = [user]

            # opzionale: includi chat dell'utente
            if include_chats:
                cursor.execute("""
                    (
                      SELECT c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo,
                             COUNT(m.id_messaggio) AS messaggi_utente,
                             MIN(m.data_invio) AS prima_interazione,
                             MAX(m.data_invio) AS ultima_interazione
                      FROM utenti_presenza up
                      JOIN chat c ON up.id_chat = c.id_chat
                      LEFT JOIN messaggi m ON m.id_chat = c.id_chat AND m.id_autore = up.id_utente
                      WHERE up.id_utente = %s
                      GROUP BY c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo
                    )
                    UNION
                    (
                      SELECT c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo,
                             COUNT(m.id_messaggio) AS messaggi_utente,
                             MIN(m.data_invio) AS prima_interazione,
                             MAX(m.data_invio) AS ultima_interazione
                      FROM messaggi m
                      JOIN chat c ON c.id_chat = m.id_chat
                      WHERE m.id_autore = %s
                      GROUP BY c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo
                    )
                    ORDER BY (ultima_interazione IS NULL), ultima_interazione DESC, nome_chat
                """, (user_id, user_id))
                chats = cursor.fetchall() or []

                for c in chats:
                    c["prima_interazione"] = to_iso_utc(c.get("prima_interazione"))
                    c["ultima_interazione"] = to_iso_utc(c.get("ultima_interazione"))
                result["chats"] = chats

        # -------------------------
        # Ricerca per nome/username
        # -------------------------
        elif q:
            like_pattern = f"%{q}%"
            cursor.execute("""
                SELECT id, nome, username, foto_path, data_importazione
                FROM utenti
                WHERE LOWER(nome) LIKE LOWER(%s) OR LOWER(username) LIKE LOWER(%s)
                ORDER BY data_importazione DESC
                LIMIT %s OFFSET %s
            """, (like_pattern, like_pattern, limit, offset))
            rows = cursor.fetchall()

            if not rows:
                return jsonify({
                    "status": "error",
                    "message": "Nessun utente trovato con la query specificata."
                }), 404

            for r in rows:
                r["nome"] = clean_nome(r.get("nome"), r.get("username"))
                r["data_importazione"] = to_iso_utc(r.get("data_importazione"))
                r["avatar_url"] = to_download_url(r.get("foto_path"))
            result["users"] = rows

        else:
            return jsonify({"status": "error", "message": "Specificare 'q' o 'id'"}), 400

        return jsonify({"status": "success", "data": result})

    except Exception as e:
        logger.error(f"Errore DB in cerca: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass



# =========================
# Presenza dell'utente (autocomplete chat)
# =========================
@app.route("/api/suggerisci_chat_per_utente", methods=["GET"])
def suggerisci_chat_per_utente():
    """
    Dato un id_prefix (ID utente parziale o completo),
    restituisce le chat/gruppi dove l'utente potrebbe essere.
    """
    id_prefix = request.args.get("id_prefix", "").strip()
    limit = min(10, int(request.args.get("limit", 5)))

    if not id_prefix or not id_prefix.isdigit():
        return jsonify({"status": "error", "message": "Parametro 'id_prefix' non valido"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        like_pattern = f"{id_prefix}%"

        cursor.execute("""
            (
              SELECT u.id, u.nome, u.username,
                      c.id_chat, c.nome_chat, c.tipo,
                      MAX(m.data_invio) AS ultima_interazione
              FROM utenti u
              JOIN utenti_presenza up ON u.id = up.id_utente
              JOIN chat c ON c.id_chat = up.id_chat
              LEFT JOIN messaggi m ON m.id_chat = c.id_chat AND m.id_autore = u.id
              WHERE CAST(u.id AS CHAR) LIKE %s
              GROUP BY u.id, u.nome, u.username, c.id_chat, c.nome_chat, c.tipo
            )
            UNION
            (
              SELECT u.id, u.nome, u.username,
                      c.id_chat, c.nome_chat, c.tipo,
                      MAX(m.data_invio) AS ultima_interazione
              FROM utenti u
              JOIN messaggi m ON m.id_autore = u.id
              JOIN chat c ON c.id_chat = m.id_chat
              WHERE CAST(u.id AS CHAR) LIKE %s
              GROUP BY u.id, u.nome, u.username, c.id_chat, c.nome_chat, c.tipo
            )
            ORDER BY (ultima_interazione IS NULL), ultima_interazione DESC, nome_chat

            LIMIT %s
        """, (like_pattern, like_pattern, limit))
        rows = cursor.fetchall()

        for r in rows:
            r["nome"] = clean_nome(r.get("nome"), r.get("username"))
            r["ultima_interazione"] = to_iso_utc(r.get("ultima_interazione"))

        return jsonify({"status": "success", "data": rows})

    except Exception as e:
        logger.error(f"Errore suggerimento chat per utente: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


@app.route("/api/graph", methods=["GET"])
def api_graph():
    limit = int(request.args.get("limit", 50))
    category = request.args.get("category")
    include_communities = request.args.get("communities", "0").lower() in ("1", "true", "yes")

    if category:
        q = """
        MATCH (u:Utente)-[r:REPLIED_TO]-(v:Utente)
        WHERE r.category = $category
          AND u.id IS NOT NULL AND v.id IS NOT NULL AND u.id <> v.id
        WITH u, sum(r.count) AS deg
        ORDER BY deg DESC
        LIMIT 10
        WITH collect(u.id) AS topIds

        MATCH (source:Utente)-[r:REPLIED_TO]->(target:Utente)
        WHERE (source.id IN topIds OR target.id IN topIds)
          AND r.category = $category
          AND source.id IS NOT NULL AND target.id IS NOT NULL
          AND source.id <> target.id
        WITH source, target, r,
             CASE WHEN source.id < target.id THEN source.id ELSE target.id END AS fromId,
             CASE WHEN source.id < target.id THEN target.id ELSE source.id END AS toId
        WITH fromId, toId,
             sum(r.count) AS peso,
             sum(CASE WHEN source.id < target.id THEN r.count ELSE 0 END) AS forward,
             sum(CASE WHEN source.id > target.id THEN r.count ELSE 0 END) AS reverse
        ORDER BY peso DESC
        LIMIT $limit

        MATCH (fromNode:Utente {id: fromId})
        MATCH (toNode:Utente {id: toId})
        WITH collect({from: fromId, to: toId, peso: peso,
                      forward: forward, reverse: reverse}) AS rels,
             collect(DISTINCT fromNode) + collect(DISTINCT toNode) AS utenti
        RETURN rels, utenti
        """
        params = {"limit": limit, "category": category}
    else:
        q = """
        MATCH (u:Utente)-[r:REPLIED_TO_GLOBAL]-(v:Utente)
        WHERE u.id IS NOT NULL AND v.id IS NOT NULL AND u.id <> v.id
        WITH u, sum(r.count) AS deg
        ORDER BY deg DESC
        LIMIT 10
        WITH collect(u.id) AS topIds

        MATCH (source:Utente)-[r:REPLIED_TO_GLOBAL]->(target:Utente)
        WHERE (source.id IN topIds OR target.id IN topIds)
          AND source.id IS NOT NULL AND target.id IS NOT NULL
          AND source.id <> target.id
        WITH source, target, r,
             CASE WHEN source.id < target.id THEN source.id ELSE target.id END AS fromId,
             CASE WHEN source.id < target.id THEN target.id ELSE source.id END AS toId
        WITH fromId, toId,
             sum(r.count) AS peso,
             sum(CASE WHEN source.id < target.id THEN r.count ELSE 0 END) AS forward,
             sum(CASE WHEN source.id > target.id THEN r.count ELSE 0 END) AS reverse
        ORDER BY peso DESC
        LIMIT $limit

        MATCH (fromNode:Utente {id: fromId})
        MATCH (toNode:Utente {id: toId})
        WITH collect({from: fromId, to: toId, peso: peso,
                      forward: forward, reverse: reverse}) AS rels,
             collect(DISTINCT fromNode) + collect(DISTINCT toNode) AS utenti
        RETURN rels, utenti
        """
        params = {"limit": limit}

    res = run_query(q, params)
    if not res:
        return jsonify({"nodes": [], "edges": []})

    rels = res[0]["rels"]
    utenti = res[0]["utenti"]

    connected_ids = {r["from"] for r in rels if r.get("from")} | \
                    {r["to"] for r in rels if r.get("to")}

    nodes = []
    seen_node_ids = set()
    for u in utenti:
        uid = u.get("id")
        if not uid or uid not in connected_ids or uid in seen_node_ids:
            continue
        seen_node_ids.add(uid)

        nodes.append({
            "id": f"user_{uid}",
            "label": u.get("username") or str(uid),
            "group": "Utente",
            "shape": "dot"
        })

    edges, seen_edges = [], set()
    for r in rels:
        if not r.get("from") or not r.get("to"):
            continue

        edge_key = tuple(sorted([r["from"], r["to"]]))
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        edges.append({
            "id": f"user_{r['from']}->user_{r['to']}",
            "from": f"user_{r['from']}",
            "to": f"user_{r['to']}",
            "label": str(r["peso"]),
            "value": r["peso"],
            "forward": int(r.get("forward") or 0),
            "reverse": int(r.get("reverse") or 0),
            "reciprocal": bool(r.get("forward") and r.get("reverse")),
            "reciprocity": round(
                (2 * min(r.get("forward") or 0, r.get("reverse") or 0)) / r["peso"],
                3,
            ) if r.get("peso") else 0,
        })

    payload = {"nodes": nodes, "edges": edges}
    if include_communities and not category:
        analysis = get_community_analysis(run_query)
        metrics_by_node = analysis["node_metrics"]
        labeled_communities = enrich_community_labels(analysis["communities"])
        labels_by_id = {
            community["id"]: community["label"]
            for community in labeled_communities
        }
        for node in nodes:
            user_id = int(node["id"].replace("user_", ""))
            metrics = metrics_by_node.get(user_id)
            if not metrics:
                continue
            node.update({
                "community": metrics["community"],
                "community_label": labels_by_id.get(metrics["community"]),
                "pagerank": metrics["pagerank"],
                "bridge_score": metrics["bridge_score"],
                "external_communities": metrics["external_communities"],
                "weighted_degree": metrics["weighted_degree"],
            })
        payload["community_analysis"] = {
            "summary": analysis["summary"],
            "communities": labeled_communities[:20],
            "bridges": analysis["bridges"][:20],
        }

    return jsonify(payload)


@app.route("/api/graph/community-analysis", methods=["GET"])
@cache.cached(timeout=300)
def api_graph_community_analysis():
    analysis = get_community_analysis(
        run_query,
        force=request.args.get("refresh", "0") in ("1", "true"),
    )
    return jsonify({
        "summary": analysis["summary"],
        "communities": enrich_community_labels(analysis["communities"]),
        "bridges": analysis["bridges"],
    })


# ===========================================================
# =====================   FOCUS   ===========================
# ===========================================================

@app.route("/api/graph/focus", methods=["GET"])
def api_graph_focus():
    focus_id = request.args.get("focusId")
    top = int(request.args.get("top", 5))
    category = request.args.get("category")   # ✅ IMPORTANTE

    if not focus_id:
        return jsonify({"error": "focusId richiesto"}), 400

    # ---------- RISOLVO focusId ----------
    if focus_id.isdigit() or (focus_id.startswith("-") and focus_id[1:].isdigit()):
        fid = int(focus_id)
    else:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT id FROM utenti WHERE LOWER(username) = LOWER(%s)",
                (focus_id,)
            )
            row = cursor.fetchone()
            if not row:
                return jsonify({"error": "Nessun utente trovato"}), 404
            fid = row["id"]
        finally:
            cursor.close()
            conn.close()

    # =====================================================
    # CASO CHAT (focusId è una chat)
    # =====================================================
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id_chat, nome_chat FROM chat WHERE id_chat = %s", (fid,))
    chat_row = cursor.fetchone()

    if chat_row:
        cursor.execute("""
            SELECT m.id_autore AS id_utente, COUNT(*) AS messaggi
            FROM messaggi m
            WHERE m.id_chat = %s AND m.id_autore > 0
            GROUP BY m.id_autore
            ORDER BY messaggi DESC
            LIMIT %s
        """, (fid, top))
        top_users = cursor.fetchall()

        if not top_users:
            cursor.close()
            conn.close()
            return jsonify({"nodes": [], "edges": [], "has_more": False})

        user_ids = [r["id_utente"] for r in top_users]

        placeholders = ",".join(["%s"] * len(user_ids))
        cursor.execute(f"""
            SELECT id, nome, username
            FROM utenti
            WHERE id IN ({placeholders})
        """, tuple(user_ids))
        user_infos = {u["id"]: u for u in cursor.fetchall()}

        cursor.close()
        conn.close()

        nodes = []
        for r in top_users:
            uid = r["id_utente"]
            info = user_infos.get(uid, {})
            label = info.get("username") or info.get("nome") or str(uid)

            nodes.append({
                "id": f"user_{uid}",
                "label": label,
                "group": "Utente",
                "title": f"{label}\nMessaggi: {r['messaggi']}",
                "value": r['messaggi']
            })

        q_edges = """
        UNWIND $ids AS uid1
        UNWIND $ids AS uid2
        WITH uid1, uid2
        WHERE uid1 < uid2

        OPTIONAL MATCH (u1:Utente {id: uid1})-[r1:REPLIED_TO {chatId: $chatId}]->(u2:Utente {id: uid2})
        OPTIONAL MATCH (u2b:Utente {id: uid2})-[r2:REPLIED_TO {chatId: $chatId}]->(u1b:Utente {id: uid1})

        WITH uid1 AS da, uid2 AS a,
             coalesce(r1.count, 0) AS forward,
             coalesce(r2.count, 0) AS reverse,
             coalesce(r1.count, 0) + coalesce(r2.count, 0) AS peso
        WHERE peso > 0
        RETURN da, a, peso, forward, reverse
        """

        res_edges = run_query(q_edges, {"ids": user_ids, "chatId": fid}) or []

        edges = [
            {
                "id": f"user_{r['da']}->user_{r['a']}",
                "from": f"user_{r['da']}",
                "to": f"user_{r['a']}",
                "label": str(r["peso"]),
                "value": r["peso"],
                "forward": int(r.get("forward") or 0),
                "reverse": int(r.get("reverse") or 0),
                "reciprocal": bool(r.get("forward") and r.get("reverse")),
                "reciprocity": round(
                    (2 * min(r.get("forward") or 0, r.get("reverse") or 0)) / r["peso"],
                    3,
                ) if r.get("peso") else 0,
            }
            for r in res_edges
        ]

        return jsonify({
            "nodes": list({n["id"]: n for n in nodes}.values()),
            "edges": list({e["id"]: e for e in edges}.values()),
            "has_more": len(top_users) == top
        })

    # =====================================================
    # CASO UTENTE
    # =====================================================
    cursor.close()
    conn.close()

    params = {"focusId": fid, "top": top}

    if category:
        rel_type = "REPLIED_TO"
        node_filter = "AND r.category = $category"
        edge_filter1 = "WHERE r1 IS NULL OR r1.category = $category"
        edge_filter2 = "WHERE r2 IS NULL OR r2.category = $category"
        params["category"] = category
    else:
        rel_type = "REPLIED_TO_GLOBAL"
        node_filter = ""
        edge_filter1 = ""
        edge_filter2 = ""

    # 1️⃣ Trovo vicini top
    q = f"""
    MATCH (u:Utente {{id:$focusId}})-[r:{rel_type}]-(v:Utente)
    WHERE v.id IS NOT NULL AND u.id <> v.id
    {node_filter}
    WITH v, sum(r.count) AS totReply
    ORDER BY totReply DESC
    LIMIT $top
    RETURN v.id AS vicino, totReply
    """

    top_nodes = run_query(q, params) or []

    if not top_nodes:
        return jsonify({"nodes": [], "edges": [], "has_more": False})

    top_ids = [r["vicino"] for r in top_nodes]
    params["topIds"] = top_ids

    # 2️⃣ Archi bidirezionali
    q_edges = f"""
    UNWIND $topIds AS vid

    OPTIONAL MATCH (u:Utente {{id:$focusId}})-[r1:{rel_type}]->(v:Utente {{id: vid}})
    {edge_filter1}
    WITH vid, coalesce(sum(r1.count), 0) AS focusTo

    OPTIONAL MATCH (v2:Utente {{id: vid}})-[r2:{rel_type}]->(u2:Utente {{id:$focusId}})
    {edge_filter2}

    WITH vid, focusTo, coalesce(sum(r2.count), 0) AS toFocus
    WITH vid, focusTo, toFocus, focusTo + toFocus AS peso
    WHERE peso > 0

    WITH
        CASE WHEN $focusId < vid THEN $focusId ELSE vid END AS da,
        CASE WHEN $focusId < vid THEN vid ELSE $focusId END AS a,
        peso,
        CASE WHEN $focusId < vid THEN focusTo ELSE toFocus END AS forward,
        CASE WHEN $focusId < vid THEN toFocus ELSE focusTo END AS reverse
    RETURN DISTINCT da, a, peso, forward, reverse
    """

    res_edges = run_query(q_edges, params) or []

    # 3️⃣ Info utenti da MySQL
    all_ids = list(set(top_ids + [fid]))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    placeholders = ",".join(["%s"] * len(all_ids))
    cursor.execute(
        f"SELECT id, nome, username FROM utenti WHERE id IN ({placeholders})",
        tuple(all_ids)
    )
    user_infos = {u["id"]: u for u in cursor.fetchall()}
    cursor.close()
    conn.close()

    nodes = []
    for uid in all_ids:
        info = user_infos.get(uid, {})
        label = info.get("username") or info.get("nome") or str(uid)

        nodes.append({
            "id": f"user_{uid}",
            "label": label,
            "group": "Utente",
            "title": label + (" (focus)" if uid == fid else "")
        })

    edges = []
    seen_edges = set()
    for r in res_edges:
        da, a, peso = r["da"], r["a"], r["peso"]
        edge_key = (min(da, a), max(da, a))
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        edges.append({
            "id": f"user_{da}->user_{a}",
            "from": f"user_{da}",
            "to": f"user_{a}",
            "label": str(peso),
            "value": peso,
            "forward": int(r.get("forward") or 0),
            "reverse": int(r.get("reverse") or 0),
            "reciprocal": bool(r.get("forward") and r.get("reverse")),
            "reciprocity": round(
                (2 * min(r.get("forward") or 0, r.get("reverse") or 0)) / peso,
                3,
            ) if peso else 0,
        })

    return jsonify({
        "nodes": list({n["id"]: n for n in nodes}.values()),
        "edges": edges,
        "has_more": len(top_nodes) == top
    })

# =========================
# Top utenti
# =========================
@app.route("/api/top_utenti", methods=["GET"])
@cache.cached(timeout=60, key_prefix="top_utenti")
def get_top_utenti():
    limit = int(request.args.get("limit", 5))
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Query: Estrazione dell'ID corto corretto (senza -100) per la JOIN
        cursor.execute("""
            SELECT
                m.id_autore,
                COUNT(m.id_messaggio) AS messaggi,
                u.nome AS u_nome,
                u.username AS u_user,
                c_auth.nome_chat AS c_nome_auth,
                c_auth.nome_chat_tradotto AS c_nome_tradotto_auth
            FROM messaggi m
            LEFT JOIN utenti u ON u.id = m.id_autore

            -- ⚠️ NUOVA LOGICA DI JOIN:
            -- Se id_autore è negativo (-100xxxx), prendiamo ABS(SUBSTRING(id_autore, 2)) che diventa xxxx.
            -- Se id_autore è positivo, usiamo semplicemente l'id_autore.
            LEFT JOIN chat c_auth ON c_auth.id_chat =
                CASE
                    WHEN m.id_autore < 0 THEN ABS(CAST(SUBSTRING(CAST(m.id_autore AS CHAR), 5) AS SIGNED))
                    ELSE m.id_autore
                END

            WHERE m.id_autore IS NOT NULL
            -- La GROUP BY DEVE includere tutti i campi non aggregati
            GROUP BY m.id_autore, u.nome, u.username, c_auth.nome_chat, c_auth.nome_chat_tradotto
            ORDER BY messaggi DESC
            LIMIT %s
        """, (limit,))

        rows = cursor.fetchall()

        # Post-processing per costruire il nome (non è cambiato)
        data = []
        for r in rows:
            id_autore = r["id_autore"]
            nome_chat = r.get("c_nome_auth")
            nome_chat_tradotto = r.get("c_nome_tradotto_auth")

            # 🔹 Logica nome:
            if r["u_nome"] or r["u_user"]:
                # 1. Utente
                nome = clean_nome(r["u_nome"], r["u_user"])
                is_channel = False
            elif id_autore < 0 and (nome_chat or nome_chat_tradotto):
                # 2. Canale Esterno/Ufficiale trovato (grazie al fix della JOIN)
                nome = nome_chat_tradotto or nome_chat
                nome = nome + " (Canale)"
                is_channel = True
            else:
                # 3. Fallback (Nome chat non trovato)
                nome = f"Canale Esterno {abs(id_autore)}" if id_autore < 0 else f"Utente Sconosciuto {id_autore}"
                is_channel = id_autore < 0

            data.append({
                "id": id_autore,
                "nome": nome,
                "username": r["u_user"],
                "messaggi": r["messaggi"],
                "is_channel": is_channel
            })

        return jsonify({"status": "success", "data": data})
    except Exception as e:
        logger.error(f"Errore DB in get_top_utenti: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno del server"}), 500
    finally:
        try:
            if 'cursor' in locals() and cursor is not None: cursor.close()
            if 'conn' in locals() and conn is not None: conn.close()
        except Exception:
            pass


# =========================
# Top chat (per numero di messaggi) - AGGIORNATO con flag is_channel
# =========================
@app.route("/api/top_chat", methods=["GET"])
@cache.cached(timeout=60, key_prefix="top_chat")
def get_top_chat():
    limit = int(request.args.get("limit", 5))
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo,
                   COUNT(m.id_messaggio) AS messaggi
            FROM chat c
            JOIN messaggi m ON m.id_chat = c.id_chat
            GROUP BY c.id_chat, c.nome_chat, c.nome_chat_tradotto, c.tipo
            ORDER BY messaggi DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()

        # Aggiungi flag is_channel
        for r in rows:
            r["is_channel"] = r["id_chat"] < 0

        return jsonify({"status": "success", "data": rows})
    except Exception as e:
        logger.error(f"Errore in get_top_chat: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


# =========================
# Chat per categoria
# =========================
@app.route("/api/chat_per_categoria", methods=["GET"])
def get_chat_per_categoria():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT categoria_chat, COUNT(*) AS totale
            FROM chat
            GROUP BY categoria_chat
            ORDER BY totale DESC
        """)
        rows = cursor.fetchall()

        return jsonify({
            "status": "success",
            "data": rows
        })
    except Exception as e:
        logger.error(f"Errore in get_chat_per_categoria: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Errore interno"}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


@app.route("/api/graph/keyword", methods=["GET"])
def api_graph_keyword():
    keyword = request.args.get("term", "").strip()
    category = request.args.get("category")

    if not keyword:
        return jsonify({"nodes": [], "edges": [], "keyword_edges": [], "keyword_stats": {}}), 400

    max_users = int(request.args.get("maxUsers", 50))
    min_count = int(request.args.get("minCount", 1))
    max_targets = int(request.args.get("maxTargets", 30))

    kw = keyword.lower()

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # ============================
        # 1️⃣ TOP UTENTI CON KEYWORD
        # ============================

        cat_join = ""
        cat_where = ""
        params_mysql = [kw, kw, kw]

        if category:
            cat_join = "JOIN chat c ON m.id_chat = c.id_chat"
            cat_where = "AND c.categoria_chat = %s"
            params_mysql.append(category)

        params_mysql.extend([min_count, max_users])

        cursor.execute(f"""
            SELECT m.id_autore,
                   COUNT(*) AS kw_count,
                   SUM(LENGTH(m.testo) - LENGTH(REPLACE(LOWER(m.testo), %s, '')))
                   / LENGTH(%s) AS kw_frequency
            FROM messaggi m
            {cat_join}
            WHERE m.id_autore IS NOT NULL
              AND m.id_autore > 0
              AND MATCH(m.testo) AGAINST(%s IN BOOLEAN MODE)
              {cat_where}
            GROUP BY m.id_autore
            HAVING kw_count >= %s
            ORDER BY kw_frequency DESC, kw_count DESC
            LIMIT %s
        """, tuple(params_mysql))

        raw_users = cursor.fetchall()

        if not raw_users:
            return jsonify({"nodes": [], "edges": [], "keyword_edges": [], "keyword_stats": {}})

        user_ids_kw = [u["id_autore"] for u in raw_users]
        keyword_stats = {u["id_autore"]: int(u["kw_count"]) for u in raw_users}

        # ============================
        # 2️⃣ RELAZIONI AGGREGATE (MySQL)
        # ============================

        placeholders = ",".join(["%s"] * len(user_ids_kw))

        params_rel = [kw, kw] + user_ids_kw + user_ids_kw + [kw, kw]
        if category:
            params_rel.append(category)

        cursor.execute(f"""
            SELECT
                LEAST(m.id_autore, m2.id_autore) AS da,
                GREATEST(m.id_autore, m2.id_autore) AS a,
                COUNT(*) AS kw_count_rel,
                SUM(CASE WHEN MATCH(m.testo) AGAINST(%s IN BOOLEAN MODE) THEN 1 ELSE 0 END) AS kw_in_reply,
                SUM(CASE WHEN MATCH(m2.testo) AGAINST(%s IN BOOLEAN MODE) THEN 1 ELSE 0 END) AS kw_in_original
            FROM messaggi m
            JOIN messaggi m2
              ON m.reply_to_msg_id = m2.id_messaggio
             AND m.id_chat = m2.id_chat
            {cat_join}
            WHERE m.id_autore IS NOT NULL
              AND m.id_autore > 0
              AND m2.id_autore IS NOT NULL
              AND m2.id_autore > 0
              AND m.id_autore <> m2.id_autore
              AND (
                  m.id_autore IN ({placeholders})
                  OR m2.id_autore IN ({placeholders})
              )
              AND (
                  MATCH(m.testo) AGAINST(%s IN BOOLEAN MODE)
                  OR MATCH(m2.testo) AGAINST(%s IN BOOLEAN MODE)
              )
              {cat_where}
            GROUP BY da, a
            HAVING kw_count_rel > 0
        """, tuple(params_rel))

        kw_rel_aggregated = cursor.fetchall()

        # Conta i destinatari più attivi
        target_count_map = {}
        for r in kw_rel_aggregated:
            target_count_map[r["da"]] = target_count_map.get(r["da"], 0) + r["kw_count_rel"]
            target_count_map[r["a"]] = target_count_map.get(r["a"], 0) + r["kw_count_rel"]

        top_targets = sorted(
            target_count_map,
            key=target_count_map.get,
            reverse=True
        )[:max_targets]

        target_set = set(top_targets)

        kw_rel_filtered = [
            r for r in kw_rel_aggregated
            if r["da"] in target_set and r["a"] in target_set
        ]

        # ============================
        # 3️⃣ NODI E NOMI
        # ============================

        all_user_ids = sorted(set(user_ids_kw) | target_set)

        placeholders_users = ",".join(["%s"] * len(all_user_ids))

        cursor.execute(
            f"SELECT id, nome, username FROM utenti WHERE id IN ({placeholders_users})",
            tuple(all_user_ids)
        )
        user_map = {u["id"]: u for u in cursor.fetchall()}

        cursor.execute(
            f"SELECT id_chat as id, nome_chat as nome FROM chat WHERE id_chat IN ({placeholders_users})",
            tuple(all_user_ids)
        )
        chat_map = {c["id"]: c for c in cursor.fetchall()}

        # ============================
        # 4️⃣ RELAZIONI NEO4J (CORRETTE)
        # ============================

        neo_params = {"ids": all_user_ids}

        if category:
            rel_type = "REPLIED_TO"
            where_edge1 = "WHERE r1.category = $category"
            where_edge2 = "WHERE r2.category = $category"
            neo_params["category"] = category
        else:
            rel_type = "REPLIED_TO_GLOBAL"
            where_edge1 = ""
            where_edge2 = ""

        q_edges_keyword_fix = f"""
        UNWIND $ids AS uid1
        UNWIND $ids AS uid2
        WITH uid1, uid2
        WHERE uid1 < uid2

        OPTIONAL MATCH (u1:Utente {{id: uid1}})-[r1:{rel_type}]->(u2:Utente {{id: uid2}})
        {where_edge1}

        OPTIONAL MATCH (u2b:Utente {{id: uid2}})-[r2:{rel_type}]->(u1b:Utente {{id: uid1}})
        {where_edge2}

        WITH uid1 AS da, uid2 AS a,
             coalesce(r1.count, 0) + coalesce(r2.count, 0) AS peso
        WHERE peso > 0
        RETURN da, a, peso
        """

        neo_edges = run_query(q_edges_keyword_fix, neo_params) or []

        kw_pairs = set((r["da"], r["a"]) for r in kw_rel_filtered)

        # ============================
        # 5️⃣ COSTRUZIONE JSON FINALE
        # ============================

        nodes = []
        for uid in all_user_ids:
            if uid in user_map:
                label = user_map[uid].get("username") or user_map[uid].get("nome")
            else:
                label = chat_map.get(uid, {}).get("nome", f"Utente {uid}")

            kw_count = keyword_stats.get(uid, 0)

            nodes.append({
                "id": f"user_{uid}",
                "label": label,
                "shape": "dot",
                "hasKeyword": kw_count > 0,
                "keyword_count": kw_count,
                "title": f"{label}\n{kw_count} occorrenze" if kw_count > 0 else label
            })

        edges = []
        for r in neo_edges:
            da, a, peso = r["da"], r["a"], r["peso"]

            edges.append({
                "id": f"e_{da}_{a}",
                "from": f"user_{da}",
                "to": f"user_{a}",
                "value": peso,
                "label": str(peso),
                "hasKeyword": (da, a) in kw_pairs or (a, da) in kw_pairs
            })

        keyword_edges = []
        for r in kw_rel_filtered:
            da, a = r["da"], r["a"]
            count = r["kw_count_rel"]
            kw_total = r["kw_in_reply"] + r["kw_in_original"]

            keyword_edges.append({
                "id": f"kw_{da}_{a}",
                "from": f"user_{da}",
                "to": f"user_{a}",
                "value": count,
                "label": str(count),
                "hasKeyword": True,
                "kw_in_reply": r["kw_in_reply"],
                "kw_in_original": r["kw_in_original"],
                "keyword_total": kw_total
            })

        return jsonify({
            "nodes": nodes,
            "edges": edges,
            "keyword_edges": keyword_edges,
            "keyword_stats": keyword_stats
        })

    except Exception as e:
        logger.error(f"Errore in api_graph_keyword: {e}", exc_info=True)
        return jsonify({"error": "Errore interno del server"}), 500

    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


@app.route("/api/admins/<int:chat_id>", methods=["GET"])
def get_admins(chat_id):
    import os, json

    admin_json_path = os.path.join(os.path.dirname(__file__), "admins.json")

    if not os.path.exists(admin_json_path):
        return jsonify({"status": "error", "message": "admins.json non trovato"}), 404

    with open(admin_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return jsonify({
        "status": "success",
        "chat_id": chat_id,
        "admins": data.get(str(chat_id), [])
    })

# =========================
# SYSTEM: IMPORT LOCK
# =========================
# Evita che due scansioni per la stessa chat vengano avviate insieme
ACTIVE_IMPORTS = set()

# =========================
# IMPORT API ROUTES
# =========================
@app.route('/api/importa_chat', methods=['POST'])
def api_importa_chat():
    data = request.json
    target = str(data.get('target'))  # Sempre stringa
    mode = data.get('mode', 'incrementale')

    if not target:
        return jsonify({"error": "Target mancante"}), 400

    # BLOCCO: evita doppia scansione concorrente della stessa chat
    if target in ACTIVE_IMPORTS:
        return jsonify({
            "status": "running",
            "message": f"Scansione già in corso per {target}"
        }), 409

    ACTIVE_IMPORTS.add(target)

    def task_wrapper():
        try:
            start_import_process(target, mode)
        finally:
            # A fine importazione sblocca la chat
            ACTIVE_IMPORTS.discard(target)

    thread = threading.Thread(target=task_wrapper)
    thread.daemon = True
    thread.start()

    return jsonify({
        "status": "started",
        "message": f"Scansione avviata per {target}"
    })


@app.route('/api/import_status/<target>', methods=['GET'])
def api_import_status(target):
    key = str(target)
    # Se lo stato non è presente, assumiamo che sia terminato (IDLE)
    status = IMPORT_STATUS.get(key, {"status": "idle", "progress": "ℹ️ Scansione completata (non più in memoria)."})

    # ⚠️ FIX: Se Flask restituisce 404, il frontend entra in errore.
    # Restituire sempre 200 OK, anche se lo stato è IDLE.
    return jsonify(status)

@app.route('/api/telegram_status', methods=['GET'])
def api_telegram_status():
    """
    Endpoint per verificare lo stato della sessione Telegram.
    Utile per mostrare nel frontend se l'autenticazione è OK.
    """
    try:
        status = get_session_status_sync()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Errore verifica stato Telegram: {e}", exc_info=True)
        return jsonify({
            "authenticated": False,
            "message": f"Errore: {str(e)}"
        }), 500


# =========================
# OSINT - Maigret Integration
# =========================

# Cartella report (deve corrispondere a quella in maigret_service)
OSINT_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "osint_reports")

@app.route("/api/osint/<username>/report", methods=["GET"])
def get_osint_report(username):
    """Restituisce il report HTML se esiste"""
    try:
        # Cerca il file report
        reports_dir = Path(OSINT_REPORTS_DIR)
        if not reports_dir.exists():
            return jsonify({"status": "not_found", "message": "Nessun report disponibile"}), 404

        # Cerca file che contiene l'username
        report_file = None
        for f in reports_dir.glob(f"*{username}*.html"):
            report_file = f
            break

        if not report_file or not report_file.exists():
            return jsonify({"status": "not_found", "message": "Report non trovato"}), 404

        # Ritorna info sul file
        return jsonify({
            "status": "success",
            "username": username,
            "report_file": report_file.name,
            "report_url": f"/api/osint/{username}/report/view",
            "created_at": datetime.fromtimestamp(report_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        })

    except Exception as e:
        logger.error(f"Errore recupero report OSINT: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/osint/<username>/report/view", methods=["GET"])
def view_osint_report(username):
    """Serve il file HTML del report"""
    try:
        reports_dir = Path(OSINT_REPORTS_DIR)

        # Cerca il file
        report_file = None
        for f in reports_dir.glob(f"*{username}*.html"):
            report_file = f
            break

        if not report_file or not report_file.exists():
            return "Report non trovato", 404

        return send_from_directory(str(reports_dir), report_file.name, mimetype='text/html')

    except Exception as e:
        logger.error(f"Errore view report: {e}")
        return f"Errore: {str(e)}", 500


@app.route("/api/osint/<username>/search", methods=["POST"])
def search_osint(username):
    """Avvia una ricerca OSINT per un username"""
    try:
        from maigret_service import queue_maigret_request, get_request_status

        current_status = get_request_status(username)
        if current_status.get("status") in ["queued", "processing"]:
            return jsonify({
                "status": current_status["status"],
                "message": current_status["message"]
            })

        queue_maigret_request(username)

        return jsonify({
            "status": "queued",
            "message": "⏳ Ricerca OSINT avviata. Attendere 1-2 minuti..."
        })

    except ImportError:
        return jsonify({"status": "error", "message": "❌ Servizio Maigret non configurato"}), 501
    except Exception as e:
        logger.error(f"Errore richiesta OSINT: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/osint/<username>/status", methods=["GET"])
def get_osint_status(username):
    """Controlla lo stato di una richiesta OSINT"""
    try:
        from maigret_service import get_request_status
        status = get_request_status(username)
        return jsonify(status)
    except ImportError:
        return jsonify({"status": "idle", "message": "Servizio non attivo"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# =========================
# SangMata - Storico Username
# =========================

@app.route("/api/sangmata/search/<int:user_id>", methods=["POST"])
def start_sangmata_search(user_id):
    """Avvia la ricerca dello storico username in background"""
    try:
        queue_sangmata_request(user_id)
        return jsonify({"status": "queued", "message": "⏳ Ricerca storico avviata..."})
    except Exception as e:
        logger.error(f"Errore avvio SangMata: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/sangmata/status/<int:user_id>", methods=["GET"])
def check_sangmata_status(user_id):
    """Controlla lo stato della ricerca SangMata"""
    status = get_sangmata_status(user_id)
    return jsonify(status)

@app.route("/api/utente/<int:user_id>/storico", methods=["GET"])
def get_utente_storico(user_id):
    """Recupera i record dello storico salvati nel database"""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT username, first_name, last_name, rilevato_il, fonte
            FROM storico_username
            WHERE user_id = %s
            ORDER BY rilevato_il DESC
        """, (user_id,))
        rows = cursor.fetchall()

        for r in rows:
            r["rilevato_il"] = to_iso_utc(r["rilevato_il"])

        return jsonify({"status": "success", "data": rows})
    except Exception as e:
        logger.error(f"Errore recupero storico DB: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()



# =========================
# Main
# =========================
if __name__ == "__main__":
    app.run(
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
