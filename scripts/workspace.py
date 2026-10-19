#!/usr/bin/env python3
"""
The workspace: several projects on a forge, one MANAGEMENT repo and N CODER repos (ADR 0013).

    python3 scripts/workspace.py init <dir> --org X [--forge github] [--name N] [--repo X/management] [--local] [--apply]
    python3 scripts/workspace.py add <id> --repo R [--dir D] [--profile P] [--agent claude-code] [--forge gitlab] [--create] [--local] [--apply]
    python3 scripts/workspace.py epic "<title>" --child <project>:"<task>" [--child …] [--milestone M] [--goal G] [--apply]
    python3 scripts/workspace.py dispatch <n> [--apply]
    python3 scripts/workspace.py status [<n> …] [--apply]
    python3 scripts/workspace.py wiki [--apply]
    python3 scripts/workspace.py check

The management repo (this `workspace.json`) holds the epics, the milestones, the portfolio board,
the wiki and the ORCHESTRATOR queue (Hermes). It has no code. Each coder has its repo, its board,
its queue and its agent (Claude Code or Hermes), with its own harness. What ties them is the epic:
a parent issue in management with a checklist of children, and one child issue per line in the
coder's repo, linked to the parent (plugin/harness/forge.py).

  init      the management skeleton: workspace.json, the orchestrator AGENTS.md, wiki/, the
            roadmap, the epic template and the harness installed; in the forge, the repo, the
            milestones and the board (`--local`: only the files).
  add       a coder: registers it, installs the harness in `--dir` with its profile, its forge and
            its agent as `loop.agentCommand`, and creates its board (`--create`: the repo too).
  epic      an epic in the management repo: its checklist of children (`--child project:task`), its
            milestone, on the portfolio board.
  dispatch  the children of epic `<n>` not yet out: one issue per line in its repo, linked to the
            parent, queued in the coder's loop (`[issue: <repo>#<n>]`).
  status    each epic's checklist from the forge: `[x]` closed, `[!]` what the coder's loop
            escalated to a human.
  wiki      regenerates wiki/Proyectos.md from workspace.json and pushes wiki/ to the wiki repo.
  check     no network: workspace.json and every forge against their schemas, each forge with its
            examples, each operation classified by its integration, the forge's pipeline and a
            dispatch end to end against the simulated forge. A gate signal.

DRY-RUN by default (P9): READS go to the real forge (the plan comes out with the real epic) and
what writes is printed and simulated. `--apply` publishes. `--simulated`: everything against the
toy forge, no network. The loop never publishes (P13): with `--apply` a human runs or approves this
(`terminal.ask` rule `workspace-publica`).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent  # the harness repo (or an installed copy)
PLANT = HOME / "plantillas"
MANAGEMENT = PLANT / "workspace" / "management"
WS_SCHEMA = PLANT / "workspace" / "workspace.schema.json"
FORGE_SCHEMA = PLANT / "forges" / "forge.schema.json"
WS = "workspace.json"
sys.path.insert(0, str(HOME / "plugin"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import forge as fg  # noqa: E402
from harness import integ as nucleo  # noqa: E402
import schema_check  # noqa: E402

SIGNAL = {"name": "workspace (manifest and forges)", "command": ["python3", ".hermes/harness/scripts/workspace.py", "check"],
          "why": "a workspace.json naming a project, a forge or an agent that does not exist, or a forge whose command is no longer "
                 "what its integration classifies, fails only when dispatching, with half the children already published"}


def _json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def forges() -> dict[str, dict]:
    return {f.stem: _json(f) for f in sorted((PLANT / "forges").glob("*.json")) if not f.name.endswith(".schema.json")}


def integrations() -> dict[str, dict]:
    return {f.stem: _json(f) for f in sorted((PLANT / "integraciones").glob("*.json"))}


def find_ws(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / WS).is_file():
            return d
    return None


def read_ws(d: Path) -> dict:
    return _json(d / WS)


def write_ws(d: Path, ws: dict) -> None:
    (d / WS).write_text(json.dumps(ws, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def projects(ws: dict) -> dict[str, dict]:
    return {p["id"]: p for p in ws.get("projects") or [] if isinstance(p, dict) and p.get("id")}


def forge_of(ws: dict, p: dict | None = None) -> dict:
    fid = (p or {}).get("forge") or ws.get("forge") or "github"
    m = forges().get(fid)
    if m is None:
        raise fg.ForgeError(f"forge `{fid}` does not exist (plantillas/forges/)")
    return m


def by_repo(ws: dict, repo: str) -> dict | None:
    if (ws.get("management") or {}).get("repo") == repo:
        return ws["management"]
    return next((p for p in projects(ws).values() if p.get("repo") == repo), None)


def to_forge(m: dict, text: str) -> str:
    """Azure stores the description as HTML: each line break, a `<br>`."""
    br = m.get("lineBreak")
    return text.replace("\n", br) if br else text


def from_forge(m: dict, text: str) -> str:
    br = m.get("lineBreak")
    return text.replace(br, "\n") if br else text


def ws_problems(ws: dict) -> list[str]:
    """The schema first; then what it cannot say: forges, agents and profiles that exist, unique ids,
    and no coder on the management repo."""
    out = [f"{WS} {e}" for e in schema_check.validate(ws, _json(WS_SCHEMA))]
    fs = forges()
    agents = ws.get("agents") or {}
    if ws.get("forge") not in fs:
        out.append(f"`forge` {ws.get('forge')!r} is not one of {', '.join(fs)}")
    m = ws.get("management") or {}
    if m.get("agent") and m["agent"] not in agents:
        out.append(f"management.agent `{m['agent']}` is not in `agents`")
    seen = set()
    for i, p in enumerate(ws.get("projects") or []):
        where = f"projects[{i}] ({p.get('id')})"
        if p.get("id") in seen:
            out.append(f"{where}: repeated `id`")
        seen.add(p.get("id"))
        if p.get("repo") and p.get("repo") == m.get("repo"):
            out.append(f"{where}: it is the management repo: code does not go there")
        if p.get("forge") and p["forge"] not in fs:
            out.append(f"{where}: forge `{p['forge']}` does not exist")
        if p.get("agent") and p["agent"] not in agents:
            out.append(f"{where}: agent `{p['agent']}` is not in `agents`")
        if p.get("profile") and not (PLANT / "perfiles" / f"{p['profile']}.json").is_file():
            out.append(f"{where}: profile `{p['profile']}` does not exist")
    for name, argv in agents.items():
        if not any("{prompt}" in str(a) for a in argv or []):
            out.append(f"agents.{name}: argv without `{{prompt}}`: the loop would have no way to pass it the task")
    return out


# ── running against the forge ────────────────────────────────────────────────

class SimulatedForge:
    """The toy forge: issues, bodies and links in memory. It answers in the SAME shape as the real
    CLI (`simulated` in the manifest), so what reads the output is tested the same way."""

    def __init__(self):
        self.issues: dict[tuple[str, str], dict] = {}
        self.links: list[tuple[str, str]] = []
        self._count: dict[str, int] = {}

    def _next(self, key: str) -> int:
        self._count[key] = self._count.get(key, 0) + 1
        return self._count[key]

    def knows(self, vars_: dict) -> bool:
        return (vars_.get("repo", ""), str(vars_.get("n", ""))) in self.issues

    @staticmethod
    def raw(m: dict, state: str) -> str:
        return next((k for k, v in (m.get("states") or {}).items() if v == state), state)

    def seed(self, m: dict, repo: str, body: str, n: str | None = None) -> str:
        n = str(n or self._next(repo))
        self.issues[(repo, n)] = {"body": body, "raw": self.raw(m, "open")}
        return n

    def close(self, m: dict, repo: str, n: str) -> None:
        self.issues[(repo, str(n))]["raw"] = self.raw(m, "closed")

    def do(self, m: dict, op: str, vars_: dict) -> str:
        repo, n = vars_.get("repo", ""), str(vars_.get("n", ""))
        val: dict = {"repo": repo, "n": n}
        if op == "issue.create":
            val["n"] = self.seed(m, repo, vars_.get("body", ""))
        elif op in ("issue.state", "issue.body", "issue.id"):
            i = self.issues.get((repo, n))
            if i is None:
                raise fg.ForgeError(f"the simulated forge has no {repo}#{n}")
            val.update(raw=i["raw"], body=i["body"], id=f"9{n}", json_body=json.dumps({"description": i["body"]}))
        elif op == "issue.edit":
            self.issues.setdefault((repo, n), {"raw": self.raw(m, "open")})["body"] = vars_.get("body", "")
        elif op == "issue.link":
            self.links.append((f"{vars_.get('parent_repo')}#{vars_.get('parent_n')}", str(vars_.get("child_id") or n)))
        elif op == "board.create":
            val["n"] = self._next("board")
        return fg.fill((m.get("simulated") or {}).get(op, ""), val)


class Runner:
    """`apply`: everything for real · `dry`: reads for real, the rest simulated · `simulated`: nothing goes out."""

    def __init__(self, mode: str, sim: SimulatedForge | None = None, log=print):
        self.mode, self.sim, self.log = mode, sim or SimulatedForge(), log

    def __call__(self, m: dict, op: str, vars_: dict) -> str | None:
        argv = fg.command(m, op, vars_)
        if argv is None:
            return None
        reads = (m.get("classes") or {}).get(op) == "read"
        if self.mode == "apply" or (self.mode == "dry" and reads and not self.sim.knows(vars_)):
            self.log(f"  $ {shlex.join(argv)}")
            try:
                p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            except FileNotFoundError:
                raise fg.ForgeError(f"`{argv[0]}` is not on the PATH. Setup of forge `{m['id']}`: "
                                    + " · ".join(m.get("setup") or [])) from None
            if p.returncode != 0:
                raise fg.ForgeError(f"`{shlex.join(argv[:4])} …` exited {p.returncode}: {(p.stderr or p.stdout).strip()[:400]}")
            if self.mode == "dry" and op == "issue.body":
                # What was read for real, the simulation remembers: what follows (editing it) is dry.
                self.sim.seed(m, vars_.get("repo", ""), fg.read_output(m, op, p.stdout), vars_.get("n"))
            return p.stdout
        self.log(f"  {'·' if reads else '+'} {shlex.join(argv)}")
        return self.sim.do(m, op, vars_)


def repo_vars(repo: str, **extra) -> dict:
    return {**fg.repo_vars(repo), **{k: v for k, v in extra.items() if v is not None}}


# ── dispatch and status (what `check` tests against the simulated forge) ────

def read_body(ws: dict, n, run: Runner) -> str:
    m = forge_of(ws)
    return from_forge(m, fg.read_output(m, "issue.body", run(m, "issue.body", repo_vars(ws["management"]["repo"], n=n)) or ""))


def queue_line(title: str, r: str) -> str:
    return f"- [ ] {title} [issue: {r}]"


def queue_of(ws_dir: Path | None, p: dict) -> Path | None:
    if ws_dir is None or not p.get("dir"):
        return None
    q = (ws_dir / p["dir"]).resolve() / ".hermes" / "loop" / "tasks.md"
    return q if q.is_file() else None


def dispatch(ws: dict, n, run: Runner, ws_dir: Path | None = None, write: bool = False, log=print) -> tuple[list[str], list[str]]:
    """(references created, problems). All or nothing: with one problem in the checklist, none is created."""
    mg, management = forge_of(ws), ws["management"]["repo"]
    body = read_body(ws, n, run)
    create, problems = fg.plan_dispatch(body, projects(ws))
    if not fg.children(body):
        problems.append(f"epic {management}#{n} has no checklist of children (`- [ ] [<project>] <title>`)")
    if problems or not create:
        return [], problems
    parent = fg.ref(management, n)
    parent_vars = repo_vars(management)
    created = []
    for c in create:
        p = projects(ws)[c["project"]]
        m = forge_of(ws, p)
        out = run(m, "issue.create", repo_vars(p["repo"], title=c["title"], body=to_forge(m, fg.child_body(m, parent)), label=p.get("label")))
        nc = fg.read_output(m, "issue.create", out or "")
        r = fg.ref(p["repo"], nc)
        if m["id"] == mg["id"]:
            # The native link, only within the same forge. Across forges the child's body carries it.
            cid = fg.read_output(m, "issue.id", run(m, "issue.id", repo_vars(p["repo"], n=nc)) or "") if (m.get("ops") or {}).get("issue.id") else nc
            run(m, "issue.link", repo_vars(p["repo"], n=nc, child_id=cid, parent_repo=management, parent_n=n,
                                           parent_repo_enc=parent_vars["repo_enc"]))
        else:
            log(f"  · {r} is on another forge ({m['id']}): its link to {parent} lives in the issue body")
        url = (out or "").strip()
        if p.get("board") and url.startswith("http"):
            run(m, "board.add", repo_vars(p["repo"], board=p["board"], url=url))
        body = fg.with_ref(body, c["line"], r)
        q = queue_of(ws_dir, p)
        if q is not None:
            log(f"  + {q}: {queue_line(c['title'], r)}")
            if write:
                text = q.read_text(encoding="utf-8")
                q.write_text(text + ("" if text.endswith("\n") else "\n") + queue_line(c["title"], r) + "\n", encoding="utf-8")
        created.append(r)
    run(mg, "issue.edit", repo_vars(management, n=n, body=to_forge(mg, body)))
    return created, []


def escalated(ws_dir: Path | None, p: dict | None, r: str) -> bool:
    q = queue_of(ws_dir, p or {})
    if q is None:
        return False
    return re.search(rf"^\s*[-*]\s+\[!\].*\[issue:\s*{re.escape(r)}\]", q.read_text(encoding="utf-8"), re.M) is not None


def status(ws: dict, n, run: Runner, ws_dir: Path | None = None) -> tuple[dict[str, str], bool]:
    """({reference: mark}, changed). Closed in the forge → `x`; escalated in the queue → `!`; else ` `."""
    mg = forge_of(ws)
    body = read_body(ws, n, run)
    marks = {}
    for c in fg.children(body):
        if not c["ref"]:
            continue
        repo, nc = fg.split_ref(c["ref"])
        p = by_repo(ws, repo)
        m = forge_of(ws, p)
        st = fg.state(m, fg.read_output(m, "issue.state", run(m, "issue.state", repo_vars(repo, n=nc)) or ""))
        marks[c["ref"]] = "x" if st == "closed" else ("!" if escalated(ws_dir, p, c["ref"]) else " ")
    new = fg.with_marks(body, marks)
    if new != body:
        run(mg, "issue.edit", repo_vars(ws["management"]["repo"], n=n, body=to_forge(mg, new)))
    return marks, new != body


def epic_body(goal: str, children_: list[tuple[str, str]]) -> str:
    """The epic from its template (plantillas/workspace/management/epic.md) with its children."""
    template = (MANAGEMENT / "epic.md").read_text(encoding="utf-8")
    lines = "\n".join(f"- [ ] [{p}] {t}" for p, t in children_)
    body = re.sub(r"(?m)^- \[ \] \[[\w.-]+\] .*$", lambda _: lines, template, count=1)
    if goal:
        body = re.sub(r"(## Objetivo\n\n).*?\n\n", lambda mm: mm.group(1) + goal.strip() + "\n\n", body, count=1, flags=re.S)
    return body


def create_epic(ws: dict, title: str, children_: list[tuple[str, str]], run: Runner, milestone: str | None = None,
                goal: str = "") -> tuple[str, list[str]]:
    """(the epic's reference, problems). Every child names a coder of the workspace, or nothing is created."""
    body = epic_body(goal, children_)
    _, problems = fg.plan_dispatch(body, projects(ws))
    if not children_:
        problems.append("an epic needs at least one child (`--child <project>:<task>`)")
    if problems:
        return "", problems
    m, repo = forge_of(ws), ws["management"]["repo"]
    out = run(m, "issue.create", repo_vars(repo, title=title, body=to_forge(m, body), milestone=milestone))
    n = fg.read_output(m, "issue.create", out or "")
    url = (out or "").strip()
    if ws["management"].get("board") and url.startswith("http"):
        run(m, "board.add", repo_vars(repo, board=ws["management"]["board"], url=url))
    return fg.ref(repo, n), []


# ── check: no network ────────────────────────────────────────────────────────

def _rehearsal_repos(m: dict) -> tuple[str, str, str]:
    """`repoParts`: how many parts a repo name has on this forge (Azure: org/project/repo)."""
    base = "/".join(["org", "plat", "x"][-int(m.get("repoParts") or 2):][:-1])
    return f"{base}/management", f"{base}/api", f"{base}/web"


def rehearsal(m: dict) -> list[str]:
    """An epic end to end against the simulated forge: create it, dispatch, do not repeat, close a child, mark."""
    out = []
    rg, ra, rw = _rehearsal_repos(m)
    ws = {"name": "rehearsal", "forge": m["id"], "management": {"repo": rg, "agent": "hermes"}, "epics": [],
          "projects": [{"id": "api", "repo": ra, "role": "coder"}, {"id": "web", "repo": rw, "role": "coder"}],
          "agents": {"hermes": ["hermes", "chat", "-q", "{prompt}"]}}
    sim = SimulatedForge()
    run = Runner("simulated", sim, log=lambda *_: None)
    try:
        epic, problems = create_epic(ws, "Login", [("api", "Login"), ("web", "Login screen")], run)
        if problems or not epic:
            return [f"creating an epic with 2 children failed: {'; '.join(problems)}"]
        n = fg.split_ref(epic)[1]
        created, problems = dispatch(ws, n, run, log=lambda *_: None)
        if problems or len(created) != 2:
            return [f"dispatching an epic with 2 children created {len(created)} ({'; '.join(problems)})"]
        body = read_body(ws, n, run)
        if [c["ref"] for c in fg.children(body)] != created:
            out.append("the epic was not left with each child's reference")
        if (m.get("ops") or {}).get("issue.link") and len(sim.links) != 2:
            out.append(f"the native parent→child link was made {len(sim.links)} times, not 2")
        for r in created:
            repo, nc = fg.split_ref(r)
            if fg.ref(rg, n) not in from_forge(m, sim.issues[(repo, nc)]["body"]):
                out.append(f"child {r} does not name its parent in the body")
        again, problems = dispatch(ws, n, run, log=lambda *_: None)
        if again:
            out.append(f"dispatching the same epic twice created {again} again")
        sim.close(m, *fg.split_ref(created[0]))
        marks, changed = status(ws, n, run)
        if marks != {created[0]: "x", created[1]: " "} or not changed:
            out.append(f"status: with the first child closed, the marks are {marks}")
        if [c["mark"] for c in fg.children(read_body(ws, n, run))] != ["x", " "]:
            out.append("status did not leave the epic's checklist marked in the forge")
        before = len(sim.issues)
        _, problems = create_epic(ws, "Other", [("api", "One"), ("nobody", "Two")], run)
        n2 = sim.seed(m, rg, to_forge(m, "- [ ] [api] One\n- [ ] [nobody] Two\n"))
        created, problems2 = dispatch(ws, n2, run, log=lambda *_: None)
        if not problems or created or not problems2 or len(sim.issues) != before + 1:
            out.append("an epic with a project that does not exist was created or dispatched halfway: it has to be all or nothing")
    except fg.ForgeError as e:
        out.append(f"the rehearsal crashes: {e}")
    return out


def forge_problems(m: dict, integ: dict | None) -> list[str]:
    """A forge: its schema, its shape, its examples, each operation classified by its integration as the
    forge says, its pipeline and an epic end to end against the simulated forge."""
    shape = [f"schema {e}" for e in schema_check.validate(m, _json(FORGE_SCHEMA))] + fg.manifest_problems(m)
    if shape:
        return shape
    out = []
    for ex in m.get("examples") or []:
        try:
            did = fg.command(m, ex["op"], ex.get("vars") or {})
        except fg.ForgeError as e:
            did = str(e)
        if did != ex.get("argv"):
            out.append(f"example `{ex['op']}` ({ex.get('why')}): builds {did}, expected {ex.get('argv')}")
    if integ is None:
        out.append(f"integration `{m.get('integration')}` is not in plantillas/integraciones: nothing governs its CLI")
    for op, template in (m.get("ops") or {}).items():
        if template is None or integ is None:
            continue
        text = " ".join(fg.command(m, op, {v: "v1" for v in fg.variables(template)}) or [])
        expected = (m.get("classes") or {}).get(op)
        got = nucleo.clase(integ, text)
        if not re.search(integ.get("command") or "(?!)", text):
            out.append(f"`{op}` ({text}) is not a command of integration `{integ.get('id')}`")
        elif got == "deny":
            out.append(f"`{op}` is a `deny` class for its integration: the agent could never run it")
        elif got != expected:
            out.append(f"`{op}`: the integration classifies it `{got}` and the forge declares `{expected}`")
    has_gate = False
    for e in m.get("ci") or []:
        f = PLANT / e["from"]
        if not f.is_file():
            out.append(f"pipeline `{e['from']}` does not exist")
            continue
        text = f.read_text(encoding="utf-8")
        has_gate = has_gate or "scripts/gate.py" in text
        if e.get("runner") == "drift" and "scripts/drift.py" not in text:
            out.append(f"`{e['from']}` is the drift runner and does not run drift.py: switched on and nobody runs it")
    if not has_gate:
        out.append("no pipeline of the forge runs the gate: green CI without the gate is CI that does not look")
    return out + [f"rehearsal: {e}" for e in rehearsal(m)]


def all_forge_problems() -> list[str]:
    ints = integrations()
    return [f"{fid}: {e}" for fid, m in forges().items() for e in forge_problems(m, ints.get(m.get("integration") or ""))]


def repo_config(d: Path) -> dict | None:
    try:
        return _json(d / ".hermes" / "harness.config.json")
    except (OSError, ValueError):
        return None


def management_problems(ws_dir: Path) -> list[str]:
    """The management repo is not a code target: its config declares no stack code."""
    cfg = repo_config(ws_dir)
    if cfg is None or (cfg.get("workspace") or {}).get("role") != "management":
        return []
    own = set(_json(MANAGEMENT / "profile.json").get("codeExtensions") or [])
    others = sorted(set((cfg.get("gate") or {}).get("codeExtensions") or []) - own)
    if others:
        return [f"the management repo config declares stack code ({', '.join(others)}): code goes to a coder"]
    return []


# ── commands ─────────────────────────────────────────────────────────────────

def _install(d: Path, profile: str | None, forge: str, adjust, own: dict[Path, str], apply: bool) -> int:
    """The usual installer (install.plan), with the workspace's own files first and the config
    adjusted. It never overwrites."""
    import install as ins

    items = [(a, dst, src) for a, dst, src in ins.plan(d, profile, False, forge) if dst not in own]
    for a, dst, src in items:
        if isinstance(src, dict) and dst == d / ".hermes" / "harness.config.json":
            adjust(src)
    every = [("=" if dst.exists() else "+", dst, text) for dst, text in own.items()] + items
    for a, dst, _ in every:
        if "/.hermes/harness/" not in dst.as_posix():
            print(f"{a}  {os.path.relpath(dst, d)}")
    code = sum(1 for a, dst, _ in every if a == "+" and "/.hermes/harness/" in dst.as_posix())
    print(f"+  .hermes/harness/  ({code} harness files)")
    if apply:
        for a, dst, src in every:
            if a == "=":
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(src, dict):
                dst.write_text(json.dumps(src, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            elif isinstance(src, str):
                dst.write_text(src, encoding="utf-8")
            else:
                shutil.copy2(src, dst)
                if dst.parent.name == ".githooks":
                    dst.chmod(0o755)
    return sum(1 for a, *_ in every if a != "=")


def management_agents(name: str) -> str:
    base = (PLANT / "AGENTS.md").read_text(encoding="utf-8")
    own = (MANAGEMENT / "AGENTS-management.md").read_text(encoding="utf-8").replace("{workspace}", name)
    new = re.sub(r"(## Qué es este repo\n\n)<!--[^>]*-->\n", lambda mm: mm.group(1) + own, base, count=1)
    return new if new != base else base + "\n## El proyecto de gestión\n\n" + own


def projects_md(ws: dict) -> str:
    """wiki/Proyectos.md (a Spanish doc page) from workspace.json."""
    rows = [f"| gestión | `{ws['management']['repo']}` | {ws.get('forge')} | {ws['management'].get('agent') or '—'} | "
            f"{ws['management'].get('board') or '—'} |"]
    for p in ws.get("projects") or []:
        rows.append(f"| {p['id']} | `{p['repo']}` | {p.get('forge') or ws.get('forge')} | {p.get('agent') or '—'} | "
                    f"{p.get('board') or '—'} |")
    return ("# Proyectos\n\nLo regenera `workspace.py wiki` desde `workspace.json`: no se edita a mano.\n\n"
            "| Proyecto | Repo | Forja | Agente | Tablero |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n")


def cmd_init(a, run: Runner, apply: bool) -> int:
    d = Path(a.dir).expanduser().resolve()
    if (d / WS).exists():
        print(f"workspace: {d} is already a workspace ({WS} exists). To add a project: `workspace.py add`.")
        return 1
    m = forges().get(a.forge)
    if m is None:
        print(f"workspace: forge `{a.forge}` does not exist. Available: {', '.join(forges())}")
        return 1
    name = a.name or d.name
    repo = a.repo or (f"{a.org}/{name}" if a.org else "")
    ws = _json(MANAGEMENT / WS)
    ws["$schema"] = ".hermes/harness/plantillas/workspace/workspace.schema.json"
    ws.update(name=name, forge=a.forge)
    ws["management"]["repo"] = repo
    problems = ws_problems(ws)
    if problems:
        print("workspace: " + "\n  ".join(problems) + ("\n  (pass --org or --repo)" if not repo else ""))
        return 1
    print(f"{'Creating' if apply else 'DRY-RUN (--apply to run)'} the management project `{name}` in {d} · forge {a.forge}\n")
    own = {d / WS: json.dumps(ws, indent=2, ensure_ascii=False) + "\n",
           d / "AGENTS.md": management_agents(name),
           d / ".hermes" / "loop" / "tasks.md": (MANAGEMENT / "tasks.md").read_text(encoding="utf-8"),
           d / "roadmap.json": (MANAGEMENT / "roadmap.json").read_text(encoding="utf-8"),
           d / "wiki" / "Proyectos.md": projects_md(ws)}
    for f in sorted((MANAGEMENT / "wiki").glob("*.md")):
        own[d / "wiki" / f.name] = f.read_text(encoding="utf-8").replace("{workspace}", name)
    if m.get("issueTemplate"):
        own[d / m["issueTemplate"]["path"]] = m["issueTemplate"].get("header", "") + (MANAGEMENT / "epic.md").read_text(encoding="utf-8")

    def adjust(cfg: dict) -> None:
        import install as ins

        cfg.update(ins.merge_profile(cfg, _json(MANAGEMENT / "profile.json")))
        cfg["workspace"] = {"role": "management", "manifest": WS}
        cfg.setdefault("loop", {})["agentCommand"] = ws["agents"][ws["management"]["agent"]]
        cfg.setdefault("gate", {}).setdefault("signals", []).append(SIGNAL)

    if apply:
        d.mkdir(parents=True, exist_ok=True)
    _install(d, None, a.forge, adjust, own, apply)
    if not a.local:
        print(f"\nIn the forge ({m['id']}):")
        run(m, "repo.create", repo_vars(repo, description=f"Management of workspace {name}: epics, milestones, board and wiki"))
        for ms in _json(MANAGEMENT / "roadmap.json").get("milestones") or []:
            run(m, "milestone.create", repo_vars(repo, title=ms["title"], description=ms.get("description"), date=ms.get("date")))
        out = run(m, "board.create", repo_vars(repo, title=f"{name} · portfolio"))
        if out is not None:
            ws["management"]["board"] = fg.read_output(m, "board.create", out)
            if apply:
                write_ws(d, ws)
    print(f"""
Next (a human does it):
  1. cd {d} && git init && python3 .hermes/harness/scripts/githooks.py install
  2. git remote add origin <the URL of {repo}> and the first push
  3. {m.get('wikiNote') or 'the wiki: `workspace.py wiki --apply`'}
  4. Each coder: python3 .hermes/harness/scripts/workspace.py add <id> --repo <org/repo> --dir <path> --profile <stack> --agent claude-code
  5. An epic: python3 .hermes/harness/scripts/workspace.py epic "<title>" --child <id>:"<task>"; then `workspace.py dispatch <n>`""")
    return 0


def _ws_dir(a) -> Path:
    d = Path(a.ws).expanduser().resolve() if a.ws else find_ws(Path.cwd())
    if d is None or not (d / WS).is_file():
        sys.exit("workspace: no workspace.json found (run from the management repo or pass --ws)")
    return d


def _valid_ws(a) -> tuple[Path, dict] | None:
    d = _ws_dir(a)
    ws = read_ws(d)
    problems = ws_problems(ws)
    if problems:
        print("workspace: " + "\n  ".join(problems))
        return None
    return d, ws


def cmd_add(a, run: Runner, apply: bool) -> int:
    d = _ws_dir(a)
    ws = read_ws(d)
    if a.id in projects(ws) or a.id == "management":
        print(f"workspace: project `{a.id}` already exists")
        return 1
    p = {"id": a.id, "repo": a.repo, "role": "coder", "profile": a.profile, "agent": a.agent,
         "dir": os.path.relpath(Path(a.dir).expanduser().resolve(), d) if a.dir else None, "board": None}
    if a.forge:
        p["forge"] = a.forge
    p = {k: v for k, v in p.items() if v is not None or k == "board"}
    problems = ws_problems({**ws, "projects": [*(ws.get("projects") or []), p]})
    if problems:
        print("workspace: " + "\n  ".join(problems))
        return 1
    m = forge_of(ws, p)
    print(f"{'Adding' if apply else 'DRY-RUN (--apply to run)'} the coder `{a.id}` ({a.repo}) · forge {m['id']}"
          f" · agent {a.agent or '—'}\n")
    if a.dir:
        target = Path(a.dir).expanduser().resolve()
        if apply:
            target.mkdir(parents=True, exist_ok=True)

        def adjust(cfg: dict) -> None:
            cfg["workspace"] = {"role": "coder", "id": a.id, "management": ws["management"]["repo"]}
            if a.agent:
                cfg.setdefault("loop", {})["agentCommand"] = ws["agents"][a.agent]

        _install(target, a.profile, m["id"], adjust, {}, apply)

    def register() -> None:
        # Before the forge, and again after the board: if the forge fails, the project is already registered.
        if apply:
            write_ws(d, {**ws, "projects": [*(ws.get("projects") or []), p]})
            (d / "wiki").mkdir(exist_ok=True)
            (d / "wiki" / "Proyectos.md").write_text(projects_md(read_ws(d)), encoding="utf-8")

    register()
    print(f"\n{'' if apply else '(dry) '}{WS}: + projects[{a.id}] · wiki/Proyectos.md up to date")
    if a.local:
        return 0
    print(f"\nIn the forge ({m['id']}):")
    if a.create:
        run(m, "repo.create", repo_vars(a.repo, description=f"{ws.get('name')} · {a.id}"))
    out = run(m, "board.create", repo_vars(a.repo, title=f"{ws.get('name')} · {a.id}"))
    if out is not None:
        p["board"] = fg.read_output(m, "board.create", out)
        register()
    return 0


def cmd_epic(a, run: Runner, apply: bool) -> int:
    valid = _valid_ws(a)
    if valid is None:
        return 1
    d, ws = valid
    kids = []
    for spec in a.child or []:
        project, sep, task = spec.partition(":")
        if not sep or not project.strip() or not task.strip():
            print(f"workspace: `--child {spec}` is not `<project>:<task>`")
            return 1
        kids.append((project.strip(), task.strip()))
    print(f"{'Creating' if apply else 'DRY-RUN (--apply to publish)'} an epic in {ws['management']['repo']}: {a.title}\n")
    r, problems = create_epic(ws, a.title, kids, run, a.milestone, a.goal or "")
    if problems:
        print("workspace: nothing created:\n  " + "\n  ".join(problems))
        return 1
    print(f"\nepic {r}" + ("" if apply else " (dry: the number is simulated)") + f" · next: `workspace.py dispatch {fg.split_ref(r)[1]}`")
    return 0


def cmd_dispatch(a, run: Runner, apply: bool) -> int:
    valid = _valid_ws(a)
    if valid is None:
        return 1
    d, ws = valid
    print(f"{'Dispatching' if apply else 'DRY-RUN (--apply to publish)'} epic {ws['management']['repo']}#{a.n}\n")
    created, problems = dispatch(ws, a.n, run, d, write=apply)
    if problems:
        print("workspace: nothing dispatched (all or nothing):\n  " + "\n  ".join(problems))
        return 1
    if not created:
        print("  (nothing to dispatch: every child already has its issue)")
    if apply and int(a.n) not in (ws.get("epics") or []):
        ws["epics"] = [*(ws.get("epics") or []), int(a.n)]
        write_ws(d, ws)
    print(f"\n{len(created)} child(ren): {', '.join(created) or '—'}")
    return 0


def cmd_status(a, run: Runner, apply: bool) -> int:
    valid = _valid_ws(a)
    if valid is None:
        return 1
    d, ws = valid
    epics = a.n or ws.get("epics") or []
    if not epics:
        print("workspace: no epics dispatched yet (`workspace.py dispatch <n>` records them)")
        return 0
    rc = 0
    for n in epics:
        print(f"\n{ws['management']['repo']}#{n}")
        try:
            marks, changed = status(ws, n, run, d)
        except fg.ForgeError as e:
            print(f"  ✗ {e}")
            rc = 1
            continue
        done = sum(1 for v in marks.values() if v == "x")
        up = [r for r, v in marks.items() if v == "!"]
        print(f"  {done}/{len(marks)} closed" + (f" · escalated to a human: {', '.join(up)}" if up else "")
              + ("" if changed else " · the checklist was already up to date"))
    return rc


def cmd_wiki(a, run: Runner, apply: bool) -> int:
    valid = _valid_ws(a)
    if valid is None:
        return 1
    d, ws = valid
    m = forge_of(ws)
    remote = fg.fill(m.get("wiki") or "", fg.repo_vars(ws["management"]["repo"]))
    print(f"{'Publishing' if apply else 'DRY-RUN (--apply to publish)'} the wiki to {remote}\n  + wiki/Proyectos.md (from {WS})")
    if apply:
        (d / "wiki").mkdir(exist_ok=True)
        (d / "wiki" / "Proyectos.md").write_text(projects_md(ws), encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        steps = [["git", "clone", "-q", remote, tmp], ["copy", str(d / "wiki"), tmp], ["git", "-C", tmp, "add", "-A"],
                 ["git", "-C", tmp, "commit", "-q", "-m", "wiki: from workspace.py"], ["git", "-C", tmp, "push", "-q"]]
        for step in steps:
            print(f"  {'$' if apply else '+'} {shlex.join(step)}")
            if not apply:
                continue
            if step[0] == "copy":
                for f in Path(step[1]).glob("*.md"):
                    shutil.copy2(f, Path(tmp) / f.name)
                continue
            p = subprocess.run(step, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            if p.returncode != 0 and "commit" not in step:
                print(f"workspace: {(p.stderr or p.stdout).strip()[:400]}\n  {m.get('wikiNote') or ''}")
                return 1
    return 0


def cmd_check(a) -> int:
    errors = all_forge_problems()
    d = Path(a.ws).expanduser().resolve() if a.ws else find_ws(Path.cwd())
    errors += [f"template {WS}: {e}" for e in ws_problems(_json(MANAGEMENT / WS))]
    if d is not None and (d / WS).is_file():
        errors += [f"{WS}: {e}" for e in ws_problems(read_ws(d)) + management_problems(d)]
    for e in errors:
        print(f"  ✗ {e}")
    if errors:
        print(f"\nworkspace: {len(errors)} problem(s).")
        return 1
    print(f"✓ workspace: {len(forges())} forges against their schema and examples, each operation classified by its integration, "
          f"their pipeline and an epic end to end against the simulated forge" + (f" · {d / WS} valid" if d else ""))
    return 0


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="The workspace: management + coders on a forge (dry-run by default).")
    ap.add_argument("--ws", help="the management repo (default: the one holding workspace.json from the cwd)")
    sub = ap.add_subparsers(dest="cmd")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--apply", action="store_true")
    common.add_argument("--simulated", action="store_true", help="everything against the toy forge, no network")
    common.add_argument("--ws", default=argparse.SUPPRESS)
    p = sub.add_parser("init", parents=[common])
    p.add_argument("dir")
    p.add_argument("--forge", default="github")
    p.add_argument("--org")
    p.add_argument("--name")
    p.add_argument("--repo")
    p.add_argument("--local", action="store_true", help="only the files; nothing in the forge")
    p = sub.add_parser("add", parents=[common])
    p.add_argument("id")
    p.add_argument("--repo", required=True)
    p.add_argument("--dir")
    p.add_argument("--profile")
    p.add_argument("--agent")
    p.add_argument("--forge")
    p.add_argument("--create", action="store_true", help="also create the repo in the forge")
    p.add_argument("--local", action="store_true", help="register and install; nothing in the forge")
    p = sub.add_parser("epic", parents=[common])
    p.add_argument("title")
    p.add_argument("--child", action="append", help="<project>:<task> (repeatable)")
    p.add_argument("--milestone")
    p.add_argument("--goal", help="the epic's goal (its `## Objetivo` section)")
    p = sub.add_parser("dispatch", parents=[common])
    p.add_argument("n")
    p = sub.add_parser("status", parents=[common])
    p.add_argument("n", nargs="*")
    sub.add_parser("wiki", parents=[common])
    sub.add_parser("check", parents=[common])
    if not argv:
        print(__doc__)
        return 1
    a = ap.parse_args(argv)
    if a.cmd == "check":
        return cmd_check(a)
    apply = bool(getattr(a, "apply", False))
    if apply and a.simulated:
        print("workspace: --apply and --simulated do not go together")
        return 1
    run = Runner("apply" if apply else ("simulated" if a.simulated else "dry"))
    try:
        return {"init": cmd_init, "add": cmd_add, "epic": cmd_epic, "dispatch": cmd_dispatch, "status": cmd_status,
                "wiki": cmd_wiki}[a.cmd](a, run, apply)
    except fg.ForgeError as e:
        print(f"workspace: {e}")
        return 1


if __name__ == "__main__":
    # Windows: console and pipes default to cp1252, and `▶ ✓ ✗` or an `ñ` crash print BEFORE
    # anything is verified — the gate did not fail, it vanished (the CI matrix caught it).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
