"""
game/agents.py — Agent 层

Phase 1 只实现 NPCDialogueAgent。
其余 3 个 Agent(NPCDecisionAgent / DirectorAgent / NarratorAgent)按 PLAN.md 顺序
在后续 Phase 中追加。

设计要点(见 docs/ARCHITECTURE.md 第 3、5 节):
- Agent 是无状态的。每次调用时从 WorldState 取该 NPC 的私有数据,拼成 prompt。
- 信息隔离铁律:NPCDialogueAgent 的 prompt 只放该 NPC 自己的 secrets / hidden_goal,
  绝不能拼入其它 NPC 的秘密或全局真相。
- Prompt 模板硬盘上,代码层 .format() 填充。禁止硬编码 prompt 文本到 .py。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from game.llm import LLMError, call_m3
from game.state import NPCState, WorldState

_PROMPT_DIR: Path = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=8)
def _load_prompt(name: str) -> str:
    """读取 prompts/<name>.txt 模板,缓存避免重复磁盘 I/O。"""
    path = _PROMPT_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def _format_memory(memory: list[str]) -> str:
    """把 NPC 的记忆列表格式化为 prompt 友好的文本。空记忆返回占位。"""
    if not memory:
        return "(无,这是你第一次和这位侦探说话)"
    # 旧→新依序列出,带行号便于 LLM 把握时序
    return "\n".join(f"{i + 1}. {m}" for i, m in enumerate(memory))


def _format_secrets(secrets: list[str]) -> str:
    """把秘密列表格式化为带圆点的多行文本。"""
    return "\n".join(f"- {s}" for s in secrets)


class NPCDialogueAgent:
    """单个 NPC 的对话 Agent。

    ─────────────────────────────────────────────────
    为什么这里需要 M3 而不是规则:
    NPC 要根据自己的性格 / 秘密 / 记忆 / 玩家这句话,即兴生成一段
    "听起来像这个人"的回应。这是典型的"语言生成 + 角色一致性"任务,
    不可能用 if/else 或查表枚举所有可能对话。
    ─────────────────────────────────────────────────
    """

    PROMPT_NAME: str = "npc_dialogue"
    # NPC 性格扮演需要一定温度,但不能太散
    TEMPERATURE: float = 0.8
    # 回应控制在 2-4 句话。注意 MiniMax-M3 必带 thinking 块且会吃 token 预算，
    # 必须给足额度，否则 thinking 占满后 text 回复被截断为空。
    MAX_TOKENS: int = 1200
    # 失败时的安全降级文案——保持沉默,不暴露任何东西
    FALLBACK_REPLY: str = "……(对方沉默了一下,没有回答。)"

    @classmethod
    def respond(
        cls,
        npc: NPCState,
        world: WorldState,
        player_message: str,
    ) -> str:
        """生成 NPC 的回应,并把对话写入该 NPC 的私有记忆。

        参数:
            npc: 要回应的 NPC(对象会被原地修改:memory 追加一条)
            world: 当前世界状态(只读取 scene)
            player_message: 玩家这次说的话

        返回:
            NPC 的回应文本。即使 M3 调用失败也会返回降级文案,不会抛异常。
        """
        # === 拼 prompt:严格只用该 NPC 自己的信息 ===
        # 这里是信息隔离的关键执行点,任何修改务必看一遍 ARCHITECTURE.md §5
        template = _load_prompt(cls.PROMPT_NAME)
        user_prompt = template.format(
            name=npc.name,
            public_role=npc.public_role,
            personality=npc.personality,
            secrets=_format_secrets(npc.secrets),
            hidden_goal=npc.hidden_goal,
            scene=world.scene,
            memory=_format_memory(npc.memory),
            suspicion=npc.suspicion_of_player,
            player_message=player_message,
        )
        system_prompt = (
            "你是一个完全沉浸在中国文字推理游戏中的真实角色。"
            "把自己当成这个人，用他的口吻和思维方式说话。"
            "直接输出对话，不要加旁白、引号、系统音或任何解释。"
        )

        try:
            reply = call_m3(
                system=system_prompt,
                user=user_prompt,
                purpose=f"npc_dialogue:{npc.name}",
                temperature=cls.TEMPERATURE,
                max_tokens=cls.MAX_TOKENS,
                thinking_enabled=False,  # 对话场景关闭 thinking:省 token + 避免推理过程输出
            )
        except LLMError as e:
            # 不让一次 M3 抽风崩掉整局游戏(AGENTS.md 代码规范)
            print(f"[llm warn] {npc.name} 的对话调用失败,使用降级回应: {e}")
            reply = cls.FALLBACK_REPLY

        # === 写回私有记忆 ===
        # Phase 1 用最朴素的"原文记录"。Phase 2 再做摘要压缩。
        npc.memory.append(f"侦探对我说:「{player_message}」 我回:「{reply}」")
        return reply


# ============================================================
# NarratorAgent — 场景叙事
# ============================================================

import game.rules as rules


class NarratorAgent:
    """
    每个时段开始时生成氛围描写。

    ─────────────────────────────────────────────────
    为什么这里需要 M3 而不是规则:
    氛围描写需要"文学感"和"临场感",用 if/else 拼出来的句子缺乏连贯性。
    根据当前时段+地点+事件,生成一段渲染紧张悬疑气氛的散文,
    是典型的语言生成任务。
    ─────────────────────────────────────────────────
    """

    PROMPT_NAME: str = "narrator"
    TEMPERATURE: float = 0.9
    MAX_TOKENS: int = 1200  # M3 thinking 占额度，需给足（见 NPCDialogueAgent 说明）
    FALLBACK: str = "暴风雨依旧在下，所有人各怀心事。"

    @classmethod
    def narrate(cls, world: WorldState) -> str:
        """
        生成并返回当前时段的氛围描写。
        不修改 world。
        """
        from game.rules import all_npc_locations, clock_name

        # 拼最近 3 条公共事件(按 clock 倒序取最新)
        recent = sorted(world.public_events, key=lambda e: e.clock, reverse=True)[:3]
        if recent:
            events_text = "\n".join(f"- {e.description}" for e in reversed(recent))
        else:
            events_text = "(尚无公共事件)"

        # NPC 位置概览
        locs = all_npc_locations(world)
        npc_locs_text = "\n".join(f"- {name}: {loc}" for name, loc in locs.items())

        template = _load_prompt(cls.PROMPT_NAME)
        user_prompt = template.format(
            clock_name=clock_name(world.clock),
            clock=world.clock,
            scene=world.scene,
            npc_locations=npc_locs_text,
            recent_events=events_text,
        )
        system_prompt = (
            "你是一个文字推理游戏的旁白。严格以悬疑氛围风格描写场景。"
            "只输出描写文字,不要加旁白或解释。"
        )

        try:
            text = call_m3(
                system=system_prompt,
                user=user_prompt,
                purpose="narrator",
                temperature=cls.TEMPERATURE,
                max_tokens=cls.MAX_TOKENS,
                thinking_enabled=False,
            )
        except LLMError as e:
            print(f"[llm warn] NarratorAgent 调用失败,使用降级描写: {e}")
            text = cls.FALLBACK

        return text


# ============================================================
# NPCDecisionAgent — 重大决策
# ============================================================


class NPCDecisionAgent:
    """
    NPC 在关键时刻的自主决策。

    ─────────────────────────────────────────────────
    为什么这里需要 M3 而不是规则:
    NPC 的"重大行动"需要综合其性格、隐藏目标、当前局势来判断，
    不是简单 if/else 能枚举的。例如林婉在"可能被暴露"时可以选择：
    - 销毁证据
    - 转移嫌疑
    - 主动出击搅浑水
    - 按兵不动等待时机
    这种多维度判断需要 M3 的推理能力。
    ─────────────────────────────────────────────────
    """

    PROMPT_NAME: str = "npc_decision"
    TEMPERATURE: float = 0.5   # 决策需要稳定，不宜太高
    MAX_TOKENS: int = 1500  # JSON 输出 + M3 thinking 占额度，需给足
    THINKING_ENABLED: bool = True  # 决策场景开启 thinking 要质量

    # Phase 3 林婉的预设可行动作
    LINWAN_ACTIONS: list[str] = [
        "销毁证据：回到自己房间，烧毁病历笔记",
        "转移嫌疑：主动找某人说其他人的坏话",
        "按兵不动：假装不知道，保持正常行为",
        "主动出击：先发制人，在公开场合提出某个质疑转移注意力",
    ]

    @classmethod
    def decide(cls, npc: NPCState, world: WorldState) -> dict:
        """
        生成 NPC 的决策 JSON: {action, target, reason}。

        失败时返回 {"action": "wait", "target": "", "reason": "无法决策"}。
        """
        import game.rules as rules

        # 构建局势描述
        locs = rules.all_npc_locations(world)
        current_loc = locs.get(npc.name, "未知")
        inventory_list = ", ".join(world.player.inventory) or "无"

        # 林婉特殊处理：预设决策选项
        if npc.name == "林婉":
            available_actions = "\n".join(
                f"- {a}" for a in cls.LINWAN_ACTIONS
            )
        else:
            available_actions = "- 等待观望\n- 采取行动（描述你想做什么）"

        template = _load_prompt(cls.PROMPT_NAME)
        user_prompt = template.format(
            name=npc.name,
            public_role=npc.public_role,
            personality=npc.personality,
            hidden_goal=npc.hidden_goal,
            secrets="\n".join(f"- {s}" for s in npc.secrets),
            current_situation=(
                f"当前时段: {rules.clock_name(world.clock)}\n"
                f"当前地点: {current_loc}\n"
                f"玩家已获得证据: {inventory_list}\n"
                f"玩家已对话NPC数: {len(world.player.revealed_to)}\n"
                f"当前阶段: {world.phase}"
            ),
            memory=(
                "\n".join(f"- {m}" for m in npc.memory[-5:])
                if npc.memory else "(无记忆)"
            ),
            available_actions=available_actions,
        )
        system_prompt = (
            "你是一个文字推理游戏中的 NPC，在关键时刻做出决策。"
            "严格按 JSON 格式返回，不要任何其他文字。"
        )

        try:
            result_text = call_m3(
                system=system_prompt,
                user=user_prompt,
                purpose=f"npc_decision:{npc.name}",
                temperature=cls.TEMPERATURE,
                max_tokens=cls.MAX_TOKENS,
                thinking_enabled=cls.THINKING_ENABLED,
            )
            decision = cls._parse_decision(result_text)
            return decision
        except LLMError as e:
            print(f"[llm warn] NPCDecisionAgent({npc.name}) 调用失败: {e}")
            return {"action": "wait", "target": "", "reason": "无法决策"}

    @staticmethod
    def _parse_decision(text: str) -> dict:
        """解析 M3 返回的 JSON 决策。失败返回默认。"""
        import json, re

        text = text.strip()
        # 去掉可能的 markdown 包裹
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"```$", "", text)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 对象
            match = re.search(r"\{[^{}]*\}", text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return {"action": "wait", "target": "", "reason": "解析失败"}


# ============================================================
# DirectorAgent — 主控裁判
# ============================================================


class DirectorAgent:
    """
    主控裁判：阶段推进最终判断、结局生成。

    ─────────────────────────────────────────────────
    为什么这里需要 M3 而不是规则:
    结局叙事需要综合整个游戏过程,生成一段连贯、有戏剧张力的故事收尾。
    这不是查表能实现的——需要理解证据链、各角色动机、事件全貌,
    然后组织成一段令人信服的结局文本。
    ─────────────────────────────────────────────────
    """

    PROMPT_NAME: str = "director"
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000  # 结局生成较长 + M3 thinking 占额度，需给足
    THINKING_ENABLED: bool = True

    @classmethod
    def judge(
        cls,
        world: WorldState,
        player_accusation: str | None = None,
    ) -> dict:
        """
        裁判结局。

        参数:
            world: 当前世界状态
            player_accusation: 玩家指认的嫌疑人名字,None 表示未指认

        返回结局 JSON:
            {
              "verdict": str,      # 结局类型
              "summary": str,      # 结局叙述
              "culprit": str,      # 真凶
              "innocent": list,    # 无辜者
              "game_over": bool
            }
        """
        import game.rules as rules

        # 拼装局势摘要
        evidence_text = ", ".join(world.player.inventory) or "无"
        talked_text = ", ".join(world.player.revealed_to.keys()) or "无"
        events_text = "\n".join(
            f"- {e.description}" for e in world.public_events[-10:]
        ) or "无"

        template = _load_prompt(cls.PROMPT_NAME)
        user_prompt = template.format(
            phase=world.phase,
            clock_name=rules.clock_name(world.clock),
            clock=world.clock,
            evidence=evidence_text,
            talked_npcs=talked_text,
            public_events=events_text,
        )
        system_prompt = (
            "你是一个文字推理游戏的主控裁判。严格按 JSON 格式返回结局,不要任何其他文字。"
        )

        try:
            result_text = call_m3(
                system=system_prompt,
                user=user_prompt,
                purpose="director:judge",
                temperature=cls.TEMPERATURE,
                max_tokens=cls.MAX_TOKENS,
                thinking_enabled=cls.THINKING_ENABLED,
            )
            return cls._parse_judgment(result_text, player_accusation)
        except LLMError as e:
            print(f"[llm warn] DirectorAgent 调用失败: {e}")
            return cls._fallback_judgment(player_accusation is not None)

    @classmethod
    def _parse_judgment(cls, text: str, accusation: str | None) -> dict:
        """解析 M3 返回的结局 JSON。"""
        import json, re

        text = text.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"```$", "", text)
        text = text.strip()

        try:
            result = json.loads(text)
            # 验证必需字段
            for field in ("verdict", "summary", "culprit", "innocent", "game_over"):
                if field not in result:
                    raise ValueError(f"缺少字段: {field}")
            return result
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[warn] 结局 JSON 解析失败({e}),使用默认结局")
            return cls._fallback_judgment(accusation is not None)

    @staticmethod
    def _fallback_judgment(did_accuse: bool) -> dict:
        """JSON 解析失败时的降级结局。"""
        if did_accuse:
            return {
                "verdict": "真凶落网",
                "summary": (
                    "林婉在证据面前无法自圆其说,承认了一切。 "
                    "暴风雨渐歇,渡船缓缓驶来。 "
                    "谜案终于水落石出。"
                ),
                "culprit": "林婉",
                "innocent": ["陈伯", "苏苏", "王总", "阿福", "小张"],
                "game_over": True,
            }
        else:
            return {
                "verdict": "真凶逃脱",
                "summary": (
                    "时间已到,渡船靠岸。 "
                    "众人匆匆离岛,林婉带着她的秘密消失在人群中。 "
                    "谜案永无答案。"
                ),
                "culprit": "林婉",
                "innocent": ["陈伯", "苏苏", "王总", "阿福", "小张"],
                "game_over": True,
            }
