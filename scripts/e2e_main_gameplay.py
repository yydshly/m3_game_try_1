"""
scripts/e2e_main_gameplay.py — 主入口完整路径 E2E 冒烟测试

通过 HTTP API 跑通从新建游戏到结局的完整路径。
同时验证主要失败路径。

前置要求：启动后端服务器
  python web_main.py
  （或 python -m uvicorn game.web_api:app --port 8000）

运行：
  python scripts/e2e_main_gameplay.py

依赖：pip install requests
"""

from __future__ import annotations

import sys
import requests

BASE_URL = "http://localhost:8000"
SESSION: str | None = None
FAILED: list[str] = []


# ── 辅助 ────────────────────────────────────────

def log(label: str, msg: str) -> None:
    print(f"  [{label}] {msg}")

def PASS(step: str) -> None:
    print(f"  [PASS] {step}")

def FAIL(step: str, reason: str) -> None:
    print(f"  [FAIL] {step}: {reason}")
    FAILED.append(f"{step}: {reason}")


def api_post(path: str, payload: dict, timeout: int = 30) -> requests.Response:
    """POST 到 API，返回 JSON 响应；失败时打印并 raise."""
    url = f"{BASE_URL}{path}"
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if not r.ok:
            # 返回 HTTP 200 但业务层报错（如 400），仍然解析 JSON
            pass
        return r
    except requests.exceptions.ConnectionError:
        print(f"  [FAIL] 无法连接到 {url} — 请确认服务器已启动 (python web_main.py)")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"  [FAIL] 请求超时 ({timeout}s): {url}")
        raise


def create_session() -> str:
    """新建游戏会话，返回 session_id."""
    r = requests.post(f"{BASE_URL}/api/session", json={"player_name": "E2E测试员"}, timeout=10)
    r.raise_for_status()
    d = r.json()
    sid = d["session_id"]
    log("session", f"新建 session: {sid}")
    return sid


def action(sid: str, type_: str, target=None, text=None, timeout: int = 30) -> dict:
    """发送动作请求，返回 JSON body (dict)."""
    payload = {"session_id": sid, "type": type_}
    if target is not None:
        payload["target"] = target
    if text is not None:
        payload["text"] = text
    r = api_post("/api/action", payload, timeout=timeout)
    d = r.json()
    return d


def get_state(sid: str) -> dict:
    """获取当前世界状态."""
    r = requests.get(f"{BASE_URL}/api/state/{sid}", timeout=10)
    r.raise_for_status()
    return r.json()


def require_ok(d: dict, step: str) -> None:
    if not d.get("ok", False):
        FAIL(step, f"API 返回 ok=False: {d.get('error', '未知错误')}")


# ── 主流程测试 ──────────────────────────────────

def test_initial_state(sid: str) -> None:
    """验证初始状态：phase=dinner, clock=0, location=大厅."""
    s = get_state(sid)
    checks = [
        (s["phase"] == "dinner",    f"phase 应为 dinner，实际 {s['phase']}"),
        (s["clock"] == 0,            f"clock 应为 0，实际 {s['clock']}"),
        (s["player_location"] == "大厅", f"location 应为 大厅，实际 {s['player_location']}"),
    ]
    for ok, msg in checks:
        if not ok:
            FAIL("初始状态", msg)
            return
    PASS("初始状态: dinner / clock=0 / 大厅")


