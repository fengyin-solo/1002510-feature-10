"""调度中心接口：维护调度台，覆盖登记降级、登记故障、切换备用、处理故障等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.dispatchcenter import DispatchcenterService

router = APIRouter(prefix="/api/dispatchcenter", tags=["调度中心"])

service = DispatchcenterService()

LIST_FIELDS = ["调度台编号", "管辖范围", "优先级", "显示设备", "操作终端", "通信链路", "通道状态", "备用方式", "调度台状态"]
STATUSES = ["正常", "通道降级", "设备故障", "备用运行"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按调度台编号检索"),
    status: str | None = Query(default=None, description="正常、通道降级、设备故障、备用运行"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按调度台编号与状态过滤调度中心列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条调度台明细，含完整切换记录；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"调度台 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条调度台，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="调度台已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条调度台执行登记降级、登记故障、切换备用、处理故障。

    越级流转、停用调度台、操作终端或备用方式缺失、管辖范围内存在更高优先级
    故障链路等情况都会被拦下并说明原因；成功流转会留下切换记录。
    """
    action = str(payload.values.get("action") or "").strip()
    operator = str(payload.values.get("operator") or "").strip()
    entry, message = service.run_action(entry_id, action, operator or None)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出调度中心清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "dispatchcenter", "total": total, "items": items}
