"""
scripts/smoke_test.py — 核心流程冒烟测试

不依赖真实 M3 API，不触发 M3 调用，只测规则层/动作层/状态层。
运行：python scripts/smoke_test.py
"""

import sys
from pathlib import Path

# 确保项目根在 path 上
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.scenario_data import build_initial_world
from game.actions import (
    PlayerAction,
    dispatch,
    available_actions,
    VALID_LOCATIONS,
)
from game.rules import PHASE_CONFRONTATION, npc_location_at


def test_build_world():
    """测试：build_initial_world 能正常创建世界"""
    w = build_initial_world()
    assert w.player.location == "大厅"
    assert w.phase == "dinner"
    assert w.clock == 0
    assert len(w.npcs) == 6
    print("[PASS] test_build_world")


def test_available_actions():
    """测试：available_actions(world) 能返回动作列表"""
    w = build_initial_world()
    actions = available_actions(w)
    types = {a.type for a in actions}
    assert "move" in types
    assert "investigate" in types
    assert "advance" in types
    # 没有同地点 NPC，故无 talk
    talk_actions = [a for a in actions if a.type == "talk"]
    assert len(talk_actions) == 0
    # accuse 存在但 disabled
    accuse_actions = [a for a in actions if a.type == "accuse"]
    assert len(accuse_actions) == 6
    assert all(not a.enabled for a in accuse_actions)
    print("[PASS] test_available_actions")


def test_move_and_investigate():
    """测试：移动到书房，调查能拿到新遗嘱草稿"""
    w = build_initial_world()
    r = dispatch(w, PlayerAction(type="move", target="书房"))
    assert r.ok, f"移动失败: {r.error}"
    assert w.player.location == "书房"

    r = dispatch(w, PlayerAction(type="investigate"))
    assert r.ok, f"调查失败: {r.error}"
    assert "新遗嘱草稿" in w.player.inventory
    print("[PASS] test_move_and_investigate")


def test_talk_wrong_location():
    """测试：非同地点 NPC 对话会被拒绝"""
    w = build_initial_world()
    # 玩家在大厅，陈伯在书房，拒绝
    r = dispatch(w, PlayerAction(type="talk", target="陈伯", text="你好"))
    assert not r.ok, "非同地点对话应该被拒绝"
    assert "不在这里" in r.error
    print("[PASS] test_talk_wrong_location")


def test_talk_correct_location():
    """测试：同地点 NPC 对话能成功（需要先移动）"""
    w = build_initial_world()
    # 移动到书房（陈伯在书房）
    dispatch(w, PlayerAction(type="move", target="书房"))
    # 现在同地点，可以对话（但不真正调用 M3）
    # 由于 dispatch 内部会调 NPCDialogueAgent.respond，这里我们只测试规则校验
    # 不实际调用 M3，故只验证校验逻辑
    r = dispatch(w, PlayerAction(type="talk", target="陈伯", text="你好"))
    # M3 未配置时可能抛异常，但规则校验应该先通过
    # 这里只验证 location check 通过了（error 不含"不在这里"）
    if not r.ok:
        assert "不在这里" not in r.error, f"location check failed unexpectedly: {r.error}"
    print("[PASS] test_talk_correct_location (location check passed)")


def test_accuse_wrong_phase():
    """测试：非 confrontation 阶段指认会被拒绝"""
    w = build_initial_world()
    assert w.phase != PHASE_CONFRONTATION
    r = dispatch(w, PlayerAction(type="accuse", target="林婉"))
    assert not r.ok, "非对峙阶段指认应该被拒绝"
    assert "对峙" in r.error
    print("[PASS] test_accuse_wrong_phase")


def test_invalid_location():
    """测试：非法地点移动被拒绝"""
    w = build_initial_world()
    r = dispatch(w, PlayerAction(type="move", target="不存在的地点"))
    assert not r.ok
    assert "无效" in r.error
    print("[PASS] test_invalid_location")


def test_status_action():
    """测试：status 动作返回状态信息"""
    w = build_initial_world()
    r = dispatch(w, PlayerAction(type="status"))
    assert r.ok
    assert any("时段" in ev["text"] for ev in r.events)
    print("[PASS] test_status_action")


def test_advance_blocked_without_conditions():
    """测试：晚宴阶段未满足盘问条件时，advance 被拒绝且 clock 不变化"""
    w = build_initial_world()
    old_clock = w.clock
    r = dispatch(w, PlayerAction(type="advance"))
    assert not r.ok
    assert "还需盘问" in r.error
    assert w.clock == old_clock
    assert w.phase == "dinner"
    print("[PASS] test_advance_blocked_without_conditions")


