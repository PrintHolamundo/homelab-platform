import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class Database:
    def __init__(self, db_path: str = "/data/dochat.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS document_financials (
                    document_id INTEGER PRIMARY KEY,
                    title TEXT,
                    correspondent TEXT,
                    document_date TEXT,
                    year INTEGER,
                    month INTEGER,
                    period TEXT,
                    saldo_inicial REAL DEFAULT 0,
                    depositos_pagos REAL DEFAULT 0,
                    compras_cargos REAL DEFAULT 0,
                    saldo_final REAL DEFAULT 0,
                    pago_minimo REAL DEFAULT 0,
                    pago_sin_intereses REAL DEFAULT 0,
                    resumen TEXT,
                    gastos_principales TEXT,
                    extracted_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def is_indexed(self, document_id: int) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM document_financials WHERE document_id = ?",
                (document_id,)
            ).fetchone()
            return row is not None

    def save_financial(self, data: Dict[str, Any]):
        gastos_json = json.dumps(data.get("gastos_principales", []), ensure_ascii=False)
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO document_financials (
                    document_id, title, correspondent, document_date,
                    year, month, period, saldo_inicial, depositos_pagos,
                    compras_cargos, saldo_final, pago_minimo, pago_sin_intereses,
                    resumen, gastos_principales, extracted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                data["document_id"],
                data.get("title", ""),
                data.get("correspondent", ""),
                data.get("document_date", ""),
                data.get("year", 0),
                data.get("month", 0),
                data.get("period", ""),
                float(data.get("saldo_inicial", 0.0) or 0.0),
                float(data.get("depositos_pagos", 0.0) or 0.0),
                float(data.get("compras_cargos", 0.0) or 0.0),
                float(data.get("saldo_final", 0.0) or 0.0),
                float(data.get("pago_minimo", 0.0) or 0.0),
                float(data.get("pago_sin_intereses", 0.0) or 0.0),
                data.get("resumen", ""),
                gastos_json,
            ))
            conn.commit()

    def get_financial(self, document_id: int) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM document_financials WHERE document_id = ?",
                (document_id,)
            ).fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res["gastos_principales"] = json.loads(res["gastos_principales"] or "[]")
            except Exception:
                res["gastos_principales"] = []
            return res

    def list_financials(self, year: Optional[int] = None, correspondent: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM document_financials WHERE 1=1"
        params = []
        if year:
            query += " AND year = ?"
            params.append(year)
        if correspondent:
            query += " AND correspondent LIKE ?"
            params.append(f"%{correspondent}%")
        query += " ORDER BY year ASC, month ASC, document_date ASC"

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["gastos_principales"] = json.loads(item["gastos_principales"] or "[]")
                except Exception:
                    item["gastos_principales"] = []
                results.append(item)
            return results

    def get_annual_aggregation(self, year: int, correspondent: Optional[str] = None) -> Dict[str, Any]:
        query = """
            SELECT 
                COUNT(*) as total_estados,
                COALESCE(SUM(depositos_pagos), 0) as total_depositos_pagos,
                COALESCE(SUM(compras_cargos), 0) as total_compras_cargos,
                COALESCE(AVG(compras_cargos), 0) as promedio_mensual_gasto,
                COALESCE(MAX(compras_cargos), 0) as max_gasto_mes
            FROM document_financials
            WHERE year = ?
        """
        params = [year]
        if correspondent:
            query += " AND correspondent LIKE ?"
            params.append(f"%{correspondent}%")

        with self._get_conn() as conn:
            row = conn.execute(query, params).fetchone()
            stats = dict(row) if row else {}

        # Monthly breakdown
        monthly = self.list_financials(year=year, correspondent=correspondent)
        stats["meses"] = monthly
        return stats

    def get_stats(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM document_financials").fetchone()[0]
            banks = conn.execute(
                "SELECT DISTINCT correspondent FROM document_financials WHERE correspondent != ''"
            ).fetchall()
            years = conn.execute(
                "SELECT DISTINCT year FROM document_financials WHERE year > 0 ORDER BY year ASC"
            ).fetchall()
            return {
                "total_indexed": total,
                "correspondents": [b[0] for b in banks],
                "years": [y[0] for y in years],
            }

    def save_message(self, role: str, content: str):
        with self._get_conn() as conn:
            conn.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content))
            conn.commit()

    def get_recent_history(self, limit: int = 10) -> List[Dict[str, str]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
            return history
