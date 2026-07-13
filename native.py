"""
native.py - Tool "nativi": funzioni che il server esegue direttamente via HTTP,
senza proot/Kali. Interrogano servizi esterni pubblici (es. RDAP per il whois).

Vantaggi rispetto ai tool in proot:
  - non richiedono l'installazione di Kali (~2 GB);
  - sono istantanei (nessun avvio di proot);
  - funzionano identici su telefono e su PC.

Usa solo la libreria standard.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

RDAP_BASE = "https://rdap.org"          # bootstrap: reindirizza al server RDAP giusto
HTTP_TIMEOUT = 25
_UA = {"User-Agent": "Termux-NexusSEC-OS/1.0 (RDAP client)",
       "Accept": "application/rdap+json, application/json"}

_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _vcard_field(entity: dict, field: str) -> str | None:
    """Estrae un campo (es. 'fn', 'org') dal vcardArray di un'entita' RDAP."""
    vcard = entity.get("vcardArray")
    if not isinstance(vcard, list) or len(vcard) < 2:
        return None
    for item in vcard[1]:
        if isinstance(item, list) and item and item[0] == field:
            return str(item[-1])
    return None


def _fmt_events(events: list) -> list[str]:
    out = []
    for e in events or []:
        action = e.get("eventAction", "?")
        date = (e.get("eventDate", "") or "")[:19].replace("T", " ")
        out.append(f"  {action:<22} {date}")
    return out


def _fmt_entities(entities: list) -> list[str]:
    out = []
    for ent in entities or []:
        roles = ", ".join(ent.get("roles", [])) or "?"
        name = _vcard_field(ent, "fn") or _vcard_field(ent, "org") or ent.get("handle", "?")
        out.append(f"  {roles:<22} {name}")
    return out


def _format_domain(d: dict) -> str:
    lines = [f"Dominio      : {d.get('ldhName', '?')}"]
    if d.get("status"):
        lines.append("Stato        : " + ", ".join(d["status"]))
    ev = _fmt_events(d.get("events"))
    if ev:
        lines += ["Eventi       :"] + ev
    ns = [n.get("ldhName", "?") for n in d.get("nameservers", [])]
    if ns:
        lines.append("Nameserver   : " + ", ".join(ns))
    en = _fmt_entities(d.get("entities"))
    if en:
        lines += ["Contatti     :"] + en
    return "\n".join(lines)


def _format_ip(d: dict) -> str:
    lines = [f"Rete         : {d.get('handle', '?')}  ({d.get('name', '?')})"]
    rng = f"{d.get('startAddress', '?')} - {d.get('endAddress', '?')}"
    lines.append(f"Intervallo   : {rng}")
    if d.get("country"):
        lines.append(f"Paese        : {d['country']}")
    if d.get("type"):
        lines.append(f"Tipo         : {d['type']}")
    en = _fmt_entities(d.get("entities"))
    if en:
        lines += ["Contatti     :"] + en
    return "\n".join(lines)


def _rdap(target: str) -> tuple[int, str, str]:
    kind = "ip" if _IPV4_RE.match(target) else "domain"
    url = f"{RDAP_BASE}/{kind}/{urllib.request.quote(target)}"
    try:
        data = _http_get_json(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 1, "", f"'{target}' non trovato nel sistema RDAP (TLD/registro non supportato?)."
        return 1, "", f"Errore RDAP HTTP {e.code}."
    except urllib.error.URLError as e:
        return 1, "", f"Errore di rete verso RDAP: {e.reason}."
    except (TimeoutError, json.JSONDecodeError) as e:
        return 1, "", f"Risposta RDAP non valida o timeout: {e}."

    body = _format_ip(data) if kind == "ip" else _format_domain(data)
    footer = f"\n\n[fonte: RDAP via {url}]"
    return 0, body + footer, ""


# Dispatch: tool_id -> funzione
_NATIVE = {
    "rdap": _rdap,
}


def run_native(tool_id: str, target: str | None) -> tuple[int, str, str]:
    """Esegue un tool nativo. Ritorna (returncode, stdout, stderr)."""
    fn = _NATIVE.get(tool_id)
    if fn is None:
        return 1, "", f"Tool nativo '{tool_id}' non implementato."
    return fn(target or "")
