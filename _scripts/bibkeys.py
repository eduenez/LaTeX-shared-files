#!/usr/bin/env python3
"""bibkeys.py — duplicate entries and retired citation keys of math-bibliography (maintainer library; used by vendor.py
bib-dedup and by sync-all).

Duplicates: two entries of the master that are the same work, recognized by an identifier (the arXiv id — eprint, an
arxiv.org URL, a 10.48550/arXiv DOI or an "arXiv:NNNN.NNNNN" note — or a DOI). They are merged into one: the survivor keeps its
fields and takes the fields only the others have; the others' keys are retired, recorded in rekey-dedup.json.

Retired keys (aliases): every rekey*.json of the master maps an old key to its replacement. An alias is usable only when the
old key is no longer in the master and the chain of replacements ends at a key that is (the older maps contain entries
that later maps or merges superseded; those are ignored). sync-all rewrites the citations of retired keys in every consumer
(rename_cites), and update_shared.py drops the consumer's leftover copy of a retired entry.
"""
import json
import re
from pathlib import Path

DEDUP_MAP = "rekey-dedup.json"
ARXIV_NOTE = re.compile(r"arXiv[:.]\s*(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", re.I)
KEY_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*:\d{4}[a-z]?$")
CITE = re.compile(r"(\\(?:no)?cite[A-Za-z]*\*?(?:\[[^\]]*\]){0,2}\{)([^}]*)(\})")


# ── fields of one entry (bibtex-tidy layout: `  name = value,` with balanced braces) ───────────────────────────────

def fields(raw: str) -> dict[str, str]:
    """{lowercase field name: value text as written (braces kept)}."""
    body = raw[raw.index(",") + 1:raw.rstrip().rindex("}")] if "," in raw else ""
    out, i, n = {}, 0, len(body)
    while i < n:
        m = re.compile(r"\s*([A-Za-z][\w-]*)\s*=\s*").match(body, i)
        if not m:
            break
        name, j, depth = m.group(1).lower(), m.end(), 0
        k = j
        while k < n:
            ch = body[k]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == '"' and depth == 0:
                k = body.index('"', k + 1)
            elif ch == "," and depth == 0:
                break
            k += 1
        out[name] = body[j:k].strip()
        i = k + 1
    return out


def _plain(v: str) -> str:
    return re.sub(r"[{}\s]", "", v)


def identifiers(raw: str) -> set[str]:
    """'arxiv:<id>' and 'doi:<doi>' identifiers of an entry (lowercase, versions dropped)."""
    f = fields(raw)
    ids = set()
    if f.get("eprint") and _plain(f.get("archiveprefix", "")).lower() == "arxiv":
        ids.add("arxiv:" + re.sub(r"v\d+$", "", _plain(f["eprint"]).lower()))
    doi = _plain(f.get("doi", "")).lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    if doi.startswith("10.48550/arxiv."):
        ids.add("arxiv:" + re.sub(r"v\d+$", "", doi.split("arxiv.", 1)[1]))
    elif doi:
        ids.add("doi:" + doi)
    url = _plain(f.get("url", ""))
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+?)(?:v\d+)?(?:\.pdf)?/?$", url, re.I)
    if m:
        ids.add("arxiv:" + m.group(1).lower())
    for m in ARXIV_NOTE.finditer(f.get("note", "") + " " + f.get("howpublished", "")):
        ids.add("arxiv:" + m.group(1).lower())
    return ids


# ── duplicates ──────────────────────────────────────────────────────────────────────────────────────────────────────

def title_of(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"\\[A-Za-z]+|[{}]", "", fields(raw).get("title", "")).lower())


def duplicate_groups(kmap: dict[str, str]) -> list[list[str]]:
    """Groups (of 2+ keys) of entries sharing an identifier AND the same title, transitively; each sorted survivor-first.
    (A shared identifier with different titles is a metadata error, not a duplicate: see suspect_pairs.)"""
    parent = {k: k for k in kmap}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    seen = {}
    for k, raw in kmap.items():
        for i in identifiers(raw):
            i = (i, title_of(raw))
            if i in seen:
                parent[find(k)] = find(seen[i])
            else:
                seen[i] = k
    groups = {}
    for k in kmap:
        groups.setdefault(find(k), []).append(k)
    return [sorted(g, key=lambda k: survivor_rank(k, kmap[k])) for g in groups.values() if len(g) > 1]


