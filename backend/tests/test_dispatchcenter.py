"""调度中心状态流转验证：直接跑业务规则层，不依赖 pytest。

用法：python3 tests/test_dispatchcenter.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.dispatchcenter import DispatchcenterService  # noqa: E402

service = DispatchcenterService()
checks = 0


def expect_ok(entry, message, keyword=""):
    global checks
    checks += 1
    assert entry is not None, f"应成功却被拦下：{message}"
    if keyword:
        assert keyword in message, f"提示语缺少「{keyword}」：{message}"
    return entry


def expect_blocked(entry, message, keyword):
    global checks
    checks += 1
    assert entry is None, f"应拦下却放行了：{message}"
    assert keyword in message, f"提示语缺少「{keyword}」：{message}"


# 1. 已停用的调度台不再参与状态变更
entry, msg = service.run_action(5, "登记降级", "测试员")
expect_blocked(entry, msg, "已停用")

# 2. 操作终端、备用方式缺失的不允许变更通道状态
entry, msg = service.run_action(6, "登记降级", "测试员")
expect_blocked(entry, msg, "缺失")

# 3. 完整流转：正常 → 通道降级 → 设备故障 → 备用运行 → 正常，全程留痕
entry, msg = service.run_action(1, "处理故障", "测试员")
expect_blocked(entry, msg, "不能越级")

entry = expect_ok(*service.run_action(1, "登记降级", "王值班"))
assert entry["status"] == "通道降级" and entry["通道状态"] == "通道降级"

entry, msg = service.run_action(1, "切换备用", "王值班")
expect_blocked(entry, msg, "不能越级")

entry = expect_ok(*service.run_action(1, "登记故障", "李值班"))
assert entry["status"] == "设备故障"

entry, msg = service.run_action(1, "处理故障", "李值班")
expect_blocked(entry, msg, "不能越级")  # 设备故障不能直接标回正常

entry = expect_ok(*service.run_action(1, "切换备用", "钱值班"))
assert entry["status"] == "备用运行"

entry = expect_ok(*service.run_action(1, "处理故障", "赵值班"))
assert entry["status"] == "正常" and entry["通道状态"] == "正常"

history = entry["切换记录"]
assert [r["动作"] for r in history] == ["登记降级", "登记故障", "切换备用", "处理故障"]
assert [r["操作人"] for r in history] == ["王值班", "李值班", "钱值班", "赵值班"]
assert all(r["时间"] for r in history), "每次切换都要记下时间"
assert entry["最近操作人"] == "赵值班" and entry["最近切换时间"] == history[-1]["时间"]

# 4. 管辖范围内同时出问题时按优先级处理：低优先级的 DISP-0007 被高优先级的拦住
entry, msg = service.run_action(7, "切换备用", "测试员")
expect_blocked(entry, msg, "DISP-0003")
assert "优先级" in msg

# 高优先级的 DISP-0003 可以先切备用
entry = expect_ok(*service.run_action(3, "切换备用", "钱值班"))
assert entry["status"] == "备用运行"

# DISP-0002（中，通道降级）仍压着 DISP-0007（低）
entry, msg = service.run_action(7, "切换备用", "测试员")
expect_blocked(entry, msg, "DISP-0002")

# 按顺序处理完中优先级链路后，低优先级才放行
expect_ok(*service.run_action(2, "登记故障", "李值班"))
expect_ok(*service.run_action(2, "切换备用", "钱值班"))
expect_ok(*service.run_action(2, "处理故障", "赵值班"))
entry = expect_ok(*service.run_action(7, "切换备用", "钱值班"))
assert entry["status"] == "备用运行"
expect_ok(*service.run_action(7, "处理故障", "赵值班"))
expect_ok(*service.run_action(3, "处理故障", "赵值班"))

# 5. 清单与明细结论一致：列表里看到的通道状态与明细页一致
items, total = service.list_entries(page=1, size=50)
assert total == 7
for row in items:
    detail = service.get_entry(int(row["id"]))
    assert row["通道状态"] == detail["status"], f"{row['调度台编号']} 清单与明细不一致"

# 6. 未知动作与不存在的调度台都要给出可读说明
entry, msg = service.run_action(1, "重启通道", "测试员")
expect_blocked(entry, msg, "不属于")
entry, msg = service.run_action(999, "登记降级", "测试员")
expect_blocked(entry, msg, "不存在")

# 7. 登记新调度台：缺必填字段要说明，登记成功从「正常」起步、记录为空
entry, missing = service.create_entry({"调度台编号": "DISP-0008"})
assert entry is None and "管辖范围" in missing and "显示设备" in missing
entry, missing = service.create_entry({
    "调度台编号": "DISP-0008", "管辖范围": "中心三区", "显示设备": "调度大屏C2",
    "操作终端": "调度终端08", "备用方式": "备用光纤通道",
})
checks += 1
assert not missing and entry["status"] == "正常" and entry["通道状态"] == "正常"
assert entry["切换记录"] == [] and entry["调度台状态"] == "在用"

print(f"全部 {checks} 项检查通过")
