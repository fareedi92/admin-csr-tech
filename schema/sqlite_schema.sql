-- FLT CSR App — SQLite schema (reference)
-- Mirrors the live schema in instance/users.db as created by Flask-SQLAlchemy + ensure_schema().

PRAGMA foreign_keys = OFF;

CREATE TABLE users (
    id INTEGER NOT NULL PRIMARY KEY,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    created_at DATETIME,
    display_name VARCHAR(120),
    role VARCHAR(20) DEFAULT 'csr',
    is_active BOOLEAN DEFAULT 1,
    is_available BOOLEAN DEFAULT 1,
    max_concurrent_chats INTEGER DEFAULT 4,
    last_assigned_at DATETIME,
    last_seen_at DATETIME,
    unlimited_chats BOOLEAN DEFAULT 0
);
CREATE INDEX ix_users_role ON users (role);

CREATE TABLE admin_accounts (
    id INTEGER NOT NULL PRIMARY KEY,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    display_name VARCHAR(120),
    last_seen_at DATETIME,
    created_at DATETIME
);
CREATE UNIQUE INDEX ix_admin_accounts_email ON admin_accounts (email);

CREATE TABLE tech_team_accounts (
    id INTEGER NOT NULL PRIMARY KEY,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    display_name VARCHAR(120),
    specialty VARCHAR(100),
    is_active BOOLEAN NOT NULL,
    last_seen_at DATETIME,
    created_at DATETIME
);

CREATE TABLE ticket_statuses (
    id INTEGER NOT NULL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    label VARCHAR(100) NOT NULL,
    color VARCHAR(20),
    sort_order INTEGER,
    is_default BOOLEAN,
    is_resolved BOOLEAN
);

CREATE TABLE chat_conversations (
    id INTEGER NOT NULL PRIMARY KEY,
    external_chat_id VARCHAR(100) NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    customer_email VARCHAR(150),
    customer_external_user_id VARCHAR(120),
    auth_mode VARCHAR(20) NOT NULL,
    authenticated_user_data TEXT,
    subject VARCHAR(255),
    priority VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    source VARCHAR(40) NOT NULL,
    reverted_reason TEXT,
    last_customer_message TEXT,
    assigned_csr_id INTEGER,
    assigned_at DATETIME,
    reverted_at DATETIME NOT NULL,
    last_activity_at DATETIME NOT NULL,
    resolved_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (assigned_csr_id) REFERENCES users (id)
);
CREATE UNIQUE INDEX ix_chat_conversations_external_chat_id ON chat_conversations (external_chat_id);
CREATE INDEX ix_chat_conversations_assigned_csr_id ON chat_conversations (assigned_csr_id);
CREATE INDEX ix_chat_conversations_status ON chat_conversations (status);
CREATE INDEX ix_chat_conversations_customer_external_user_id ON chat_conversations (customer_external_user_id);

CREATE TABLE chat_assignment_events (
    id INTEGER NOT NULL PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    from_csr_id INTEGER,
    to_csr_id INTEGER,
    acted_by_user_id INTEGER,
    notes TEXT,
    created_at DATETIME NOT NULL,
    acted_by_name VARCHAR(120),
    acted_by_role VARCHAR(20),
    FOREIGN KEY (chat_id) REFERENCES chat_conversations (id),
    FOREIGN KEY (from_csr_id) REFERENCES users (id),
    FOREIGN KEY (to_csr_id) REFERENCES users (id),
    FOREIGN KEY (acted_by_user_id) REFERENCES users (id)
);
CREATE INDEX ix_chat_assignment_events_chat_id ON chat_assignment_events (chat_id);
CREATE INDEX ix_chat_assignment_events_event_type ON chat_assignment_events (event_type);

CREATE TABLE chat_messages (
    id INTEGER NOT NULL PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    sender_type VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    image_attachments TEXT,
    FOREIGN KEY (chat_id) REFERENCES chat_conversations (id)
);
CREATE INDEX ix_chat_messages_sender_type ON chat_messages (sender_type);
CREATE INDEX ix_chat_messages_chat_id ON chat_messages (chat_id);

CREATE TABLE tickets (
    id INTEGER NOT NULL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    priority VARCHAR(20) NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_by_csr_id INTEGER NOT NULL,
    assigned_tech_id INTEGER,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    resolved_at DATETIME,
    ticket_number VARCHAR(24),
    chat_id INTEGER,
    FOREIGN KEY (created_by_csr_id) REFERENCES users (id),
    FOREIGN KEY (assigned_tech_id) REFERENCES tech_team_accounts (id)
);
CREATE INDEX ix_tickets_assigned_tech_id ON tickets (assigned_tech_id);
CREATE INDEX ix_tickets_status ON tickets (status);
CREATE UNIQUE INDEX ix_tickets_ticket_number ON tickets (ticket_number);
CREATE INDEX ix_tickets_chat_id ON tickets (chat_id);

CREATE TABLE ticket_status_logs (
    id INTEGER NOT NULL PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    old_status VARCHAR(50),
    new_status VARCHAR(50) NOT NULL,
    changed_by_user_id INTEGER,
    changed_by_role VARCHAR(20),
    notes TEXT,
    created_at DATETIME NOT NULL,
    old_assigned_tech_id INTEGER,
    new_assigned_tech_id INTEGER,
    FOREIGN KEY (ticket_id) REFERENCES tickets (id)
);
CREATE INDEX ix_ticket_status_logs_ticket_id ON ticket_status_logs (ticket_id);

CREATE TABLE ticket_messages (
    id INTEGER NOT NULL PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    sender_type VARCHAR(20) NOT NULL,
    sender_id INTEGER NOT NULL,
    sender_name VARCHAR(120),
    content TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets (id)
);
CREATE INDEX ix_ticket_messages_sender_type ON ticket_messages (sender_type);
CREATE INDEX ix_ticket_messages_ticket_id ON ticket_messages (ticket_id);
