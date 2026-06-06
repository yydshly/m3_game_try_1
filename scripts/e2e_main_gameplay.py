"""
scripts/e2e_main_gameplay.py — 主入口完整路径 E2E 冒烟测试

通过 HTTP API 跑通从新建游戏到结局的完整路径。
同时验证主要失败路径。

运行：
  python scripts/e2e_main_gameplay.py

特性：
  - 服务可用性检查
  - 必要时自动启动 web_main.py（Windows 兼容）
  - 健康等待（最多 30s）
  - 测试结束后自动清理自启动子进程
  - 清晰超时配置
  - accuse 步骤一次重试（防 LLM 偶发超时）
  - 失败时详细诊断信息

依赖：pip install requests
"""

from __future__ import annotations

import sys
import os
import time
import socket
import subprocess
import requests
from pathlib import Path

# 读取 config/server.toml 中的端口配置，支持 M3_GAME_BASE_URL 环境变量覆盖
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from game.server_config import load_server_config
    BASE_URL = os.getenv("M3_GAME_BASE_URL", load_server_config().browser_url)
except Exception:
    BASE_URL = os.getenv("M3_GAME_BASE_URL", "http://localhost:8000")

SERVER_STARTUP_TIMEOUT = 30   # seconds to wait for server to become available
SERVER_STARTUP_POLL = 0.5     # poll interval while waiting

# 是否由本脚本启动了服务器（用于决定是否在结束时杀进程）
_we_started_server = False
_server_process: subprocess.Popen | None = None

SESSION: str | None = None
FAILED: list[str] = []


# ── 服务器管理 ─────────────────────────────────────

def _is_port_open(host: str, port: int) -> bool:
    """检测端口是否已打开（服务可用）."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except socket.error:
        return False
    finally:
        sock.close()


def _wait_for_server(url: str, timeout: int = SERVER_STARTUP_TIMEOUT) -> bool:
    """轮询等待服务就绪，超时返回 False."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code < 500:  # any non-5xx means server is alive
                return True
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.RequestException):
            pass
        time.sleep(SERVER_STARTUP_POLL)
    return False


