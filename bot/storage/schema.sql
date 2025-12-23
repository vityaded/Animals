CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    current_level INTEGER NOT NULL DEFAULT 1,
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
    user_id INTEGER NOT NULL,
    content_id TEXT,
    expected_text TEXT,
    transcript TEXT,
    similarity INTEGER,
    is_first_try INTEGER NOT NULL DEFAULT 0,
    is_correct INTEGER DEFAULT 0,
    question TEXT,
    user_answer TEXT,
    correct_answer TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
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
    first_try_total INTEGER NOT NULL DEFAULT 0,
    first_try_errors INTEGER NOT NULL DEFAULT 0,
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
    deck_json TEXT,
    item_index INTEGER NOT NULL DEFAULT 0,
    total_items INTEGER NOT NULL,
    current_attempts INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    reward_stage INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT 'normal',
    wrong_total INTEGER NOT NULL DEFAULT 0,
    care_stage INTEGER NOT NULL DEFAULT 0,
    awaiting_care INTEGER NOT NULL DEFAULT 0,
    care_json TEXT,
    blocked INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS pets (
    user_id INTEGER PRIMARY KEY,
    pet_type TEXT NOT NULL DEFAULT 'panda',
    hunger_level INTEGER NOT NULL DEFAULT 1,
    thirst_level INTEGER NOT NULL DEFAULT 1,
    hygiene_level INTEGER NOT NULL DEFAULT 1,
    energy_level INTEGER NOT NULL DEFAULT 1,
    mood_level INTEGER NOT NULL DEFAULT 1,
    health_level INTEGER NOT NULL DEFAULT 1,
    sessions_today INTEGER NOT NULL DEFAULT 0,
    last_day TEXT,
    consecutive_zero_days INTEGER NOT NULL DEFAULT 0,
    is_dead INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS item_progress (
    user_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    content_id TEXT NOT NULL,
    learn_correct_count INTEGER NOT NULL DEFAULT 0,
    review_stage INTEGER NOT NULL DEFAULT 0,
    next_due_at TIMESTAMP,
    last_seen_at TIMESTAMP,
    PRIMARY KEY (user_id, level, content_id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);
