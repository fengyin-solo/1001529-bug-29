"""告警监测接口：维护告警记录，覆盖确认告警、关闭告警、忽略告警等动作。"""
from __future__ import annotations

import csv
import io
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.alarm import ACTION_RULES, STATUS_ORDER, AlarmService

router = APIRouter(prefix="/api/alarm", tags=["告警监测"])

service = AlarmService()

LIST_FIELDS = ["告警编号", "告警来源", "告警类型", "触发阈值", "触发时刻", "处置人员", "关闭时刻", "告警状态"]
STATUSES = STATUS_ORDER
EXPORT_HEADERS = LIST_FIELDS + ["阈值配置", "忽略理由"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按告警编号检索"),
    status: str | None = Query(default=None, description="待确认、处置中、已关闭、已忽略"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按告警编号与状态过滤告警监测列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"告警状态「{status}」不在允许范围内")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：/export 必须声明在 /{entry_id} 之前，否则 export 会被当成记录编号去解析。
@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按告警编号检索"),
    status: str | None = Query(default=None, description="待确认、处置中、已关闭、已忽略"),
) -> StreamingResponse:
    """按当前查询条件导出全量告警清单（CSV，Excel 可直接打开），条数与列表页脚一致。"""
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"告警状态「{status}」不在允许范围内")
    items, _total = service.list_entries(keyword=keyword, status=status, page=1, size=10000)

    buffer = io.StringIO()
    # 加 UTF-8 BOM，避免 Excel 打开中文表头出现乱码。
    buffer.write("﻿")
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_HEADERS)
    for item in items:
        writer.writerow([item.get(column, "") for column in EXPORT_HEADERS])
    data = buffer.getvalue().encode("utf-8")
    filename = quote("告警监测清单.csv")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


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
    if action not in ACTION_RULES:
        return ActionResult(ok=False, message=f"动作「{action}」不属于告警监测可执行范围")
    entry, message = service.run_action(entry_id, action, remark=payload.remark)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
