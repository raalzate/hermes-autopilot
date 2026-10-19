"""
Forges: where each workspace project keeps its repo, issues, milestones, board and wiki (GitHub,
GitLab, Azure DevOps…). Used by `scripts/workspace.py` (ADR 0013).

A forge is a manifest (`plantillas/forges/<id>.json`, schema `plantillas/forges/forge.schema.json`)
that maps abstract OPERATIONS (`issue.create`, `issue.link`…) to argv of its CLI. Nothing of a
provider lives here (P4): no `gh`, no `glab`, no `az`. These functions are pure: they build
commands, read outputs and rewrite an epic's checklist. They launch no process (P19): the script
runs them, and it is the one that publishes, only with `--apply` (P13: the loop never publishes).

An argument template: `"{var}"` is replaced; a sub-list `["-m", "{milestone}"]` is an OPTIONAL
group: it goes in whole when it has all its variables and is left out when one is missing. A
variable missing outside a group is an error, never an empty argument.

The epic's checklist (the parent issue in the management repo) is the source of truth of the
dispatch: each child is a line `- [ ] [<project>] <title>`; once dispatched the line gets its
reference (`→ <repo>#<n>`); closed in the forge it is ticked `[x]`; escalated by the loop, `[!]`.
"""
from __future__ import annotations

import json
import re

OPERATIONS = ("repo.create", "issue.create", "issue.id", "issue.link", "issue.state", "issue.body",
              "issue.edit", "milestone.create", "board.create", "board.add")
STATES = ("open", "closed")
_VAR = re.compile(r"\{([a-z_]+)\}")
# `- [ ] [api] Title → org/api#12` · the mark, the project, the title and (once out) the reference.
CHILD = re.compile(r"^(?P<pre>\s*[-*]\s+\[)(?P<mark>[ xX!])\]\s+\[(?P<project>[\w.-]+)\]\s+(?P<title>.+?)"
                   r"(?:\s+→\s+(?P<ref>\S+#\d+))?\s*$")


class ForgeError(ValueError):
    pass


def variables(template) -> set[str]:
    out: set[str] = set()
    for a in template or []:
        for x in (a if isinstance(a, list) else [a]):
            out.update(_VAR.findall(str(x)))
    return out


def _fill(text: str, vars_: dict) -> str:
    return _VAR.sub(lambda m: str(vars_[m.group(1)]), text)


def fill(text: str, vars_: dict) -> str:
    """Like an argument template, but what has no value stays as it is (the wiki URL, the simulated
    forge output). One pass: a value with braces is not read again."""
    return _VAR.sub(lambda m: str(vars_[m.group(1)]) if m.group(1) in vars_ else m.group(0), text or "")


def command(manifest: dict, op: str, vars_: dict) -> list[str] | None:
    """The argv of `op` in this forge. None when the forge declares it `null` (not needed or not
    there, like the Azure Boards board, which comes with the project)."""
    ops = manifest.get("ops") or {}
    if op not in ops:
        raise ForgeError(f"forge `{manifest.get('id')}` does not declare the operation `{op}`")
    template = ops[op]
    if template is None:
        return None
    given = {**(manifest.get("defaults") or {}), **{k: v for k, v in vars_.items() if v is not None and v != ""}}
    argv: list[str] = []
    for a in template:
        if isinstance(a, list):
            if all(v in given for x in a for v in _VAR.findall(str(x))):
                argv.extend(_fill(str(x), given) for x in a)
            continue
        missing = [v for v in _VAR.findall(str(a)) if v not in given]
        if missing:
            raise ForgeError(f"`{op}` in `{manifest.get('id')}`: missing {', '.join(missing)}")
        argv.append(_fill(str(a), given))
    return argv


def read_output(manifest: dict, op: str, output: str) -> str:
    """What matters in what the CLI printed: `{"regex": …}` (first group) or `{"json": "a.b"}`."""
    spec = (manifest.get("output") or {}).get(op)
    text = (output or "").strip()
    if not spec:
        return text
    if spec.get("regex"):
        m = re.search(spec["regex"], text)
        if not m:
            raise ForgeError(f"`{op}`: the output does not hold what was expected ({spec['regex']}): {text[:200]!r}")
        return m.group(1)
    if spec.get("json"):
        try:
            v = json.loads(text)
            for k in spec["json"].split("."):
                v = v[int(k)] if isinstance(v, list) else v[k]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ForgeError(f"`{op}`: the output is not the expected JSON ({spec['json']}): {e}") from e
        return str(v)
    return text


