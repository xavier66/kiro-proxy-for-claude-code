"""Flow Database - SQLite 数据库存储

将流量记录持久化到 SQLite 数据库中，支持重启后数据恢复。
字段严格对应 LLMFlow / FlowTiming / FlowRequest / FlowResponse / FlowError 的实际属性。
"""
import sqlite3
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .flow_monitor import LLMFlow, FlowState


def _safe_serialize(obj: Any) -> Any:
    """安全序列化对象，处理 dataclass、dict、list 等类型"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item) for item in obj]
    if hasattr(obj, '__dataclass_fields__'):
        try:
            return asdict(obj)
        except Exception:
            return str(obj)
    return str(obj)


class FlowDatabase:
    """Flow SQLite 数据库"""

    def __init__(self, db_path: str = "flows.db"):
        self.db_path = Path(db_path)
        self.init_database()

    def init_database(self):
        """初始化数据库表，自动迁移旧表结构"""
        with sqlite3.connect(self.db_path) as conn:
            # 如果旧表存在但结构不对，删掉重建
            if self._table_exists(conn):
                columns = self._get_columns(conn)
                expected = {"id", "protocol", "state", "account_id", "created_at", "first_byte_at", "completed_at", "request_data", "response_data", "error_data"}
                if not expected.issubset(set(columns)):
                    print(f"[FlowDB] 检测到旧表结构，重建数据库...")
                    conn.execute("DROP TABLE flows")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS flows (
                    id TEXT PRIMARY KEY,
                    protocol TEXT,
                    state TEXT,
                    account_id TEXT,
                    created_at REAL,
                    first_byte_at REAL,
                    completed_at REAL,
                    request_data TEXT,
                    response_data TEXT,
                    error_data TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_flows_protocol ON flows(protocol)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_flows_state ON flows(state)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_flows_created_at ON flows(created_at)")

    def _table_exists(self, conn) -> bool:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='flows'")
        return cursor.fetchone() is not None

    def _get_columns(self, conn) -> list:
        cursor = conn.execute("PRAGMA table_info(flows)")
        return [row[1] for row in cursor.fetchall()]

    def save_flow(self, flow: 'LLMFlow'):
        """保存 Flow 到数据库"""
        try:
            request_data = json.dumps(_safe_serialize(flow.request)) if flow.request else None
            response_data = json.dumps(_safe_serialize(flow.response)) if flow.response else None
            error_data = json.dumps(_safe_serialize(flow.error)) if flow.error else None

            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO flows
                    (id, protocol, state, account_id, created_at, first_byte_at, completed_at,
                     request_data, response_data, error_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    flow.id,
                    flow.protocol,
                    flow.state.value,
                    flow.account_id,
                    flow.timing.created_at,
                    flow.timing.first_byte_at,
                    flow.timing.completed_at,
                    request_data,
                    response_data,
                    error_data,
                ))
        except Exception as e:
            print(f"[FlowDB] 保存 Flow 失败: {e}")

    def load_flow(self, flow_id: str) -> Optional['LLMFlow']:
        """从数据库加载 Flow"""
        from .flow_monitor import LLMFlow, FlowState, FlowTiming, FlowRequest, FlowResponse, FlowError

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM flows WHERE id = ?", (flow_id,))
                row = cursor.fetchone()
                if not row:
                    return None

                timing = FlowTiming(
                    created_at=row["created_at"] or 0,
                    first_byte_at=row["first_byte_at"],
                    completed_at=row["completed_at"],
                )

                flow = LLMFlow(
                    id=row["id"],
                    protocol=row["protocol"] or "",
                    state=FlowState(row["state"]),
                    account_id=row["account_id"],
                    timing=timing,
                )

                if row["request_data"]:
                    req_data = json.loads(row["request_data"])
                    flow.request = FlowRequest(
                        method=req_data.get("method", ""),
                        path=req_data.get("path", ""),
                        headers=req_data.get("headers", {}),
                        body=req_data.get("body", {}),
                        model=req_data.get("model", ""),
                        messages=req_data.get("messages", []),
                        system=req_data.get("system", ""),
                        tools=req_data.get("tools", []),
                        stream=req_data.get("stream", False),
                        max_tokens=req_data.get("max_tokens", 0),
                        temperature=req_data.get("temperature", 1.0),
                    )

                if row["response_data"]:
                    resp_data = json.loads(row["response_data"])
                    usage_data = resp_data.get("usage", {})
                    from .flow_monitor import TokenUsage
                    flow.response = FlowResponse(
                        status_code=resp_data.get("status_code", 0),
                        headers=resp_data.get("headers", {}),
                        body=resp_data.get("body"),
                        content=resp_data.get("content", ""),
                        tool_calls=resp_data.get("tool_calls", []),
                        stop_reason=resp_data.get("stop_reason", ""),
                        usage=TokenUsage(**usage_data) if isinstance(usage_data, dict) else TokenUsage(),
                        chunks=resp_data.get("chunks", []),
                    )

                if row["error_data"]:
                    err_data = json.loads(row["error_data"])
                    flow.error = FlowError(
                        type=err_data.get("type", ""),
                        message=err_data.get("message", ""),
                        status_code=err_data.get("status_code", 0),
                        raw=err_data.get("raw", ""),
                    )

                return flow
        except Exception as e:
            print(f"[FlowDB] 加载 Flow 失败: {e}")
            return None

    def query_flows(
        self,
        protocol: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at DESC"
    ) -> List[str]:
        """查询 Flow ID 列表"""
        try:
            conditions = []
            params = []
            if protocol:
                conditions.append("protocol = ?")
                params.append(protocol)
            if state:
                conditions.append("state = ?")
                params.append(state)
            where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            query = f"SELECT id FROM flows {where_clause} ORDER BY {order_by} LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(query, params)
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"[FlowDB] 查询 Flow 失败: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT
                        COUNT(*) as total_flows,
                        COUNT(CASE WHEN state = 'completed' THEN 1 END) as completed_flows,
                        COUNT(CASE WHEN state = 'error' THEN 1 END) as error_flows,
                        AVG(completed_at - created_at) as avg_duration,
                        MIN(created_at) as first_flow_time,
                        MAX(created_at) as last_flow_time
                    FROM flows
                """)
                row = cursor.fetchone()
                return {
                    "total_flows": row[0] or 0,
                    "completed_flows": row[1] or 0,
                    "error_flows": row[2] or 0,
                    "avg_duration": row[3] or 0,
                    "first_flow_time": row[4],
                    "last_flow_time": row[5]
                }
        except Exception as e:
            print(f"[FlowDB] 获取统计信息失败: {e}")
            return {}