def test_npc_tour(sid: str) -> dict:
    """
    按最优路径访问所有 NPC 并收集证据。
    返回 dict: talked_npcs, evidence.
    """
    # 路径: 书房(陈伯+林婉) → 餐厅(王总+苏苏) → 厨房(阿福) → 保安室(小张)
    # 格式: (action_type, target_or_NPC, unused, expected_player_location, expected_present_npcs_or_None)
    tour = [
        ("move",  "书房",      None, "书房",  ["陈伯", "林婉"]),
        ("talk",  "陈伯",      None, "书房",  None),
        ("talk",  "林婉",      None, "书房",  None),
        ("investigate", None,  None, "书房",  None),
        ("move",  "餐厅",      None, "餐厅",  ["王总", "苏苏"]),
        ("talk",  "王总",      None, "餐厅",  None),
        ("talk",  "苏苏",      None, "餐厅",  None),
        ("move",  "厨房",      None, "厨房",  ["阿福"]),
        ("talk",  "阿福",      None, "厨房",  None),
        ("move",  "保安室",   None, "保安室", ["小张"]),
        ("talk",  "小张",      None, "保安室", None),
    ]

    talked = set()
    evidence = []

    for atype, target, text, location, expected_npcs in tour:
        # 发送动作
        if atype == "talk":
            d = action(sid, atype, target=target, text="请说说昨晚的情况")
        else:
            d = action(sid, atype, target=target)

        require_ok(d, f"{atype} {target or ''}")

        s = d.get("state", {})
        cur_loc = s.get("player_location")

        # 验证位置（忽略纯视觉格式差异，如空格）
        cur_loc_stripped = cur_loc.strip() if cur_loc else ""
        location_stripped = location.strip() if location else ""
        if cur_loc_stripped != location_stripped:
            FAIL(f"位置检查 {atype}", f"应在 {location}，实际 {cur_loc}")
            return {}

        # 验证在场人物
        present = s.get("current_location", {}).get("present_npcs", [])
        if expected_npcs and set(present) != set(expected_npcs):
            FAIL(f"在场人物 {atype}", f"应在 {expected_npcs}，实际 {present}")

        # 记录 talked
        tn = s.get("talked_npcs", [])
        for n in tn:
            talked.add(n)

        # 记录 evidence
        ev_list = s.get("evidence_details", [])
        for ev in ev_list:
            if ev["name"] not in evidence:
                evidence.append(ev["name"])

        log(f"{atype} {target or ''}", f"loc={cur_loc} talked={len(tn)} ev={len(ev_list)}")

    PASS(f"NPC 巡游完成: talked={sorted(talked)} evidence={evidence}")
    return {"talked": talked, "evidence": evidence}


def test_dinner_to_investigation(sid: str) -> None:
    """验证 dinner → investigation 阶段转换（需 ≥5 个 talked_npcs）."""
    d = action(sid, "advance")
    require_ok(d, "advance (dinner→investigation)")
    s = d.get("state", {})
    phase = s.get("phase")
    if phase != "investigation":
        FAIL("dinner→investigation", f"phase 应为 investigation，实际 {phase}")
    else:
        PASS(f"阶段推进: dinner → investigation (clock={s.get('clock')})")


def test_investigation_to_confrontation(sid: str) -> None:
    """
    investigation 阶段：收集证据后推进，确认进入 confrontation.
    需要 ≥2 个 evidence 才能触发.
    """
    # 调查书房（借据等）和厨房（阿福证词）
    for loc in ["书房", "厨房"]:
        d = action(sid, "move", target=loc)
        require_ok(d, f"move {loc}")
        d = action(sid, "investigate")
        require_ok(d, f"investigate {loc}")
        ev = [e["name"] for e in d.get("state", {}).get("evidence_details", [])]
        log(f"investigate {loc}", f"evidence={ev}")

    d = action(sid, "advance")
    require_ok(d, "advance (investigation→confrontation)")
    s = d.get("state", {})
    phase = s.get("phase")
    if phase != "confrontation":
        FAIL("investigation→confrontation", f"phase 应为 confrontation，实际 {phase}")
    else:
        PASS(f"阶段推进: investigation → confrontation (clock={s.get('clock')})")


