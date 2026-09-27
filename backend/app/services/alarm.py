"""告警监测业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "alarm"
REQUIRED_FIELDS = ["告警编号", "告警来源", "告警类型"]
STATUS_ORDER = ["待确认", "处置中", "已关闭", "已忽略"]
STATUS_FIELD = "告警状态"
ACTION_RULES = {"确认告警": "处置中", "关闭告警": "已关闭", "忽略告警": "已忽略"}
TERMINAL_STATUSES = {"已关闭", "已忽略"}
# 每个状态允许流向的下一状态；已关闭、已忽略是收尾状态，不再回跳
ALLOWED_TRANSITIONS = {
    "待确认": {"处置中", "已关闭", "已忽略"},
    "处置中": {"已关闭", "已忽略"},
    "已关闭": set(),
    "已忽略": set(),
}


def _annotate(row: dict[str, Any]) -> dict[str, Any]:
    """给列表与导出行补上派生标识，不改动仓库里的原始记录。"""
    item = dict(row)
    item["阈值缺失"] = not str(row.get("触发阈值") or "").strip()
    return item


class AlarmService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        source: str | None = None,
        alarm_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("告警编号", ""))]
        if source:
            rows = [row for row in rows if source in str(row.get("告警来源", ""))]
        if alarm_type:
            rows = [row for row in rows if alarm_type in str(row.get("告警类型", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_annotate(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        reason: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"告警记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于告警监测可执行范围"
        target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current == target:
            return entry, f"告警记录已处于「{target}」，重复{action}不会改变状态"
        if target not in ALLOWED_TRANSITIONS.get(current, set()):
            return None, f"告警记录已处于「{current}」，收尾状态不再回跳，不能再{action}"
        if action == "忽略告警":
            reason = (reason or "").strip()
            if not reason:
                return None, "忽略告警必须填写忽略理由，否则导出清单无法追溯"
            entry["忽略理由"] = reason
        if action == "关闭告警":
            entry["关闭时刻"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry["status"] = target
        entry[STATUS_FIELD] = target
        entry["pending"] = target not in TERMINAL_STATUSES
        entry["abnormal"] = target == "处置中"
        return entry, f"告警记录已{action}"
