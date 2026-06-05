"""
game/scenario_data.py — 把 docs/SCENARIO.md 转译为初始 WorldState

Phase 2 激活全部 6 个 NPC(见 docs/PLAN.md Phase 2)。

数据完全照搬 docs/SCENARIO.md,不许私自调整。
"""

from __future__ import annotations

from game.state import (
    PHASE_DINNER,
    NPCState,
    PlayerState,
    WorldState,
)

INITIAL_SCENE: str = (
    "海上孤岛别墅,古堡大厅。窗外暴风雨大作,渡船清晨才能返回。"
    "岛主周慎之(70岁富商)今早被发现死在书房——表面是心脏病,"
    "但管家陈伯发现茶杯里有异常残留。所有人被困在岛上,"
    "玩家是被请来的私人侦探。"
)


def _build_chenbo() -> NPCState:
    return NPCState(
        name="陈伯",
        public_role="服侍周家 30 年的老管家",
        hidden_goal="保护少主(周慎之的私生子,无人知晓其身份)",
        secrets=[
            "知道新遗嘱的存在",
            "知道周慎之有个私生子",
            "最先发现茶杯异常",
        ],
        personality="沉稳、忠诚、说话留三分、对'遗产'话题极度回避",
        memory=[],
        relationships={"周慎之": 90, "林婉": 20, "苏苏": 40, "王总": 10, "阿福": 70, "小张": 50},
        alive=True,
        suspicion_of_player=20,
    )


def _build_linwan() -> NPCState:
    """医生林婉——真凶。"""
    return NPCState(
        name="林婉",
        public_role="周慎之的私人医生",
        hidden_goal="销毁能证明她知晓绝症诊断的病历,洗清嫌疑",
        secrets=[
            "早就知道周慎之患绝症",
            "我下的毒",
            "新遗嘱断了我的研究经费",
        ],
        personality="冷静、专业、善于把话题引向医学解释、被逼问时会反咬别人",
        memory=[],
        relationships={"周慎之": -40, "陈伯": 10, "苏苏": 0, "王总": 30, "阿福": 20, "小张": 10},
        alive=True,
        suspicion_of_player=15,
    )


def _build_susu() -> NPCState:
    return NPCState(
        name="苏苏",
        public_role="周慎之的侄女,来探望",
        hidden_goal="拿到遗产,并把嫌疑引向堂兄王总",
        secrets=[
            "昨晚偷听到林婉和周慎之激烈争吵",
            "急需用钱还赌债",
        ],
        personality="情绪化、爱演、容易说漏嘴、主动向玩家'提供线索'(但带私心)",
        memory=[],
        relationships={"周慎之": 50, "林婉": 0, "王总": -60, "陈伯": 40, "阿福": 30, "小张": 20},
        alive=True,
        suspicion_of_player=10,
    )


def _build_wangzong() -> NPCState:
    return NPCState(
        name="王总",
        public_role="周慎之的生意合伙人",
        hidden_goal="取回一张证明周慎之欠他巨款的借据原件",
        secrets=[
            "周慎之欠我一大笔钱",
            "借据藏在书房保险柜",
        ],
        personality="强势、商人嘴脸、用利益衡量一切、对玩家保持距离",
        memory=[],
        relationships={"周慎之": -20, "苏苏": -60, "林婉": 30, "陈伯": 10, "阿福": 20, "小张": 20},
        alive=True,
        suspicion_of_player=25,
    )


def _build_afu() -> NPCState:
    return NPCState(
        name="阿福",
        public_role="别墅厨师",
        hidden_goal="撇清关系,不想被卷入富人的纷争",
        secrets=[
            "深夜看到有人进了书房",
            "没看清是谁,但是个女人的身影",
        ],
        personality="老实、紧张、一问就慌、知道关键线索但不敢主动说",
        memory=[],
        relationships={"陈伯": 70, "林婉": 20, "苏苏": 30, "王总": 30, "小张": 30},
        alive=True,
        suspicion_of_player=5,
    )


def _build_xiaozhang() -> NPCState:
    return NPCState(
        name="小张",
        public_role="别墅安保",
        hidden_goal="隐瞒自己当晚睡岗、没巡逻的失职",
        secrets=[
            "当晚睡着了",
            "监控录像有一段空白是因为我没开机",
        ],
        personality="年轻、心虚、说谎技术差、被追问会越描越黑",
        memory=[],
        relationships={"陈伯": 50, "林婉": 10, "王总": 20, "苏苏": 10, "阿福": 30},
        alive=True,
        suspicion_of_player=15,
    )


def build_initial_world() -> WorldState:
    """构建完整的 6 NPC 初始 WorldState。"""
    return WorldState(
        scene=INITIAL_SCENE,
        phase=PHASE_DINNER,
        clock=0,
        player=PlayerState(location="大厅"),
        npcs={
            "陈伯": _build_chenbo(),
            "林婉": _build_linwan(),
            "苏苏": _build_susu(),
            "王总": _build_wangzong(),
            "阿福": _build_afu(),
            "小张": _build_xiaozhang(),
        },
    )