def state(manifest: dict, raw: str) -> str:
    """The forge's state (`OPEN`, `opened`, `Done`…) in the workspace vocabulary."""
    return (manifest.get("states") or {}).get((raw or "").strip(), "open")


def repo_vars(repo: str) -> dict:
    """`org/repo` or `org/project/repo` (Azure): the parts the templates use."""
    parts = [p for p in (repo or "").split("/") if p]
    if len(parts) < 2:
        raise ForgeError(f"`{repo}` is not `<owner>/<repo>`")
    from urllib.parse import quote
    return {"repo": "/".join(parts), "owner": parts[0], "name": parts[-1],
            "project": parts[1] if len(parts) > 2 else parts[-1], "repo_enc": quote("/".join(parts), safe="")}


def ref(repo: str, n) -> str:
    return f"{repo}#{n}"


def split_ref(r: str) -> tuple[str, str]:
    repo, _, n = (r or "").rpartition("#")
    if not repo or not n.isdigit():
        raise ForgeError(f"`{r}` is not a `<repo>#<n>` reference")
    return repo, n


def children(body: str) -> list[dict]:
    """The child lines of the epic's checklist, in order, with their line number."""
    out = []
    for i, line in enumerate((body or "").splitlines()):
        m = CHILD.match(line)
        if m:
            out.append({"line": i, "mark": m.group("mark").lower(), "project": m.group("project"),
                        "title": m.group("title").strip(), "ref": m.group("ref") or ""})
    return out


def plan_dispatch(body: str, projects: dict) -> tuple[list[dict], list[str]]:
    """(what to create, problems). A child already dispatched is not repeated; one of a project the
    workspace does not have, or that is not a coder, is a problem and is not created."""
    create, problems = [], []
    for c in children(body):
        if c["ref"]:
            continue
        p = projects.get(c["project"])
        if not p:
            problems.append(f"line {c['line'] + 1}: project `{c['project']}` is not in workspace.json")
        elif p.get("role", "coder") != "coder":
            problems.append(f"line {c['line'] + 1}: `{c['project']}` is not a coder: code does not go to the management repo")
        else:
            create.append(c)
    return create, problems


def with_ref(body: str, line: int, r: str) -> str:
    lines = (body or "").splitlines()
    lines[line] = lines[line].rstrip() + f" → {r}"
    return "\n".join(lines) + ("\n" if (body or "").endswith("\n") else "")


def with_marks(body: str, marks: dict[str, str]) -> str:
    """The checklist with each child's mark by its reference: `x` closed, `!` escalated, ` ` open."""
    lines = (body or "").splitlines()
    for c in children(body):
        new = marks.get(c["ref"])
        if c["ref"] and new is not None and new != c["mark"]:
            m = CHILD.match(lines[c["line"]])
            lines[c["line"]] = lines[c["line"]][:m.end("pre")] + new + lines[c["line"]][m.end("mark"):]
    return "\n".join(lines) + ("\n" if (body or "").endswith("\n") else "")


def child_body(manifest: dict, parent: str, text: str = "") -> str:
    """The child issue's body: it always names the parent, even when the forge has a native link (if
    the link fails or is lost, the text stays and `status` still finds it)."""
    template = manifest.get("childBody") or "Part of {parent}"
    return (text.strip() + "\n\n" if text.strip() else "") + template.replace("{parent}", parent)


def manifest_problems(m: dict) -> list[str]:
    """What the forge schema cannot say: every operation present (null when not needed), each one
    starting with the forge's CLI, and the issue pattern compiling and matching its example."""
    out = []
    ops = m.get("ops") or {}
    for op in OPERATIONS:
        if op not in ops:
            out.append(f"missing operation `{op}` (null when the forge does not need it)")
    for op, template in ops.items():
        if op not in OPERATIONS:
            out.append(f"`{op}` is not a workspace operation")
        elif template is not None and (not template or str(template[0]) != m.get("cli")):
            out.append(f"`{op}` does not start with the forge CLI (`{m.get('cli')}`)")
    for v in (m.get("states") or {}).values():
        if v not in STATES:
            out.append(f"state `{v}` is not one of {STATES}")
    try:
        if m.get("issueExample") and not re.search(m.get("issuePattern") or "(?!)", m["issueExample"]):
            out.append("`issueExample` does not match `issuePattern`")
    except re.error as e:
        out.append(f"`issuePattern` does not compile: {e}")
    return out
