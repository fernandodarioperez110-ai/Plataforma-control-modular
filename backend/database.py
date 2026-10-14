"""
Persistencia de corridas en SQLite. Guarda métricas + telemetría completa.
La página de datos consulta los últimos 50 registros.
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "runs.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creado TEXT,
                prototipo TEXT,
                controlador TEXT,
                params TEXT,
                tiempo_ejecucion REAL,
                error_rms REAL,
                sobreimpulso REAL,
                error_estacionario REAL,
                telemetria TEXT
            )
            """
        )


def save_run(prototipo, controlador, params, metrics, telemetria):
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO runs (creado, prototipo, controlador, params,
                tiempo_ejecucion, error_rms, sobreimpulso, error_estacionario, telemetria)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                prototipo,
                controlador,
                json.dumps(params),
                metrics["tiempo_ejecucion"],
                metrics["error_rms"],
                metrics["sobreimpulso"],
                metrics["error_estacionario"],
                json.dumps(telemetria),
            ),
        )
        return cur.lastrowid


def last_runs(limit=50):
    with _conn() as c:
        rows = c.execute(
            """
            SELECT id, creado, prototipo, controlador, params,
                   tiempo_ejecucion, error_rms, sobreimpulso, error_estacionario
            FROM runs ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d["params"])
            out.append(d)
        return out


def delete_runs(ids):
    if not ids:
        return 0
    with _conn() as c:
        placeholders = ",".join("?" for _ in ids)
        cur = c.execute(f"DELETE FROM runs WHERE id IN ({placeholders})", list(ids))
        deleted = cur.rowcount
        # Si ya no queda ningún registro, reinicia el contador de IDs para
        # que la próxima corrida vuelva a empezar en 1.
        restantes = c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        if restantes == 0:
            c.execute("DELETE FROM sqlite_sequence WHERE name = 'runs'")
        return deleted


def get_run(run_id):
    with _conn() as c:
        r = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["params"] = json.loads(d["params"])
        d["telemetria"] = json.loads(d["telemetria"])
        return d
