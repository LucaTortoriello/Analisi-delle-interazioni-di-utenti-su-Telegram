import mysql.connector
from Neo4jConnector2_0 import run_query, close_driver
from datetime import datetime

BATCH_SIZE = 5000

# Connessione MySQL
mysql_conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="analisiutentitelegram",
    charset="utf8mb4"
)
mysql_cur = mysql_conn.cursor(dictionary=True)


def ensure_indexes():
    print("⚙️ Creo indici...")
    run_query("CREATE INDEX user_id IF NOT EXISTS FOR (u:Utente) ON (u.id)")


def full_cleanup():
    """Elimina TUTTE le relazioni esistenti"""
    print("\n🧹 PULIZIA COMPLETA...")
    
    # Conta prima
    result = run_query("MATCH ()-[r:REPLIED_TO]->() RETURN count(r) AS cnt")
    cnt1 = result[0]['cnt'] if result else 0
    
    result = run_query("MATCH ()-[r:REPLIED_TO_GLOBAL]->() RETURN count(r) AS cnt")
    cnt2 = result[0]['cnt'] if result else 0
    
    print(f"   Relazioni da eliminare: REPLIED_TO={cnt1}, REPLIED_TO_GLOBAL={cnt2}")
    
    # Elimina in batch per evitare timeout
    print("   Eliminazione REPLIED_TO...")
    while True:
        result = run_query("""
            MATCH ()-[r:REPLIED_TO]->()
            WITH r LIMIT 50000
            DELETE r
            RETURN count(*) AS deleted
        """)
        deleted = result[0]['deleted'] if result else 0
        if deleted == 0:
            break
        print(f"      Eliminate {deleted} relazioni...")
    
    print("   Eliminazione REPLIED_TO_GLOBAL...")
    while True:
        result = run_query("""
            MATCH ()-[r:REPLIED_TO_GLOBAL]->()
            WITH r LIMIT 50000
            DELETE r
            RETURN count(*) AS deleted
        """)
        deleted = result[0]['deleted'] if result else 0
        if deleted == 0:
            break
        print(f"      Eliminate {deleted} relazioni...")
    
    # Verifica
    result = run_query("MATCH ()-[r:REPLIED_TO]->() RETURN count(r) AS cnt")
    result2 = run_query("MATCH ()-[r:REPLIED_TO_GLOBAL]->() RETURN count(r) AS cnt")
    print(f"   ✅ Dopo pulizia: REPLIED_TO={result[0]['cnt']}, REPLIED_TO_GLOBAL={result2[0]['cnt']}")


def sync_from_mysql():
    """Crea relazioni fresche da MySQL"""
    
    print("\n📊 ESTRAZIONE DA MYSQL...")
    
    # 🔹 MODIFICA: Join con tabella chat per prendere la categoria
    mysql_cur.execute("""
        SELECT 
            r.id_chat AS chatId,
            COALESCE(c.categoria_chat, 'Altro') AS category,
            r.id_autore AS autore, 
            m.id_autore AS destinatario,
            COUNT(*) AS freq
        FROM messaggi r
        JOIN messaggi m 
          ON r.reply_to_msg_id = m.id_messaggio
         AND r.id_chat = m.id_chat
        JOIN chat c ON r.id_chat = c.id_chat
        WHERE r.reply_to_msg_id IS NOT NULL
          AND TRIM(r.reply_to_msg_id) != ''
          AND r.reply_to_msg_id != '0'
          AND m.id_autore > 0
          AND r.id_autore > 0
          AND r.id_autore <> m.id_autore
        GROUP BY r.id_chat, c.categoria_chat, r.id_autore, m.id_autore
    """)
    chat_rows = mysql_cur.fetchall()
    print(f"   Coppie per chat: {len(chat_rows)}")
    
    # Query per relazioni GLOBALI (somma tutte le chat)
    mysql_cur.execute("""
        SELECT 
            r.id_autore AS autore, 
            m.id_autore AS destinatario,
            COUNT(*) AS freq
        FROM messaggi r
        JOIN messaggi m 
          ON r.reply_to_msg_id = m.id_messaggio
         AND r.id_chat = m.id_chat
        WHERE r.reply_to_msg_id IS NOT NULL
          AND TRIM(r.reply_to_msg_id) != ''
          AND r.reply_to_msg_id != '0'
          AND m.id_autore > 0
          AND r.id_autore > 0
          AND r.id_autore <> m.id_autore
        GROUP BY r.id_autore, m.id_autore
    """)
    global_rows = mysql_cur.fetchall()
    print(f"   Coppie globali: {len(global_rows)}")
    
    # INSERIMENTO RELAZIONI PER CHAT (CON CATEGORIA)
    print("\n📥 INSERIMENTO REPLIED_TO (per chat)...")
    for i in range(0, len(chat_rows), BATCH_SIZE):
        batch = chat_rows[i:i+BATCH_SIZE]
        
        # 🔹 MODIFICA: Aggiunta property 'category' alla relazione
        run_query("""
            UNWIND $batch AS row
            MERGE (u1:Utente {id: row.autore})
            MERGE (u2:Utente {id: row.destinatario})
            CREATE (u1)-[r:REPLIED_TO {
                chatId: row.chatId, 
                category: row.category, 
                count: row.freq
            }]->(u2)
        """, {"batch": batch})
        
        print(f"   ✔ {min(i+BATCH_SIZE, len(chat_rows))}/{len(chat_rows)}")
    
    # INSERIMENTO RELAZIONI GLOBALI
    print("\n📥 INSERIMENTO REPLIED_TO_GLOBAL...")
    for i in range(0, len(global_rows), BATCH_SIZE):
        batch = global_rows[i:i+BATCH_SIZE]
        
        run_query("""
            UNWIND $batch AS row
            MERGE (u1:Utente {id: row.autore})
            MERGE (u2:Utente {id: row.destinatario})
            CREATE (u1)-[r:REPLIED_TO_GLOBAL {count: row.freq}]->(u2)
        """, {"batch": batch})
        
        print(f"   ✔ {min(i+BATCH_SIZE, len(global_rows))}/{len(global_rows)}")