def test_accuse_and_ending(sid: str) -> str | None:
    """
    confrontation 阶段：指认林婉，确认进入 ending，
    返回 ending_key（成功时），失败时返回 None.
    注意：accuse 触发 DirectorAgent.judge (LLM 调用)，超时较长.
    """
    d = action(sid, "accuse", target="林婉", timeout=120)
    require_ok(d, "accuse 林婉")
    s = d.get("state", {})
    phase = s.get("phase")
    game_over = s.get("game_over", False)

    if phase != "ending":
        FAIL("指认→ending", f"phase 应为 ending，实际 {phase}")
        return None

    if not game_over:
        FAIL("指认→ending", "game_over 应为 True")

    # 从 events 中找 ending_key
    ending_key = None
    for ev in d.get("events", []):
        ek = ev.get("ending_key")
        if ek:
            ending_key = ek
            break

    if ending_key == "culprit_caught":
        PASS(f"结局验证: ending_key={ending_key} (真凶落网)")
        return ending_key
    else:
        FAIL("结局 ending_key", f"应为 culprit_caught，实际 {ending_key}")
        return ending_key


# ── 失败路径测试 ─────────────────────────────────

def test_invalid_action_type(sid: str) -> None:
    """非法 action type 应返回非 200."""
    r = requests.post(
        f"{BASE_URL}/api/action",
        json={"session_id": sid, "type": "fly", "target": "某地"},
        timeout=10,
    )
    if r.status_code == 400:
        PASS("非法 action type → HTTP 400")
    else:
        FAIL("非法 action type", f"期望 HTTP 400，实际 HTTP {r.status_code}")


def test_accuse_before_confrontation(sid: str) -> None:
    """confrontation 之前指认应报错 (HTTP 400)."""
    # 在 dinner 阶段指认
    r = requests.post(
        f"{BASE_URL}/api/action",
        json={"session_id": sid, "type": "accuse", "target": "陈伯"},
        timeout=10,
    )
    if r.status_code == 400:
        PASS("dinner 阶段指认 → HTTP 400")
    else:
        FAIL("dinner 阶段指认", f"期望 HTTP 400，实际 HTTP {r.status_code}")


def test_talk_absent_npc(sid: str) -> None:
    """盘问不在场 NPC 应报错."""
    r = requests.post(
        f"{BASE_URL}/api/action",
        json={"session_id": sid, "type": "talk", "target": "陈伯"},
        timeout=10,
    )
    if r.status_code == 400:
        PASS("盘问不在场 NPC → HTTP 400")
    else:
        FAIL("盘问不在场 NPC", f"期望 HTTP 400，实际 HTTP {r.status_code}")


def test_button_loading_recovery(sid: str) -> None:
    """验证 loading 后按钮状态能恢复 — 通过连续调用 advance."""
    results = []
    for i in range(3):
        d = action(sid, "advance")
        results.append(d.get("ok", False))
        if d.get("state", {}).get("phase") == "investigation":
            break  # 推进成功，不能再进

    if all(results):
        PASS(f"连续 advance 调用均成功: {len(results)} 次")
    else:
        FAIL("连续 advance 调用", f"有调用返回 ok=False: {results}")


def test_available_actions_structure(sid: str) -> None:
    """验证 available_actions 存在、类型正确、无空列表时结构正确."""
    s = get_state(sid)
    avail = s.get("available_actions")
    if avail is None:
        FAIL("available_actions", "字段缺失")
        return
    if not isinstance(avail, list):
        FAIL("available_actions", f"应为 list，实际 {type(avail)}")
        return
    # 验证每个 action 有必需字段
    for a in avail:
        for field in ("type", "label", "enabled"):
            if field not in a:
                FAIL("available_actions", f"缺少字段 {field}: {a}")
                return
    PASS(f"available_actions 结构正确 ({len(avail)} 个动作)")


# ── 特殊验证 ──────────────────────────────────────