def _start_server() -> subprocess.Popen:
    """
    在项目根目录启动 web_main.py，返回 Popen 对象。
    兼容 Windows.
    """
    # 找 web_main.py 的绝对路径（脚本所在目录的父目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    server_script = os.path.join(project_root, "web_main.py")

    # 复用现有 PYTHONPATH 启动服务
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    proc = subprocess.Popen(
        [sys.executable, server_script],
        cwd=project_root,
        env=env,
        # Windows 下不创建控制台窗口
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def _stop_server(proc: subprocess.Popen) -> None:
    """安全关闭子进程（Windows 兼容）."""
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception:
        pass


def _ensure_server() -> None:
    """
    确保服务器在 BASE_URL 可用。
    - 已运行时：复用，不关闭
    - 未运行时：启动，等待就绪
    """
    global _we_started_server, _server_process

    port = int(BASE_URL.rsplit(":", 1)[-1])
    host = BASE_URL.rsplit("://", 1)[-1].rsplit(":", 1)[0]

    if _is_port_open(host, port):
        print(f"  [INFO] 服务已在运行: {BASE_URL}（复用现有服务，不关闭）")
        _we_started_server = False
        return

    print(f"  [INFO] 服务未运行，自动启动: python web_main.py")
    _we_started_server = True
    _server_process = _start_server()

    print(f"  [INFO] 等待服务就绪（最多 {SERVER_STARTUP_TIMEOUT}s）...")
    ready = _wait_for_server(BASE_URL, timeout=SERVER_STARTUP_TIMEOUT)
    if not ready:
        _stop_server(_server_process)
        print(f"  [FAIL] 服务启动超时（>{SERVER_STARTUP_TIMEOUT}s），请手动运行：")
        print(f"         python web_main.py")
        sys.exit(1)

    print(f"  [INFO] 服务已就绪")


def _cleanup_server() -> None:
    """如果由本脚本启动了服务器，则关闭它。必须在 finally 中调用。"""
    if _we_started_server and _server_process is not None:
        print(f"  [INFO] 关闭自动启动的服务进程 (pid={_server_process.pid})")
        _stop_server(_server_process)


# ── 工具函数 ──────────────────────────────────────

def log(label: str, msg: str) -> None:
    print(f"  [{label}] {msg}")


def PASS(step: str) -> None:
    print(f"  [PASS] {step}")


def FAIL(step: str, reason: str) -> None:
    print(f"  [FAIL] {step}: {reason}")
    FAILED.append(f"{step}: {reason}")


def _format_state(s: dict) -> str:
    """返回当前状态的简短描述，用于诊断输出."""
    return (
        f"phase={s.get('phase','?')} "
        f"clock={s.get('clock','?')} "
        f"loc={s.get('player_location','?')} "
        f"evidence={len(s.get('evidence_details',[]))}"
    )


# ── HTTP 层 ──────────────────────────────────────

def api_post(path: str, payload: dict, timeout: int = 30,
             retry: bool = False) -> requests.Response:
    """
    POST 到 API，返回 Response。
    retry=True 时，网络异常或超时时最多重试一次。
    失败时打印诊断信息并 sys.exit(1).
    """
    url = f"{BASE_URL}{path}"
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        return r
    except (requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.RequestException) as exc:
        if retry:
            log("WARN", f"请求失败（{exc}），重试一次…")
            try:
                r = requests.post(url, json=payload, timeout=timeout)
                return r
            except Exception:
                pass
        _print_request_failure(path, payload, str(exc))
        sys.exit(1)


def api_get(path: str, timeout: int = 10) -> requests.Response:
    """GET 请求，失败时打印诊断信息并退出."""
    url = f"{BASE_URL}{path}"
    try:
        return requests.get(url, timeout=timeout)
    except (requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.RequestException) as exc:
        _print_request_failure(path, {}, str(exc))
        sys.exit(1)


def _print_request_failure(path: str, payload: dict, error: str) -> None:
    """打印请求失败的详细信息."""
    print(f"  [FAIL] HTTP 请求失败")
    print(f"         URL: {BASE_URL}{path}")
    print(f"         Method: POST" if payload else f"         Method: GET")
    if payload:
        # 隐藏 session_id 避免日志过大
        safe_payload = {k: ("***" if k == "session_id" else v)
                        for k, v in payload.items()}
        print(f"         Payload: {safe_payload}")
    print(f"         Error: {error}")


# ── API 调用 ──────────────────────────────────────

def create_session() -> str:
    """新建游戏会话，返回 session_id."""
    r = api_post("/api/session", {"player_name": "E2E测试员"}, timeout=10)
    r.raise_for_status()
    d = r.json()
    sid = d["session_id"]
    log("session", f"新建 session: {sid}")
    return sid


def action(sid: str, type_: str, target=None, text=None,
           timeout: int = 30, retry: bool = False) -> dict:
    """
    发送动作请求，返回 JSON body (dict).
    retry=True 时，timeout 或网络错误时重试一次。
    """
    payload = {"session_id": sid, "type": type_}
    if target is not None:
        payload["target"] = target
    if text is not None:
        payload["text"] = text
    r = api_post("/api/action", payload, timeout=timeout, retry=retry)
    d = r.json()
    # 业务层错误（非 HTTP 400）打印诊断
    if r.status_code >= 400 or (not r.ok and d.get("ok") is False):
        s = d.get("state", {})
        print(f"  [DIAG] action={type_} target={target} status={r.status_code} "
              f"ok={d.get('ok')} error={d.get('error')} state={_format_state(s)}")
    return d


def get_state(sid: str) -> dict:
    """获取当前世界状态."""
    r = api_get(f"/api/state/{sid}", timeout=10)
    r.raise_for_status()
    return r.json()


def require_ok(d: dict, step: str) -> None:
    if not d.get("ok", False):
        s = d.get("state", {})
        FAIL(step, f"API ok=False: {d.get('error','?')} | {_format_state(s)}")


# ── 主流程测试 ─────────────────────────────────────

def test_initial_state(sid: str) -> None:
    """验证初始状态：phase=dinner, clock=0, location=大厅."""
    s = get_state(sid)
    checks = [
        (s["phase"] == "dinner",       f"phase 应为 dinner，实际 {s['phase']}"),
        (s["clock"] == 0,               f"clock 应为 0，实际 {s['clock']}"),
        (s["player_location"] == "大厅", f"location 应为 大厅，实际 {s['player_location']}"),
    ]
    for ok, msg in checks:
        if not ok:
            FAIL("初始状态", f"{msg} | {_format_state(s)}")
            return
    PASS("初始状态: dinner / clock=0 / 大厅")


def test_npc_tour(sid: str) -> dict:
    """
    按最优路径访问所有 NPC 并收集证据。
    返回 dict: talked (set), evidence (list).
    """
    # 格式: (action_type, target_or_NPC, unused, expected_player_location, expected_present_npcs_or_None)
    tour = [
        ("move",        "书房",   None, "书房",  ["陈伯", "林婉"]),
        ("talk",        "陈伯",   None, "书房",  None),
        ("talk",        "林婉",   None, "书房",  None),
        ("investigate", None,     None, "书房",  None),
        ("move",        "餐厅",   None, "餐厅",  ["王总", "苏苏"]),
        ("talk",        "王总",   None, "餐厅",  None),
        ("talk",        "苏苏",   None, "餐厅",  None),
        ("move",        "厨房",   None, "厨房",  ["阿福"]),
        ("talk",        "阿福",   None, "厨房",  None),
        ("move",        "保安室", None, "保安室", ["小张"]),
        ("talk",        "小张",   None, "保安室", None),
    ]

    talked = set()
    evidence = []

    for atype, target, _text, location, expected_npcs in tour:
        if atype == "talk":
            d = action(sid, atype, target=target, text="请说说昨晚的情况")
        else:
            d = action(sid, atype, target=target)

        require_ok(d, f"{atype} {target or ''}")

        s = d.get("state", {})
        cur_loc = (s.get("player_location") or "").strip()
        if cur_loc != location.strip():
            FAIL(f"位置检查 {atype} {target}", f"应在 {location}，实际 {cur_loc} | {_format_state(s)}")
            return {}

        present = s.get("current_location", {}).get("present_npcs", [])
        if expected_npcs and set(present) != set(expected_npcs):
            FAIL(f"在场人物 {atype} {target}", f"应在 {expected_npcs}，实际 {present}")

        for n in s.get("talked_npcs", []):
            talked.add(n)

        for ev in s.get("evidence_details", []):
            if ev["name"] not in evidence:
                evidence.append(ev["name"])

        log(f"{atype} {target or ''}", f"loc={cur_loc} talked={len(talked)} ev={len(evidence)}")

    PASS(f"NPC 巡游完成: talked={sorted(talked)} evidence={evidence}")
    return {"talked": talked, "evidence": evidence}


def test_dinner_to_investigation(sid: str) -> None:
    """验证 dinner → investigation 阶段转换（需 ≥5 个 talked_npcs）."""
    d = action(sid, "advance")
    require_ok(d, "advance (dinner→investigation)")
    s = d.get("state", {})
    phase = s.get("phase")
    if phase != "investigation":
        FAIL("dinner→investigation", f"phase 应为 investigation，实际 {phase} | {_format_state(s)}")
    else:
        PASS(f"阶段推进: dinner → investigation (clock={s.get('clock')})")


def test_investigation_to_confrontation(sid: str) -> None:
    """
    investigation 阶段：收集证据后推进，确认进入 confrontation.
    需要 ≥2 个 evidence 才能触发.
    """
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
        FAIL("investigation→confrontation", f"phase 应为 confrontation，实际 {phase} | {_format_state(s)}")
    else:
        PASS(f"阶段推进: investigation → confrontation (clock={s.get('clock')})")


def test_accuse_and_ending(sid: str) -> str | None:
    """
    confrontation 阶段：指认林婉，确认进入 ending，
    返回 ending_key（成功时），失败时返回 None.
    accuse 触发 DirectorAgent.judge (LLM)，设置 120s 超时 + 一次重试。
    """
    # accuse 是最终动作，超时/网络异常时重试一次（防 LLM 偶发慢速）
    d = action(sid, "accuse", target="林婉", timeout=120, retry=True)
    require_ok(d, "accuse 林婉")
    s = d.get("state", {})
    phase = s.get("phase")
    game_over = s.get("game_over", False)

    if phase != "ending":
        FAIL("指认→ending", f"phase 应为 ending，实际 {phase} | {_format_state(s)}")
        return None
    if not game_over:
        FAIL("指认→ending", f"game_over 应为 True | {_format_state(s)}")
        return None

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


# ── 失败路径测试 ────────────────────────────────────

def test_invalid_action_type(sid: str) -> None:
    """非法 action type 应返回 HTTP 400."""
    r = api_post("/api/action", {"session_id": sid, "type": "fly", "target": "某地"}, timeout=10)
    if r.status_code == 400:
        PASS("非法 action type → HTTP 400")
    else:
        FAIL("非法 action type", f"期望 HTTP 400，实际 HTTP {r.status_code}")


def test_accuse_before_confrontation(sid: str) -> None:
    """dinner 阶段指认应返回 HTTP 400."""
    r = api_post("/api/action", {"session_id": sid, "type": "accuse", "target": "陈伯"}, timeout=10)
    if r.status_code == 400:
        PASS("dinner 阶段指认 → HTTP 400")
    else:
        FAIL("dinner 阶段指认", f"期望 HTTP 400，实际 HTTP {r.status_code}")


def test_talk_absent_npc(sid: str) -> None:
    """盘问不在场 NPC 应返回 HTTP 400."""
    r = api_post("/api/action", {"session_id": sid, "type": "talk", "target": "陈伯"}, timeout=10)
    if r.status_code == 400:
        PASS("盘问不在场 NPC → HTTP 400")
    else:
        FAIL("盘问不在场 NPC", f"期望 HTTP 400，实际 HTTP {r.status_code}")


def test_available_actions_structure(sid: str) -> None:
    """验证 available_actions 存在、类型正确、字段完整."""
    s = get_state(sid)
    avail = s.get("available_actions")
    if avail is None:
        FAIL("available_actions", "字段缺失")
        return
    if not isinstance(avail, list):
        FAIL("available_actions", f"应为 list，实际 {type(avail)}")
        return
    for a in avail:
        for field in ("type", "label", "enabled"):
            if field not in a:
                FAIL("available_actions", f"缺少字段 {field}: {a}")
                return
    PASS(f"available_actions 结构正确 ({len(avail)} 个动作)")


def test_advance_rapid_call_risk(sid: str) -> None:
    """
    验证 advance 连续快速调用的风险。
    正常情况：每次 advance clock +1，phase 不会异常跳过。
    """
    # 用新 session 避免污染主流程 session
    sid2 = create_session()
    clock_values = []
    phase_values = []
    for i in range(5):
        d = action(sid2, "advance")
        s = d.get("state", {})
        clock_values.append(s.get("clock"))
        phase_values.append(s.get("phase"))

    expected = list(range(1, 6))
    if clock_values == expected:
        PASS(f"advance 连续调用 clock 序列正常: {clock_values}")
    else:
        FAIL("advance 连续调用", f"clock 序列异常: {clock_values}，期望 {expected}")

    if "ending" in phase_values:
        FAIL("advance 连续调用", f"phase 异常跳到 ending: {phase_values}")
    else:
        PASS(f"advance 连续调用 phase 序列正常（唯一值: {list(dict.fromkeys(phase_values))}）")


# ── 入口 ───────────────────────────────────────────

def main() -> int:
    global SESSION

    print("=" * 60)
    print("  主入口 E2E 冒烟测试")
    print("=" * 60)
    print(f"  目标服务器: {BASE_URL}")
    print()

    # 确保服务器就绪（自动启动或复用）
    print("[Step 0] 服务器可用性检查")
    _ensure_server()

    try:
        # ── 失败路径测试（独立 session）────────────
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

        # ── 主流程测试 ───────────────────────────
        print()
        print("[Step 1] 新建游戏 session")
        SESSION = create_session()

        print()
        print("[Step 2] 验证初始状态")
        test_initial_state(SESSION)

        print()
        print("[Step 3] NPC 巡游 (对话 6 NPC)")
        test_npc_tour(SESSION)

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
        print("[Step 7] ending_key 消费验证")
        if ending_key:
            PASS(f"ending_key 正确消费: {ending_key}")
        else:
            FAIL("ending_key 消费", "未获得有效 ending_key")

    finally:
        # 清理：只关闭本脚本启动的服务器
        _cleanup_server()

    # ── 总结 ───────────────────────────────────
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
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        print("  [ABORT] 用户中断")
        _cleanup_server()
        sys.exit(1)
