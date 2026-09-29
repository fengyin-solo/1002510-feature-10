"""调度中心业务规则：通道状态流转、切换记录与优先级处理都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "dispatchcenter"
REQUIRED_FIELDS = ["调度台编号", "管辖范围", "显示设备"]
STATUS_ORDER = ["正常", "通道降级", "设备故障", "备用运行"]
# 通道状态只允许逐级流转：正常 → 通道降级 → 设备故障 → 备用运行 → 正常，
# 每个动作登记 (来源状态, 目标状态)，越级流转一律拦下。
ACTION_RULES = {
    "登记降级": ("正常", "通道降级"),
    "登记故障": ("通道降级", "设备故障"),
    "切换备用": ("设备故障", "备用运行"),
    "处理故障": ("备用运行", "正常"),
}
# 操作终端、备用方式缺失的调度台不允许变更通道状态。
GUARD_FIELDS = ["操作终端", "备用方式"]
DISABLED_STATUS = "已停用"
DEFAULT_CONSOLE_STATUS = "在用"
# 管辖范围内多条通信链路同时出问题时，按优先级从高到低处理。
PRIORITY_ORDER = {"高": 0, "中": 1, "低": 2}
DEFAULT_PRIORITY = "中"
# 处于这两种状态的链路视为“正在出问题”，参与优先级比较。
FAULT_STATUSES = ("通道降级", "设备故障")
# 只有处置类动作（往恢复方向走）才校验优先级；登记类动作只是如实记录。
PRIORITY_GUARD_ACTIONS = ("切换备用", "处理故障")


class DispatchcenterService:
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
            rows = [row for row in rows if keyword in str(row.get("调度台编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        optional = ["操作终端", "通信链路", "备用方式"]
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS + optional})
        entry["优先级"] = str(values.get("优先级") or DEFAULT_PRIORITY)
        entry["调度台状态"] = str(values.get("调度台状态") or DEFAULT_CONSOLE_STATUS)
        entry["status"] = STATUS_ORDER[0]
        entry["通道状态"] = STATUS_ORDER[0]
        entry["pending"] = False
        entry["abnormal"] = False
        entry["切换记录"] = []
        entry["最近操作人"] = ""
        entry["最近切换时间"] = ""
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        operator: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"调度台 {entry_id} 不存在或已归档"
        if entry.get("调度台状态") == DISABLED_STATUS:
            return None, f"调度台 {entry.get('调度台编号', entry_id)} 已停用，不再参与通道状态变更"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于调度中心可执行范围"
        missing = [field for field in GUARD_FIELDS if not str(entry.get(field) or "").strip()]
        if missing:
            return None, f"{'、'.join(missing)}缺失，不允许变更通道状态"
        source, target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current != source:
            return None, (
                f"当前通道状态为「{current}」，不能越级流转到「{target}」，"
                f"需按 {' → '.join(STATUS_ORDER + [STATUS_ORDER[0]])} 依次处理"
            )
        if action in PRIORITY_GUARD_ACTIONS:
            blocker = self._higher_priority_fault(entry)
            if blocker is not None:
                return None, (
                    f"管辖范围「{entry.get('管辖范围')}」内调度台 {blocker.get('调度台编号')}"
                    f"（优先级{blocker.get('优先级', DEFAULT_PRIORITY)}）的通信链路仍在"
                    f"「{blocker.get('status')}」，请按优先级先处理"
                )
        operator_name = str(operator or "").strip() or "值班调度员"
        self._apply_transition(entry, action, target, operator_name)
        return entry, f"调度台已{action}，通道状态：{source} → {target}"

    def _higher_priority_fault(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """找同管辖范围内仍在故障中、且优先级更高的调度台。"""
        scope = str(entry.get("管辖范围") or "")
        own_rank = PRIORITY_ORDER.get(str(entry.get("优先级") or DEFAULT_PRIORITY), 1)
        candidates = []
        for row in store.rows(MODULE):
            if row is entry or int(row.get("id", 0)) == int(entry.get("id", 0)):
                continue
            if row.get("调度台状态") == DISABLED_STATUS:
                continue
            if str(row.get("管辖范围") or "") != scope:
                continue
            if row.get("status") not in FAULT_STATUSES:
                continue
            rank = PRIORITY_ORDER.get(str(row.get("优先级") or DEFAULT_PRIORITY), 1)
            if rank < own_rank:
                candidates.append(row)
        if not candidates:
            return None
        return min(candidates, key=lambda row: PRIORITY_ORDER.get(str(row.get("优先级") or DEFAULT_PRIORITY), 1))

    def _apply_transition(self, entry: dict[str, Any], action: str, target: str, operator: str) -> None:
        source = str(entry.get("status") or "")
        entry["status"] = target
        # 清单与明细页都读「通道状态」，流转时同步刷新，保证两边结论一致。
        entry["通道状态"] = target
        entry["pending"] = target != STATUS_ORDER[0]
        entry["abnormal"] = target in FAULT_STATUSES
        record = {
            "动作": action,
            "原状态": source,
            "目标状态": target,
            "操作人": operator,
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        history = entry.setdefault("切换记录", [])
        history.append(record)
        entry["最近操作人"] = operator
        entry["最近切换时间"] = record["时间"]
