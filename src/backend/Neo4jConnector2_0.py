# Neo4jConnector2_0.py
from neo4j import GraphDatabase

# Connessione al database Neo4j (istanza analisiutentitelegram2.0)
_driver = GraphDatabase.driver(
    "bolt://127.0.0.1:7687",  # URI locale (porta Bolt)
    auth=("neo4j", "analisi2.0")  # user e password definiti in fase di creazione istanza
)

# Messaggio di log
print("[Neo4jConnector] Connessione stabilita con Neo4j su bolt://127.0.0.1:7687")

def run_query(query, params=None):
    """
    Esegue una query Cypher su Neo4j e restituisce i risultati
    come lista di dizionari.
    """
    with _driver.session() as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]  # conversione immediata

def close_driver():
    """Chiude il driver Neo4j"""
    _driver.close()
    print("[Neo4jConnector] Connessione chiusa con Neo4j")