def test_advance_after_talk_conditions():
    """测试：晚宴阶段满足盘问条件后，advance 推进 clock 并进入 investigation"""
    w = build_initial_world()
    # Inject sufficient talk records to satisfy DINNER_MIN_TALKS without calling M3
    w.player.revealed_to = {
        "陈伯": ["已盘问"],
        "林婉": ["已盘问"],
        "王总": ["已盘问"],
        "苏苏": ["已盘问"],
        "阿福": ["已盘问"],
    }
    old_clock = w.clock
    r = dispatch(w, PlayerAction(type="advance"))
    assert r.ok, f"advance failed: {r.error}"
    assert w.clock == old_clock + 1
    assert w.phase == "investigation"
    print("[PASS] test_advance_after_talk_conditions")


def test_npc_dialogue_prompt_includes_visible_case_context():
    """测试：NPC 对话 prompt 包含玩家已知证据和问题命中信息，不调用真实 M3"""
    from game.scenario_data import build_initial_world
    from game.actions import PlayerAction, dispatch
    from game.agents import NPCDialogueAgent
    import game.agents as agents

    w = build_initial_world()

    # 玩家前往书房并调查，获得"新遗嘱草稿"
    r = dispatch(w, PlayerAction(type="move", target="书房"))
    assert r.ok, f"move failed: {r.error}"

    r = dispatch(w, PlayerAction(type="investigate"))
    assert r.ok, f"investigate failed: {r.error}"
    assert "新遗嘱草稿" in w.player.inventory

    captured = {}
    original_call_m3 = agents.call_m3

    def fake_call_m3(*, system, user, purpose, temperature, max_tokens, thinking_enabled):
        captured["system"] = system
        captured["user"] = user
        captured["purpose"] = purpose
        captured["temperature"] = temperature
        captured["max_tokens"] = max_tokens
        captured["thinking_enabled"] = thinking_enabled
        return "我知道这份新遗嘱草稿，但有些事我还不能乱说。"

    try:
        agents.call_m3 = fake_call_m3
        reply = NPCDialogueAgent.respond(
            npc=w.npcs["陈伯"],
            world=w,
            player_message="新遗嘱草稿是怎么回事？",
        )
    finally:
        agents.call_m3 = original_call_m3

    assert reply
    prompt = captured.get("user", "")

    # visible_case_context block present
    assert "当前可见案件上下文" in prompt
    # evidence details present
    assert "新遗嘱草稿" in prompt
    assert "来源:书房" in prompt
    assert "指向:动机" in prompt
    # question hit annotation present — use a message containing the exact evidence name
    assert "玩家正在追问已持有证据: 新遗嘱草稿" in prompt, \
        "hint: evidence hit fires when full name appears in player_message"
    # location and phase present
    assert "玩家当前位置: 书房" in prompt
    assert "你的当前位置: 书房" in prompt
    # correct purpose tag
    assert captured.get("purpose") == "npc_dialogue:陈伯"

    print("[PASS] test_npc_dialogue_prompt_includes_visible_case_context")


def test_valid_locations_match_rules():
    """测试：actions.py 的 VALID_LOCATIONS 和 rules.py 一致"""
    from game.rules import _NPC_LOCATIONS
    # 至少包含场景中所有提到的地点
    all_locs = set()
    for locs in _NPC_LOCATIONS.values():
        all_locs.update(locs.values())
    for loc in all_locs:
        assert loc in VALID_LOCATIONS, f"{loc} not in VALID_LOCATIONS"
    print("[PASS] test_valid_locations_match_rules")


def test_save_load_flow():
    """测试：存档和读档（不调用 M3）"""
    import tempfile, os
    from game.persistence import save_game, load_game

    w = build_initial_world()
    dispatch(w, PlayerAction(type="move", target="书房"))
    dispatch(w, PlayerAction(type="investigate"))

    with tempfile.TemporaryDirectory() as tmpdir:
        from pathlib import Path
        path = Path(tmpdir) / "test_save.json"
        saved_path = save_game(w, path)
        assert saved_path.exists()

        loaded = load_game(path)
        assert loaded.player.location == "书房"
        assert "新遗嘱草稿" in loaded.player.inventory
        assert loaded.phase == w.phase
        assert loaded.clock == w.clock

    print("[PASS] test_save_load_flow")


def _force_confrontation_phase(w):
    """Helper: 直接把 world 推入 confrontation 阶段（用于测试指认路径）"""
    w.phase = PHASE_CONFRONTATION


