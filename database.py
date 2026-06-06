import sqlite3

DB = "ligalabs.db"

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS config(
            guild_id TEXT, key TEXT, value TEXT,
            PRIMARY KEY(guild_id, key)
        );
        CREATE TABLE IF NOT EXISTS teams(
            guild_id TEXT, role_id TEXT,
            points INTEGER DEFAULT 0,
            tier TEXT DEFAULT 'E',
            PRIMARY KEY(guild_id, role_id)
        );
        CREATE TABLE IF NOT EXISTS pending_scrims(
            message_id TEXT PRIMARY KEY,
            guild_id TEXT, requester_id TEXT,
            requester_role_id TEXT, jour TEXT, heure TEXT
        );
        CREATE TABLE IF NOT EXISTS scrim_channels(
            channel_id TEXT PRIMARY KEY,
            guild_id TEXT, team1_id TEXT, team2_id TEXT,
            result_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS point_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT, role_id TEXT,
            delta INTEGER, reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

# ── Config ────────────────────────────────────────────────
def cfg(guild_id, key, default=None):
    with db() as c:
        r = c.execute("SELECT value FROM config WHERE guild_id=? AND key=?",
                      (str(guild_id), key)).fetchone()
    return r["value"] if r else default

def set_cfg(guild_id, key, value):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO config VALUES(?,?,?)",
                  (str(guild_id), key, str(value)))

# ── Teams & points ────────────────────────────────────────
def add_points(guild_id, role_id, delta, reason):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO teams(guild_id,role_id) VALUES(?,?)",
                  (str(guild_id), str(role_id)))
        c.execute("UPDATE teams SET points=points+? WHERE guild_id=? AND role_id=?",
                  (delta, str(guild_id), str(role_id)))
        c.execute("INSERT INTO point_history(guild_id,role_id,delta,reason) VALUES(?,?,?,?)",
                  (str(guild_id), str(role_id), delta, reason))

def get_team(guild_id, role_id):
    with db() as c:
        r = c.execute("SELECT * FROM teams WHERE guild_id=? AND role_id=?",
                      (str(guild_id), str(role_id))).fetchone()
    return dict(r) if r else None

def set_tier(guild_id, role_id, tier):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO teams(guild_id,role_id) VALUES(?,?)",
                  (str(guild_id), str(role_id)))
        c.execute("UPDATE teams SET tier=? WHERE guild_id=? AND role_id=?",
                  (tier, str(guild_id), str(role_id)))

def get_leaderboard(guild_id):
    with db() as c:
        rows = c.execute(
            "SELECT * FROM teams WHERE guild_id=? ORDER BY points DESC",
            (str(guild_id),)).fetchall()
    return [dict(r) for r in rows]

# ── Pending scrims ────────────────────────────────────────
def store_scrim(message_id, guild_id, requester_id, requester_role_id, jour, heure):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO pending_scrims VALUES(?,?,?,?,?,?)",
                  (str(message_id), str(guild_id), str(requester_id),
                   str(requester_role_id), jour, heure))

def get_scrim(message_id):
    with db() as c:
        r = c.execute("SELECT * FROM pending_scrims WHERE message_id=?",
                      (str(message_id),)).fetchone()
    return dict(r) if r else None

# ── Scrim channels (private salons) ──────────────────────
def create_scrim_ch(channel_id, guild_id, team1_id, team2_id):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO scrim_channels VALUES(?,?,?,?,0)",
                  (str(channel_id), str(guild_id), str(team1_id), str(team2_id)))

def get_scrim_ch(channel_id):
    with db() as c:
        r = c.execute("SELECT * FROM scrim_channels WHERE channel_id=?",
                      (str(channel_id),)).fetchone()
    return dict(r) if r else None

def inc_result(channel_id):
    with db() as c:
        c.execute("UPDATE scrim_channels SET result_count=result_count+1 WHERE channel_id=?",
                  (str(channel_id),))

def reset_result(channel_id):
    with db() as c:
        c.execute("UPDATE scrim_channels SET result_count=0 WHERE channel_id=?",
                  (str(channel_id),))

init()

# ── LigaLabs Poule (saison) ───────────────────────────────

def _init_poule():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS ligalabs_poule(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT,
            team1_id TEXT, roster1 TEXT,
            team2_id TEXT, roster2 TEXT,
            winner_team_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
_init_poule()

def add_poule_match(guild_id, team1_id, roster1, team2_id, roster2, winner_team_id):
    with db() as c:
        c.execute(
            "INSERT INTO ligalabs_poule(guild_id,team1_id,roster1,team2_id,roster2,winner_team_id)"
            " VALUES(?,?,?,?,?,?)",
            (str(guild_id),str(team1_id),roster1,str(team2_id),roster2,str(winner_team_id)))

def count_poule(guild_id, team1_id, roster1, team2_id, roster2):
    with db() as c:
        r = c.execute(
            "SELECT COUNT(*) as cnt FROM ligalabs_poule WHERE guild_id=?"
            " AND ((team1_id=? AND roster1=? AND team2_id=? AND roster2=?)"
            "   OR (team1_id=? AND roster1=? AND team2_id=? AND roster2=?))",
            (str(guild_id),
             str(team1_id),roster1,str(team2_id),roster2,
             str(team2_id),roster2,str(team1_id),roster1)).fetchone()
    return r["cnt"] if r else 0

def get_poule_matches(guild_id):
    with db() as c:
        rows = c.execute(
            "SELECT * FROM ligalabs_poule WHERE guild_id=? ORDER BY created_at",
            (str(guild_id),)).fetchall()
    return [dict(r) for r in rows]

def reset_poule_season(guild_id):
    with db() as c:
        c.execute("DELETE FROM ligalabs_poule WHERE guild_id=?", (str(guild_id),))