def suspect_pairs(kmap: dict[str, str]) -> list[tuple[str, str, str]]:
    """(key, key, identifier) of entries sharing an identifier but not the title: reported for a person, never merged."""
    seen, out = {}, []
    for k, raw in kmap.items():
        for i in identifiers(raw):
            if i in seen and title_of(kmap[seen[i]]) != title_of(raw):
                out.append((seen[i], k, i))
            seen.setdefault(i, k)
    return out


def survivor_rank(key: str, raw: str):
    """Sort key: the house-style key first, then a key whose year is the entry's year, then the entry with more fields,
    then the lower key."""
    year = _plain(fields(raw).get("year", ""))
    return (not KEY_RE.match(key), not (year and re.search(r":" + re.escape(year) + r"[a-z]?$", key)), -len(fields(raw)), key)


def merge_entry(survivor_raw: str, others: list[str]) -> str:
    """The survivor with the fields that only the others have appended (bibtex-tidy re-lays them out)."""
    have = fields(survivor_raw)
    extra = {}
    for raw in others:
        for name, v in fields(raw).items():
            if name not in have and name not in extra:
                extra[name] = v
    if not extra:
        return survivor_raw
    head = survivor_raw.rstrip()[:-1].rstrip().rstrip(",")
    return head + ",\n" + "".join(f"  {n} = {v},\n" for n, v in extra.items()) + "}"


# ── retired keys ────────────────────────────────────────────────────────────────────────────────────────────────────

def aliases(master_dir: Path, master_keys) -> dict[str, str]:
    """{retired key: current key} from every rekey*.json of the master (later files win), chains followed; only aliases whose
    old key is gone from the master and whose final key is in it."""
    raw = {}
    for p in sorted(Path(master_dir).glob("rekey*.json")):
        try:
            raw.update(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    master_keys = set(master_keys)
    out = {}
    for old in raw:
        if old in master_keys:
            continue
        new, hops = raw[old], 0
        while new not in master_keys and new in raw and hops < 20:
            new, hops = raw[new], hops + 1
        if new in master_keys and new != old:
            out[old] = new
    return out


def record_dedup(master_dir: Path, renames: dict[str, str]) -> None:
    p = Path(master_dir) / DEDUP_MAP
    data = json.loads(p.read_text()) if p.exists() else {}
    data.update(renames)
    p.write_text(json.dumps(dict(sorted(data.items(), key=lambda kv: kv[0].lower())), indent=2, ensure_ascii=False) + "\n")


# ── citations in a consumer ─────────────────────────────────────────────────────────────────────────────────────────

def _strip_comment(line: str) -> tuple[str, str]:
    m = re.search(r"(?<!\\)%", line)
    return (line, "") if not m else (line[:m.start()], line[m.start():])


def rename_cites_in(text: str, mapping: dict[str, str]) -> tuple[str, set[str]]:
    """text with \\cite-family keys renamed (outside comments) -> (new text, keys renamed)."""
    done = set()

    def sub(m):
        keys = m.group(2).split(",")
        out = []
        for k in keys:
            s = k.strip()
            if s in mapping:
                done.add(s)
                out.append(k.replace(s, mapping[s]))
            else:
                out.append(k)
        return m.group(1) + ",".join(out) + m.group(3)

    lines = text.split("\n")
    for i, line in enumerate(lines):
        code, comment = _strip_comment(line)
        if "cite" in code:
            lines[i] = CITE.sub(sub, code) + comment
    return "\n".join(lines), done


def frozen(tex: Path, tracked: set[str], root: Path) -> bool:
    """A .tex with a tracked .bbl of the same name beside it is a frozen (submitted/arXiv) version: never rewritten."""
    return str(tex.with_suffix(".bbl").relative_to(root)) in tracked


BIBDECL = re.compile(r"\\(?:bibliography|addbibresource)(?:\[[^\]]*\])?\{([^}]*)\}")


def uses_master(text: str) -> bool:
    """True if the .tex draws on references.bib (its \\bibliography/\\addbibresource names it), or declares no bibliography at
    all (a fragment \\input into a paper). A file whose bibliographies are all other databases, or that carries its own
    thebibliography, is not the master's to rename."""
    decls = []
    for line in text.split("\n"):
        code, _ = _strip_comment(line)
        if "\\begin{thebibliography}" in code or "\\bibitem" in code:
            return False                        # its own hand-made bibliography: its keys are its own
        decls += [d.strip() for m in BIBDECL.finditer(code) for d in m.group(1).split(",")]
    return not decls or any(re.sub(r"\.bib$", "", d).rsplit("/", 1)[-1] == "references" for d in decls)