def test_ending_key_correct_accusation():
    """测试：正确指认林婉时 game_over.ending_key == 'culprit_caught'"""
    w = build_initial_world()
    _force_confrontation_phase(w)
    r = dispatch(w, PlayerAction(type="accuse", target="林婉"))
    assert r.ok, f"指认失败: {r.error}"
    go_events = [e for e in r.events if e.get("kind") == "game_over"]
    assert len(go_events) == 1, "应该有 1 个 game_over 事件"
    d = go_events[0]
    assert "ending_key" in d, "game_over 事件缺少 ending_key 字段"
    assert d["ending_key"] == "culprit_caught", f"正确指认林婉应是 culprit_caught，实际: {d['ending_key']}"
    print("[PASS] test_ending_key_correct_accusation")


def test_ending_key_wrong_accusation():
    """测试：错误指认其他人时 game_over.ending_key == 'wrong_accuse'"""
    w = build_initial_world()
    _force_confrontation_phase(w)
    r = dispatch(w, PlayerAction(type="accuse", target="陈伯"))
    assert r.ok, f"指认失败: {r.error}"
    go_events = [e for e in r.events if e.get("kind") == "game_over"]
    assert len(go_events) == 1, "应该有 1 个 game_over 事件"
    d = go_events[0]
    assert "ending_key" in d, "game_over 事件缺少 ending_key 字段"
    assert d["ending_key"] == "wrong_accuse", f"错误指认应是 wrong_accuse，实际: {d['ending_key']}"
    print("[PASS] test_ending_key_wrong_accusation")


def test_ending_key_structure():
    """测试：game_over 事件包含所有必需的结构化字段（含 ending_key）"""
    w = build_initial_world()
    _force_confrontation_phase(w)
    r = dispatch(w, PlayerAction(type="accuse", target="苏苏"))
    assert r.ok
    go_events = [e for e in r.events if e.get("kind") == "game_over"]
    assert len(go_events) == 1
    d = go_events[0]
    for field in ("verdict", "summary", "culprit", "innocent", "ending_key"):
        assert field in d, f"game_over 缺少字段: {field}"
    print("[PASS] test_ending_key_structure")


def test_guide_returns_action_for_initial_state():
    """测试：guide API 初始状态返回 move/talk/investigate/advance 之一，不返回 None"""
    from game.web_api import _build_guide
    w = build_initial_world()
    guide = _build_guide(w)
    assert guide is not None
    assert "action" in guide
    # action can be None only in ending phase
    assert guide["action"] is not None, "Initial state guide should have an action"
    assert guide["action"]["type"] in ("move", "talk", "investigate", "advance"), \
        f"Unexpected action type: {guide['action']['type']}"
    print("[PASS] test_guide_returns_action_for_initial_state")


def test_guide_does_not_modify_world():
    """测试：guide API 不修改 WorldState"""
    from game.web_api import _build_guide
    w = build_initial_world()
    import copy
    w_before = copy.deepcopy(w)
    _build_guide(w)
    w_after = w
    assert w_after.phase == w_before.phase
    assert w_after.clock == w_before.clock
    assert w_after.player.location == w_before.player.location
    assert w_after.player.inventory == w_before.player.inventory
    assert w_after.player.revealed_to == w_before.player.revealed_to
    print("[PASS] test_guide_does_not_modify_world")


def test_guide_confrontation_returns_accuse_linwan():
    """测试：confrontation 阶段 guide 返回 accuse 林婉"""
    from game.web_api import _build_guide
    w = build_initial_world()
    _force_confrontation_phase(w)
    guide = _build_guide(w)
    assert guide is not None
    assert guide["action"] is not None
    assert guide["action"]["type"] == "accuse"
    assert guide["action"]["target"] == "林婉", \
        f"Expected accuse linwan, got {guide['action']['target']}"
    print("[PASS] test_guide_confrontation_returns_accuse_linwan")


def main():
    tests = [
        test_build_world,
        test_available_actions,
        test_move_and_investigate,
        test_talk_wrong_location,
        test_talk_correct_location,
        test_accuse_wrong_phase,
        test_invalid_location,
        test_status_action,
        test_advance_blocked_without_conditions,
        test_advance_after_talk_conditions,
        test_npc_dialogue_prompt_includes_visible_case_context,
        test_valid_locations_match_rules,
        test_save_load_flow,
        test_ending_key_correct_accusation,
        test_ending_key_wrong_accusation,
        test_ending_key_structure,
        test_guide_returns_action_for_initial_state,
        test_guide_does_not_modify_world,
        test_guide_confrontation_returns_accuse_linwan,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"  测试结果: {passed} 通过, {failed} 失败")
    print(f"{'='*50}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
