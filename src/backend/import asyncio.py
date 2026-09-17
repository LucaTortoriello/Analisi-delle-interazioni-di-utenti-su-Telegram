import asyncio
from telethon.sync import TelegramClient
from telethon import utils
from telethon.tl.types import User, Channel, Chat

# ==========================================
# CONFIGURAZIONE
# ==========================================
API_ID = 28785308          # Sostituisci con i tuoi
API_HASH = '5151c7140baef79f71fefc89d739021a' # Sostituisci con i tuoi
SESSION_NAME = 'sessione_telethon' 

# INSERISCI QUI GLI ID DA CONTROLLARE (separati da virgola)
# Puoi mettere sia ID positivi (12345) che negativi (-10012345)
IDS_DA_VALUTARE = [
    619316967       # Telegram Service Notification (esempio)
    # Aggiungi qui altri ID che ti sembrano sospetti nel tuo DB
]

# ==========================================
# LOGICA DI CONTROLLO
# ==========================================
async def analizza_id(client, user_id):
    print(f"\n------------------------------------------------")
    print(f"🔍 Analisi ID Input: {user_id}")
    
    try:
        # Chiede a Telegram l'entità
        entity = await client.get_entity(user_id)
        
        # Determina il tipo
        tipo = "Sconosciuto"
        icona = "❓"
        nome_display = "Nessuno"
        
        if isinstance(entity, User):
            if entity.bot:
                tipo = "BOT 🤖"
                icona = "🤖"
            else:
                tipo = "UTENTE REALE 👤"
                icona = "👤"
            nome_display = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
            
        elif isinstance(entity, Channel):
            if entity.megagroup: # I supergruppi sono tecnicamente canali in MTProto
                tipo = "SUPERGRUPPO 👥"
                icona = "👥"
            else:
                tipo = "CANALE BROADCAST 📢"
                icona = "📢"
            nome_display = entity.title
            
        elif isinstance(entity, Chat):
            tipo = "GRUPPO BASE 👥"
            icona = "👥"
            nome_display = entity.title

        # Output Dati
        print(f"{icona} Risultato: TROVATO")
        print(f"   🏷️  Nome/Titolo: {nome_display}")
        print(f"   🔗 Username: @{getattr(entity, 'username', 'Nessuno')}")
        print(f"   📊 Tipo Entità: {tipo}")
        print(f"   🆔 ID Pulito (DB): {entity.id}")
        print(f"   🔢 ID Marked (Telethon): {utils.get_peer_id(entity)}")
        
        # Check specifico per il tuo problema
        if isinstance(entity, (Channel, Chat)) or (isinstance(entity, User) and entity.bot):
            print(f"   ⚠️  NOTA: Questo ID non è una persona fisica.")

    except ValueError:
        print(f"❌ ERRORE: ID non trovato o inesistente.")
        print("   Potrebbe essere un gruppo privato di cui non fai parte.")
    except Exception as e:
        print(f"❌ ERRORE GENERICO: {e}")

async def main():
    print("🚀 Avvio scansione lista utenti...")
    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        for uid in IDS_DA_VALUTARE:
            await analizza_id(client, uid)
            # Piccola pausa per non floodare le API se la lista è lunga
            await asyncio.sleep(0.5) 
    print("\n✅ Scansione completata.")

if __name__ == '__main__':
    asyncio.run(main())