def verify():
    """Verifica finale"""
    print("\n🔍 VERIFICA FINALE...")
    
    # Conta in Neo4j
    result = run_query("MATCH ()-[r:REPLIED_TO]->() RETURN count(r) AS cnt, sum(r.count) AS total")
    neo_chat = result[0] if result else {'cnt': 0, 'total': 0}
    
    result = run_query("MATCH ()-[r:REPLIED_TO_GLOBAL]->() RETURN count(r) AS cnt, sum(r.count) AS total")
    neo_global = result[0] if result else {'cnt': 0, 'total': 0}
    
    # Conta in MySQL
    mysql_cur.execute("""
        SELECT COUNT(*) AS total
        FROM messaggi r
        JOIN messaggi m 
          ON r.reply_to_msg_id = m.id_messaggio
         AND r.id_chat = m.id_chat
        WHERE r.reply_to_msg_id IS NOT NULL
          AND TRIM(r.reply_to_msg_id) != ''
          AND r.reply_to_msg_id != '0'
          AND m.id_autore > 0
          AND r.id_autore > 0
          AND r.id_autore <> m.id_autore
    """)
    mysql_total = mysql_cur.fetchone()['total']
    
    print(f"\n   REPLIED_TO:        {neo_chat['cnt']} relazioni, {neo_chat['total']} reply")
    print(f"   REPLIED_TO_GLOBAL: {neo_global['cnt']} relazioni, {neo_global['total']} reply")
    print(f"   MySQL totale:      {mysql_total} reply")
    
    match = "✅ MATCH!" if neo_global['total'] == mysql_total else "❌ MISMATCH!"
    print(f"\n   {match}")
    
    # Test su campione
    print("\n📋 VERIFICA CAMPIONE (top 5):")
    print(f"   {'FROM':<12} {'TO':<12} {'NEO4J':<8} {'MYSQL':<8} {'OK'}")
    print("   " + "-" * 52)
    
    samples = run_query("""
        MATCH (u1:Utente)-[r:REPLIED_TO_GLOBAL]->(u2:Utente)
        RETURN u1.id AS from_id, u2.id AS to_id, r.count AS neo_count
        ORDER BY r.count DESC
        LIMIT 5
    """)
    
    all_match = True
    for s in samples:
        mysql_cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM messaggi r
            JOIN messaggi m 
              ON r.reply_to_msg_id = m.id_messaggio
             AND r.id_chat = m.id_chat
            WHERE r.id_autore = %s AND m.id_autore = %s
              AND r.reply_to_msg_id IS NOT NULL
              AND TRIM(r.reply_to_msg_id) != ''
              AND r.reply_to_msg_id != '0'
        """, (s['from_id'], s['to_id']))
        mysql_cnt = mysql_cur.fetchone()['cnt']
        
        ok = "✅" if s['neo_count'] == mysql_cnt else "❌"
        if s['neo_count'] != mysql_cnt:
            all_match = False
        print(f"   {s['from_id']:<12} {s['to_id']:<12} {s['neo_count']:<8} {mysql_cnt:<8} {ok}")
    
    return all_match


def main():
    print("=" * 70)
    print("🚀 SYNC NEO4J - RESET COMPLETO CON CATEGORIE")
    print("=" * 70)
    print(f"⏰ Inizio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    ensure_indexes()
    full_cleanup()
    sync_from_mysql()
    success = verify()
    
    print("\n" + "=" * 70)
    if success:
        print("✅ SYNC COMPLETATO CON SUCCESSO!")
    else:
        print("⚠️ SYNC COMPLETATO MA CON DISCREPANZE - VERIFICA MANUALMENTE")
    print(f"⏰ Fine: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    finally:
        mysql_cur.close()
        mysql_conn.close()
        close_driver()