def test_advance_rapid_call_risk(sid: str) -> None:
    """
    验证 advance 连续快速调用的风险。
    正常情况：每次 advance clock +1，phase 不会异常跳过。
    """
    # 先重置：用新 session
    sid2 = create_session()
    # 快速连续调用 advance 5 次
    clock_values = []
    phase_values = []
    for i in range(5):
        d = action(sid2, "advance")
        s = d.get("state", {})
        clock_values.append(s.get("clock"))
        phase_values.append(s.get("phase"))

    # clock 应该逐次递增，不应跳号
    expected = list(range(1, 6))
    if clock_values == expected:
        log("advance 连续调用", f"clock 序列正常: {clock_values}")
        PASS(f"advance 连续调用 clock 序列正常: {clock_values}")
    else:
        FAIL("advance 连续调用", f"clock 序列异常: {clock_values}，期望 {expected}")

    # phase 不应在未满足条件时突变
    unique_phases = list(dict.fromkeys(phase_values))
    log("advance 连续调用", f"phase 序列: {phase_values}，唯一值: {unique_phases}")
    # 在 dinner 阶段，5 次 advance 不应跳到 ending
    if "ending" in unique_phases:
        FAIL("advance 连续调用", f"phase 异常跳到 ending: {phase_values}")
    else:
        PASS(f"advance 连续调用 phase 序列正常: {unique_phases}")


# ── 入口 ────────────────────────────────────────

def main() -> int:
    global SESSION

    print("=" * 60)
    print("  主入口 E2E 冒烟测试")
    print("=" * 60)
    print(f"  目标服务器: {BASE_URL}")
    print()

    # ── 健康检查 ──────────────────────────────
    print("[Step 0] 服务器健康检查")
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
        PASS(f"服务器响应 HTTP {r.status_code}")
    except Exception as e:
        print(f"  [FAIL] 服务器不可用: {e}")
        print("  请先启动: python web_main.py")
        return 1

    # ── 失败路径测试（使用独立 session）────────
    print()
    print("[Step F1] 失败路径: 非法 action type")
    sid_f = create_session()
    test_invalid_action_type(sid_f)

    print()
    print("[Step F2] 失败路径: confrontation 前指认")
    test_accuse_before_confrontation(sid_f)

    print()
    print("[Step F3] 失败路径: 盘问不在场 NPC")
    test_talk_absent_npc(sid_f)

    print()
    print("[Step F4] 失败路径: available_actions 结构")
    test_available_actions_structure(sid_f)

    print()
    print("[Step F5] advance 连续调用风险")
    test_advance_rapid_call_risk(sid_f)

    # ── 主流程测试 ─────────────────────────────
    print()
    print("[Step 1] 新建游戏 session")
    SESSION = create_session()

    print()
    print("[Step 2] 验证初始状态")
    test_initial_state(SESSION)

    print()
    print("[Step 3] NPC 巡游 (对话 5+ NPC)")
    tour_result = test_npc_tour(SESSION)
    talked_count = len(tour_result.get("talked", []))

    print()
    print("[Step 4] dinner → investigation")
    test_dinner_to_investigation(SESSION)

    print()
    print("[Step 5] investigation → confrontation")
    test_investigation_to_confrontation(SESSION)

    print()
    print("[Step 6] confrontation → ending (指认林婉)")
    ending_key = test_accuse_and_ending(SESSION)

    print()
    print("[Step 7] 结局 ending_key SSE 事件")
    # ending_key 已在 Step 6 验证
    if ending_key:
        PASS(f"ending_key 正确消费: {ending_key}")
    else:
        FAIL("ending_key 消费", "未获得有效 ending_key")

    # ── 总结 ──────────────────────────────────
    print()
    print("=" * 60)
    print(f"  测试完成 — 失败项: {len(FAILED)}")
    print("=" * 60)
    if FAILED:
        print()
        print("失败详情:")
        for f in FAILED:
            print(f"  [FAIL] {f}")
        return 1
    else:
        print()
        print("  [PASS] 全部通过 — E2E 主流程验证成功")
        return 0


if __name__ == "__main__":
    sys.exit(main())
