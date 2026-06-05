"""
main.py — Phase 4 命令行入口

Phase 4 新增命令:
    指认 <NPC名>              在 confrontation 阶段指认凶手,触发结局判定
    退出

Phase 3 及之前命令:
    跟 <NPC名> 说: <话>       对话
    移动到 <地点>              移动
    调查                       调查当前地点
    推进时段                   时间推进
    查看状态 / 存档 / 读档
"""

from __future__ import annotations

import sys
from typing import Optional

from game.actions import dispatch, PlayerAction
from game.agents import DirectorAgent, NPCDialogueAgent, NarratorAgent
from game.persistence import load_game, save_game
from game.rules import (
    MAX_CLOCK,
    all_npc_locations,
    check_phase_transition,
    clock_name,
)
from game.scenario_data import build_initial_world
from game.state import PHASE_CONFRONTATION, WorldState

# 可调查地点列表
VALID_LOCATIONS = [
    "书房", "厨房", "大厅", "保安室",
    "陈伯房间", "苏苏房间", "林婉房间", "王总房间",
    "餐厅", "走廊", "自己房间",
]


def parse_command(line: str) -> Optional[tuple[str, list[str]]]:
    """解析命令,返回 (cmd, [args...]) 或 None。"""
    stripped = line.strip()
    if not stripped:
        return None

    # 跟 NPC 对话
    if stripped.startswith("跟"):
        if "说:" not in stripped:
            return None
        parts = stripped.split()
        try:
            name = parts[1]
            msg = stripped.split("说:", 1)[1].strip()
            return ("talk", [name, msg])
        except IndexError:
            return None

    # 移动
    if stripped.startswith("移动到"):
        loc = stripped[3:].strip()
        return ("move", [loc])

    # 调查
    if stripped in ("调查", "搜查", "搜"):
        return ("investigate", [])

    # 推进时段
    if stripped in ("推进时段", "推进时间", "下个时段", "时间推进"):
        return ("advance", [])

    # 存档读档
    if stripped in ("存档", "保存", "save"):
        return ("save", [])
    if stripped in ("读档", "加载", "load"):
        return ("load", [])

    # 状态
    if stripped in ("查看状态", "状态", "s", "查看"):
        return ("status", [])

    # 指认
    if stripped.startswith("指认"):
        target = stripped[2:].strip()
        if target:
            return ("accuse", [target])
        return None

    # 退出
    if stripped in ("退出", "exit", "quit", "q"):
        return ("quit", [])

    return None


def cmd_status(world: WorldState) -> None:
    """打印当前状态。"""
    locs = all_npc_locations(world)
    print("\n===== 当前状态 =====")
    print(f"时段: {clock_name(world.clock)}")
    print(f"阶段: {world.phase}")
    print(f"你在: {world.player.location}")
    print(f"持有物品: {world.player.inventory or '(无)'}")
    print(f"已对话NPC数: {len(world.player.revealed_to)}")
    print(f"证据数: {len(world.player.inventory)}")
    print("\n各人位置:")
    for name, loc in locs.items():
        marker = " ←" if name in world.player.revealed_to else ""
        print(f"  {name}: {loc}{marker}")
    print("====================\n")


def cmd_accuse(world: WorldState, accused: str) -> bool:
    """
    执行指认。
    返回 True 表示游戏结束，False 表示指认被拒绝（阶段不对）。
    """
    # 必须在 confrontation 阶段才能指认
    if world.phase != PHASE_CONFRONTATION:
        pending = check_phase_transition(world)
        if pending:
            print(f"【系统】需要先进入 {pending} 阶段才能指认。")
        else:
            print("【系统】还没到对峙阶段，继续调查吧。")
        return False

    if accused not in world.npcs:
        print(f"'{accused}' 不是有效嫌疑人。可选: {', '.join(world.npcs.keys())}")
        return False

    print(f"\n{'='*60}")
    print(f"  指认: {accused}")
    print(f"{'='*60}")

    # 调用 DirectorAgent 判定结局
    judgment = DirectorAgent.judge(world, player_accusation=accused)

    print(f"\n{'='*60}")
    print(f"  【结局】{judgment['verdict']}")
    print(f"{'='*60}")
    print(f"\n{judgment['summary']}\n")

    innocent = judgment.get("innocent", [])
    if innocent:
        print(f"经查证无辜: {', '.join(innocent)}")

    print(f"\n真凶: {judgment['culprit']}")
    print(f"\n{'='*60}")
    print("  游戏结束。感谢游玩《孤岛晚宴》！")
    print(f"{'='*60}\n")

    # 推进到 ending
    world.phase = "ending"
    return True


