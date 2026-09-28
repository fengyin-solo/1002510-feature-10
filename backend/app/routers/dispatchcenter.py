"""调度中心接口：维护调度台，覆盖登记降级、确认故障、切换备用、处理故障等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.dispatchcenter import DispatchcenterService

router = APIRouter(prefix="/api/dispatchcenter", tags=["调度中心"])

service = DispatchcenterService()

LIST_FIELDS = [
    "调度台编号",
    "管辖范围",
    "显示设备",
    "操作终端",
    "通信链路",
    "优先级",
    "通道状态",
    "备用方式",
    "调度台状态",
    "lastOperator",
    "lastSwitchedAt",
]
STATUSES = ["正常", "通道降级", "设备故障", "备用运行"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按调度台编号或管辖范围检索"),
    status: str | None = Query(default=None, description="正常、通道降级、设备故障、备用运行"),
    scope: str | None = Query(default=None, description="按管辖范围检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按编号、管辖范围与通道状态过滤调度中心列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, scope=scope, page=page, size=size)
    # 清单页与明细页共用同一份可执行动作口径，避免两页结论不一致。
    for row in items:
        row["allowedActions"] = service.allowed_actions(row)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出调度中心清单：返回当前全量数据（含最后切换人与切换时间）。

    必须排在 /{entry_id} 之前注册，否则 export 会被当成 entry_id 匹配后报参数校验错误。
    """
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "dispatchcenter", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条调度台明细（含切换记录与当前可执行动作）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"调度台 {entry_id} 不存在或已归档")
    detail = dict(entry)
    detail["allowedActions"] = service.allowed_actions(entry)
    return detail


@router.get("/{entry_id}/history", response_model=dict)
def get_history(entry_id: int) -> dict[str, Any]:
    """读取单条调度台的通道切换记录，交接后可回看每次是谁切的。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"调度台 {entry_id} 不存在或已归档")
    return {"entryId": entry_id, "items": service.list_history(entry_id)}


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条调度台，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="调度台已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条调度台执行通道流转动作；越级、缺前置条件或违反优先级都会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    operator = str(payload.values.get("operator") or "").strip() or None
    entry, message = service.run_action(entry_id, action, operator=operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    detail = dict(entry)
    detail["allowedActions"] = service.allowed_actions(entry)
    return ActionResult(ok=True, message=message, entry=detail)
