CREATE DATABASE IF NOT EXISTS analisiutentitelegram
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE analisiutentitelegram;

CREATE TABLE IF NOT EXISTS chat (
  id_chat BIGINT NOT NULL,
  nome_chat VARCHAR(255) NULL,
  username VARCHAR(255) NULL,
  nome_chat_tradotto VARCHAR(255) NULL,
  tipo VARCHAR(64) NULL,
  ultima_scansione DATETIME NULL,
  data_importazione DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  categoria_chat VARCHAR(100) NOT NULL DEFAULT 'Altro',
  PRIMARY KEY (id_chat)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS utenti (
  id BIGINT NOT NULL,
  nome VARCHAR(512) NULL,
  username VARCHAR(255) NULL,
  foto_path TEXT NULL,
  data_importazione DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS messaggi (
  id_chat BIGINT NOT NULL,
  id_messaggio BIGINT NOT NULL,
  id_autore BIGINT NULL,
  testo LONGTEXT NULL,
  data_invio DATETIME NULL,
  file_path TEXT NULL,
  media_type VARCHAR(255) NULL,
  reply_to_msg_id BIGINT NULL,
  reply_to_user_id BIGINT NULL,
  tipo_evento VARCHAR(255) NULL,
  PRIMARY KEY (id_chat, id_messaggio),
  KEY idx_messaggi_autore (id_autore),
  KEY idx_messaggi_reply (id_chat, reply_to_msg_id),
  KEY idx_messaggi_data (data_invio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS storico_username (
  user_id BIGINT NOT NULL,
  username VARCHAR(255) NOT NULL,
  first_name VARCHAR(255) NULL,
  last_name VARCHAR(255) NULL,
  rilevato_il DATETIME NOT NULL,
  fonte VARCHAR(100) NOT NULL,
  PRIMARY KEY (user_id, username),
  KEY idx_storico_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;