def cmd_narrate(world: WorldState) -> None:
    """推进时段+叙事播报。"""
    old_clock = world.clock
    new_clock = advance_clock(world)
    advance_phase(world)

    print(f"\n{'='*60}")
    print(f"⏰ {clock_name(old_clock)} → {clock_name(new_clock)}")
    print(f"{'='*60}")

    # NarratorAgent 生成氛围描写
    narration = NarratorAgent.narrate(world)
    print(f"\n{narration}\n")

    # Phase 3: 时段推进时 NPC 自动行为
    npc_events = on_clock_advance(world)
    for ev in npc_events:
        print(ev)

    # Phase 3: 林婉在证据暴露后可能触发 DecisionAgent
    if _linwan_evidence_exposed(world):
        linwan = world.npcs.get("林婉")
        if linwan and linwan.alive:
            decision = NPCDecisionAgent.decide(linwan, world)
            action = decision.get("action", "wait")
            if action != "wait":
                reason = decision.get("reason", "")
                target = decision.get("target", "")
                print(f"\n【林婉的决策】{action}（原因: {reason}）")
                from game.state import Event
                world.public_events.append(
                    Event(
                        clock=world.clock,
                        description=f"【林婉决策】{action} - {reason}",
                        visible_to=["all"],
                    )
                )

    # 检查阶段推进
    pending = check_phase_transition(world)
    if pending and pending != world.phase:
        print(f"【系统】已满足 {pending} 阶段进入条件，使用「推进时段」即可进入。")

    # Phase 4: 时段到达上限（渡船到达），自动触发结局
    if world.clock >= MAX_CLOCK and world.phase != "ending":
        advance_phase(world)
        if world.phase == "ending":
            print(f"\n{'='*60}")
            print("  渡船已经靠岸！时间耗尽。")
            print(f"{'='*60}")
            judgment = DirectorAgent.judge(world, player_accusation=None)
            print(f"\n{'='*60}")
            print(f"  【结局】{judgment['verdict']}")
            print(f"{'='*60}")
            print(f"\n{judgment['summary']}\n")
            print(f"真凶: {judgment['culprit']}")
            print(f"{'='*60}")
            print("  游戏结束。感谢游玩《孤岛晚宴》！")
            print(f"{'='*60}\n")
            try:
                again = input("再来一局？(y/n) > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                again = "n"
            if again == "y":
                world = build_initial_world()
                print("\n重新开始...\n")
                cmd_status(world)
            else:
                print("再见。")
                sys.exit(0)


def intro() -> None:
    print(
        "\n"
        "═══════════════════════════════════════════════════════════════\n"
        "          《孤岛晚宴》— Phase 4\n\n"
        "  你是被请来的私人侦探。暴风雨把所有人困在孤岛别墅。\n"
        "  岛主周慎之今晨死于书房,茶杯里有异常。\n"
        "  天亮前,找出真凶。\n\n"
        "  命令:\n"
        "    跟 <NPC名> 说: <话>   对话\n"
        "    移动到 <地点>         移动(书房/厨房/大厅/餐厅等)\n"
        "    调查                  在当前地点调查\n"
        "    推进时段              时间推进(同时播报场景)\n"
        "    查看状态              当前状态\n"
        "    存档 / 读档           保存或加载进度\n"
        "    指认 <NPC名>          在对峙阶段指认凶手(需先进入 confrontation)\n"
        "    退出\n"
        "═══════════════════════════════════════════════════════════════\n"
    )


def main() -> None:
    world: WorldState = build_initial_world()
    intro()

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            sys.exit(0)

        parsed = parse_command(raw)
        if parsed is None:
            print("无法理解命令。输入 查看状态 查看可用命令。")
            continue

        cmd, args = parsed

        if cmd == "quit":
            print("再见。")
            sys.exit(0)

        # 统一走 dispatch()
        if cmd == "status":
            result = dispatch(world, PlayerAction(type="status"))
        elif cmd == "save":
            result = dispatch(world, PlayerAction(type="save"))
        elif cmd == "load":
            result = dispatch(world, PlayerAction(type="load"))
        elif cmd == "advance":
            result = dispatch(world, PlayerAction(type="advance"))
        elif cmd == "accuse":
            result = dispatch(world, PlayerAction(type="accuse", target=args[0]))
            if result.ok and world.phase == "ending":
                try:
                    again = input("再来一局？(y/n) > ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    again = "n"
                if again == "y":
                    world = build_initial_world()
                    print("\n重新开始...\n")
                    cmd_status(world)
                else:
                    print("再见。")
                    sys.exit(0)
            continue
        elif cmd == "move":
            result = dispatch(world, PlayerAction(type="move", target=args[0]))
        elif cmd == "investigate":
            result = dispatch(world, PlayerAction(type="investigate"))
        elif cmd == "talk":
            npc_name, message = args
            result = dispatch(world, PlayerAction(type="talk", target=npc_name, text=message))
        else:
            continue

        # 打印 dispatch 返回的 events
        if not result.ok:
            print(result.error)
        for ev in result.events:
            kind = ev.get("kind", "")
            text = ev.get("text", "")
            if kind == "npc":
                print(f"\n【{ev.get('speaker', '')}】\n{text}")
            elif kind == "clock":
                print(f"\n{'='*60}")
                print(f"  {text}")
                print(f"{'='*60}")
            elif kind == "narrator":
                print(f"\n{text}\n")
            elif kind == "game_over":
                print(f"\n{'='*60}")
                print(f"  {text}")
                print(f"{'='*60}\n")
            elif kind == "investigate":
                print(f"【调查】{text}")
            else:
                print(text)


if __name__ == "__main__":
    main()
