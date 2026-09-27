"""告警监测业务规则：状态流转、字段校验、筛选口径与导出数据都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "alarm"
REQUIRED_FIELDS = ["告警编号", "告警来源", "告警类型"]
DISPLAY_FIELDS = ["告警编号", "告警来源", "告警类型", "触发阈值", "触发时刻", "处置人员", "关闭时刻"]
OPEN_STATUSES = ["待确认", "处置中"]
CLOSED_STATUSES = ["已关闭", "已忽略"]
STATUS_ORDER = OPEN_STATUSES + CLOSED_STATUSES
ACTION_RULES = {"确认告警": "处置中", "关闭告警": "已关闭", "忽略告警": "已忽略"}
# 每个状态允许继续执行的动作；已关闭、已忽略属于终态，不再放行任何动作，
# 重复点击同一个动作只会得到幂等提示，不会把状态改回去。
ALLOWED_ACTIONS: dict[str, list[str]] = {
    "待确认": ["确认告警", "关闭告警", "忽略告警"],
    "处置中": ["关闭告警", "忽略告警"],
    "已关闭": [],
    "已忽略": [],
}


def is_threshold_missing(row: dict[str, Any]) -> bool:
    """触发阈值留空的告警需要在列表与导出里单独标识出来。"""
    return not str(row.get("触发阈值") or "").strip()


def present(row: dict[str, Any]) -> dict[str, Any]:
    """把存储字段整理成列表/导出统一口径：状态、忽略理由、阈值配置都在这一层补齐。"""
    item: dict[str, Any] = {"id": row.get("id")}
    for field in DISPLAY_FIELDS:
        item[field] = row.get(field) or ""
    status = row.get("status") or STATUS_ORDER[0]
    item["status"] = status
    item["告警状态"] = status
    item["忽略理由"] = row.get("忽略理由") or ""
    item["阈值配置"] = "未配置" if is_threshold_missing(row) else "已配置"
    item["pending"] = bool(row.get("pending"))
    item["abnormal"] = bool(row.get("abnormal"))
    return item


class AlarmService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("告警编号", ""))]
        if status:
            rows = [row for row in rows if (row.get("status") or STATUS_ORDER[0]) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return present(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 触发阈值允许登记时留空，但留空的记录会在列表与导出里被标识为“未配置”。
        entry["触发阈值"] = str(values.get("触发阈值") or "").strip()
        for field in DISPLAY_FIELDS:
            entry.setdefault(field, "")
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = True
        entry["忽略理由"] = ""
        rows.append(entry)
        return present(entry), []

    def run_action(
        self, entry_id: int, action: str, remark: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"告警记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于告警监测可执行范围"
        target = ACTION_RULES[action]
        current = entry.get("status") or STATUS_ORDER[0]
        if action not in ALLOWED_ACTIONS.get(current, []):
            # 终态记录重复点同一动作时按幂等处理：明确提示、保持现状，绝不回改状态。
            if target == current:
                return present(entry), f"告警记录当前已是「{current}」，无需重复{action}"
            return None, f"告警记录当前为「{current}」，不能执行{action}"
        if action == "忽略告警" and not str(remark or "").strip():
            return None, "忽略告警必须填写忽略理由"
        entry["status"] = target
        # 待确认、处置中属于未收尾的活动告警；已关闭、已忽略后不再计入待处理与异常量，
        # 这样概览看板的异常量会随收尾动作同步下降。
        entry["pending"] = target in OPEN_STATUSES
        entry["abnormal"] = target in OPEN_STATUSES
        if action == "忽略告警":
            entry["忽略理由"] = str(remark or "").strip()
        if action == "关闭告警" and not str(entry.get("关闭时刻") or "").strip():
            entry["关闭时刻"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        return present(entry), f"告警记录已{action}"
