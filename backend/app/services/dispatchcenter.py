"""调度中心业务规则：通道状态流转、字段校验、优先级处置与切换记录都收在这里。

通道状态按「正常 → 通道降级 → 设备故障 → 备用运行 → 正常」闭环流转，
每一步都只能由对应动作触发，不能越级直接标回正常。切换备用、处理故障
这类恢复性操作要服从同一管辖范围内的链路优先级：高优先级链路还处在异常
状态时，低优先级链路不允许抢先恢复。每次变更都留一条切换记录，交接后重新
进入页面仍能看到上一次是谁切的、什么时候切的。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "dispatchcenter"
REQUIRED_FIELDS = ["调度台编号", "管辖范围", "显示设备"]
# 通道状态序列：正常 → 通道降级 → 设备故障 → 备用运行，处理完故障回到正常。
STATUS_ORDER = ["正常", "通道降级", "设备故障", "备用运行"]
# 每个动作只允许从指定状态触发，杜绝越级直接标成正常。
ACTION_RULES: dict[str, dict[str, str]] = {
    "登记降级": {"from": "正常", "to": "通道降级"},
    "确认故障": {"from": "通道降级", "to": "设备故障"},
    "切换备用": {"from": "设备故障", "to": "备用运行"},
    "处理故障": {"from": "备用运行", "to": "正常"},
}
# 恢复性动作受链路优先级约束：同管辖范围内还有更高优先级链路异常时不得执行。
PRIORITY_ACTIONS = {"切换备用", "处理故障"}
ABNORMAL_STATUSES = {"通道降级", "设备故障"}
DISABLED_STATUS = "停用"
DEFAULT_OPERATOR = "值班管理员"


def _now_text() -> str:
    """统一时间口径，明细页和清单页展示一致。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_disabled(entry: dict[str, Any]) -> bool:
    return str(entry.get("调度台状态") or "").strip() == DISABLED_STATUS


def _is_abnormal(entry: dict[str, Any]) -> bool:
    return entry.get("status") in ABNORMAL_STATUSES


def _priority(entry: dict[str, Any]) -> int:
    """链路优先级，数值越小优先级越高；登记时未填写按最低优先级处理。"""
    try:
        return int(entry.get("优先级", 99))
    except (TypeError, ValueError):
        return 99


class DispatchcenterService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        scope: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("调度台编号", ""))
                or keyword in str(row.get("管辖范围", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if scope:
            rows = [row for row in rows if scope in str(row.get("管辖范围", ""))]
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
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update(
            {
                "调度台编号": str(values.get("调度台编号", "")).strip(),
                "管辖范围": str(values.get("管辖范围", "")).strip(),
                "显示设备": str(values.get("显示设备", "")).strip(),
                "操作终端": str(values.get("操作终端") or "").strip(),
                "通信链路": str(values.get("通信链路") or "").strip(),
                "备用方式": str(values.get("备用方式") or "").strip(),
            }
        )
        try:
            entry["优先级"] = int(values.get("优先级", 99))
        except (TypeError, ValueError):
            entry["优先级"] = 99
        entry["status"] = STATUS_ORDER[0]
        entry["通道状态"] = entry["status"]
        entry["调度台状态"] = "启用"
        entry["pending"] = False
        entry["abnormal"] = False
        entry["history"] = []
        entry["lastOperator"] = None
        entry["lastSwitchedAt"] = None
        rows.append(entry)
        return entry, []

    def list_history(self, entry_id: int) -> list[dict[str, Any]]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return []
        return list(entry.get("history", []))

    def allowed_actions(self, entry: dict[str, Any]) -> list[str]:
        """按当前通道状态给出可执行动作，清单页与明细页共用同一口径。"""
        if _is_disabled(entry):
            return []
        return [
            action
            for action, rule in ACTION_RULES.items()
            if entry.get("status") == rule["from"]
        ]

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        operator: str | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"调度台 {entry_id} 不存在或已归档"
        if _is_disabled(entry):
            return None, "该调度台已停用，不再参与通道状态变更"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于调度中心可执行范围"

        rule = ACTION_RULES[action]
        current = entry.get("status")
        if current != rule["from"]:
            return None, (
                f"通道当前为「{current}」，只能先流转到「{rule['from']}」，"
                f"不允许越级执行「{action}」"
            )

        # 操作终端与备用方式缺失时不允许变更通道状态：
        # 没有操作终端无法发起切换；没有备用方式，降级/备用动作无从执行。
        absent = [
            label
            for field, label in (("操作终端", "操作终端"), ("备用方式", "备用方式"))
            if not str(entry.get(field) or "").strip()
        ]
        if absent:
            return None, f"{'、'.join(absent)}缺失，不允许变更通道状态"

        if action in PRIORITY_ACTIONS:
            blocker = self._priority_blocker(entry)
            if blocker is not None:
                return None, (
                    f"同一管辖范围内调度台「{blocker.get('调度台编号')}」"
                    f"（优先级 {_priority(blocker)}）通道仍为「{blocker.get('status')}」，"
                    "须按优先级先处置高优先级链路"
                )

        target = rule["to"]
        operator_name = (operator or "").strip() or DEFAULT_OPERATOR
        switched_at = _now_text()
        record = {
            "action": action,
            "from": current,
            "to": target,
            "operator": operator_name,
            "switchedAt": switched_at,
        }
        history = entry.setdefault("history", [])
        history.append(record)

        entry["status"] = target
        # 通道状态字段与流转状态保持同步，清单页与明细页结论必须吻合。
        entry["通道状态"] = target
        entry["lastOperator"] = operator_name
        entry["lastSwitchedAt"] = switched_at
        # 备用运行仍在等待处理故障、回到正常，计入待处理；
        # 只有通道降级与设备故障计异常。
        entry["pending"] = target != "正常"
        entry["abnormal"] = target in ABNORMAL_STATUSES
        return entry, f"调度台已{action}：{current} → {target}（操作人：{operator_name}）"

    def _priority_blocker(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """同管辖范围内优先级更高且仍处异常的调度台；停用台不参与排队。"""
        scope = str(entry.get("管辖范围") or "")
        mine = _priority(entry)
        blockers = [
            row
            for row in store.rows(MODULE)
            if int(row.get("id", 0)) != int(entry.get("id", 0))
            and str(row.get("管辖范围") or "") == scope
            and not _is_disabled(row)
            and _is_abnormal(row)
            and _priority(row) < mine
        ]
        if not blockers:
            return None
        return min(blockers, key=_priority)
