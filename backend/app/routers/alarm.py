"""告警监测接口：维护告警记录，覆盖确认告警、关闭告警、忽略告警等动作。"""
from __future__ import annotations

import csv
import io
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.alarm import AlarmService

router = APIRouter(prefix="/api/alarm", tags=["告警监测"])

service = AlarmService()

LIST_FIELDS = ["告警编号", "告警来源", "告警类型", "触发阈值", "触发时刻", "处置人员", "关闭时刻", "告警状态"]
EXPORT_FIELDS = LIST_FIELDS + ["忽略理由", "阈值缺失"]
STATUSES = ["待确认", "处置中", "已关闭", "已忽略"]


def _export_value(item: dict[str, Any], field: str) -> str:
    if field == "阈值缺失":
        return "是" if item.get("阈值缺失") else "否"
    value = item.get(field)
    return "" if value is None else str(value)


def _build_csv(items: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(EXPORT_FIELDS)
    for item in items:
        writer.writerow([_export_value(item, field) for field in EXPORT_FIELDS])
    # 带 BOM 的 UTF-8，Excel 直接打开不会乱码
    return "\ufeff" + buffer.getvalue()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按告警编号检索"),
    source: str | None = Query(default=None, description="按告警来源检索"),
    alarm_type: str | None = Query(default=None, description="按告警类型检索"),
    status: str | None = Query(default=None, description="待确认、处置中、已关闭、已忽略"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按告警编号、来源、类型与状态过滤告警监测列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, source=source, alarm_type=alarm_type, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按告警编号检索"),
    source: str | None = Query(default=None, description="按告警来源检索"),
    alarm_type: str | None = Query(default=None, description="按告警类型检索"),
    status: str | None = Query(default=None, description="待确认、处置中、已关闭、已忽略"),
) -> Response:
    """导出告警监测清单：沿用列表当前查询条件生成 CSV 文件，条数与列表页脚一致。"""
    items, _total = service.list_entries(
        keyword=keyword, source=source, alarm_type=alarm_type, status=status, page=1, size=10000
    )
    filename = quote("告警监测清单.csv")
    headers = {"Content-Disposition": f"attachment; filename=alarm-export.csv; filename*=UTF-8''{filename}"}
    return Response(content=_build_csv(items), media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条告警记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"告警记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条告警记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="告警记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条告警记录执行确认告警、关闭告警、忽略告警；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    reason = payload.values.get("忽略理由")
    entry, message = service.run_action(entry_id, action, reason=str(reason) if reason is not None else None)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
