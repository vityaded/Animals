CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    due_at TIMESTAMP,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    user_answer TEXT,
    correct_answer TEXT,
    is_correct INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions (id)
);

CREATE TABLE IF NOT EXISTS level_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    progress INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, level),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    attempts INTEGER DEFAULT 0,
    correct INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    UNIQUE (user_id, date),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    hearts INTEGER DEFAULT 3,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS revive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS session_state (
    session_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    item_index INTEGER NOT NULL DEFAULT 0,
    total_items INTEGER NOT NULL,
    correct_count INTEGER NOT NULL DEFAULT 0,
    reward_stage INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT 'normal',
    blocked INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS pets (
    user_id INTEGER PRIMARY KEY,
    pet_type TEXT NOT NULL DEFAULT 'panda',
    happiness INTEGER NOT NULL DEFAULT 80,
    hunger INTEGER NOT NULL DEFAULT 80,
    thirst INTEGER NOT NULL DEFAULT 80,
    hygiene INTEGER NOT NULL DEFAULT 80,
    energy INTEGER NOT NULL DEFAULT 80,
    mood INTEGER NOT NULL DEFAULT 80,
    health INTEGER NOT NULL DEFAULT 80,
    action_tokens INTEGER NOT NULL DEFAULT 0,
    missed_sessions_streak INTEGER NOT NULL DEFAULT 0,
    resurrect_streak INTEGER NOT NULL DEFAULT 0,
    is_dead INTEGER NOT NULL DEFAULT 0,
    last_checked_at TIMESTAMP,
    last_session_completed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    notifications_enabled INTEGER NOT NULL DEFAULT 1,
    timezone TEXT DEFAULT 'Europe/Helsinki',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);
