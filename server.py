#!/usr/bin/env python3
"""
server.py - Il "ponte" tra la PWA e i tool CLI.

Architettura:
  - Gira in Termux (bionic), bind SOLO su 127.0.0.1 (mai esposto sulla rete).
  - Ogni tool ha un "runtime": "termux" (pacchetto nativo, eseguito diretto) o
    "proot" (dentro il Debian minimale via proot-distro). Il prefisso di
    esecuzione lo decide exec_prefix() in tools.py.
  - Tool "one-shot" (es. nmap -sn): eseguiti via subprocess, output in JSON.
  - Tool "interattivi" (es. msfconsole, sqlmap, shell): esposti come terminale
    web tramite ttyd, avviato on-demand su una porta dedicata.

Sicurezza:
  - I comandi sono liste di argomenti (niente shell=True -> niente injection).
  - Il target dell'utente e' validato con regex e non puo' iniziare con '-'
    (evita che diventi un flag arbitrario del tool).
  - Solo i tool nella whitelist TOOLS possono essere eseguiti.
"""

from __future__ import annotations

import atexit
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from native import run_native
from tools import (PROOT, TOOLS, TOR_SOCKS_PORT, detection_targets, exec_prefix,
                  inner_command, profiles_list, tools_by_category, validate_target)

# --------------------------------------------------------------------------- #
# Configurazione
# --------------------------------------------------------------------------- #

HOST = "127.0.0.1"
PORT = 8000
ONESHOT_TIMEOUT = 180          # secondi max per un comando one-shot
TTYD_BASE_PORT = 7681          # le istanze ttyd partono da qui
WEBAPP_DIR = Path(__file__).parent / "webapp"

# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #

app = FastAPI(title="Termux-NexusSEC-OS bridge")

_ttyd_procs: dict[str, tuple[subprocess.Popen, int]] = {}
_tor_proc: Optional[subprocess.Popen] = None


class RunRequest(BaseModel):
    tool: str
    target: Optional[str] = None
    anon: bool = False          # instrada il traffico via Tor (se il tool lo supporta)


def _require(*bins: str) -> None:
    """Verifica che i binari indicati siano nel PATH (installati da install.sh)."""
    for b in bins:
        if shutil.which(b) is None:
            raise HTTPException(500, f"Binario '{b}' non trovato. Hai lanciato install.sh?")


# --------------------------------------------------------------------------- #
# Gestione Tor (SOCKS su 127.0.0.1:9050, aperto da tor nativo in Termux)
# --------------------------------------------------------------------------- #

def tor_is_up() -> bool:
    """True se la porta SOCKS di Tor accetta connessioni."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, TOR_SOCKS_PORT)) == 0


def ensure_tor(wait: float = 25.0) -> None:
    """Avvia Tor nativamente in Termux (se non gia' attivo) e attende la SOCKS.

    Tor gira direttamente in Termux (pacchetto nativo): la porta 9050 e'
    raggiungibile sia dai tool Termux sia da quelli in proot (rete condivisa).
    """
    global _tor_proc
    if tor_is_up():
        return
    _require("tor")
    if _tor_proc is None or _tor_proc.poll() is not None:
        # tor gira in foreground: lo lanciamo in background come processo figlio.
        _tor_proc = subprocess.Popen(["tor"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + wait
    while time.time() < deadline:
        if tor_is_up():
            return
        time.sleep(0.7)
    raise HTTPException(504, "Tor non si e' avviato in tempo. Riprova o controlla l'installazione.")


@app.get("/api/tor/status")
def tor_status():
    return {"up": tor_is_up()}


@app.post("/api/tor/start")
def tor_start():
    ensure_tor()
    return {"up": True}


@app.post("/api/tor/stop")
def tor_stop():
    global _tor_proc
    if _tor_proc and _tor_proc.poll() is None:
        _tor_proc.terminate()
    _tor_proc = None
    # tor potrebbe essere stato avviato altrove: proviamo comunque a spegnerlo.
    subprocess.run(["pkill", "-x", "tor"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"up": tor_is_up()}


# --------------------------------------------------------------------------- #
# Rilevamento dei tool installati (per mostrare un pulsante attivo per ognuno)
# --------------------------------------------------------------------------- #

_INSTALLED: dict = {"t": 0.0, "ids": None}
INSTALL_TTL = 20.0     # secondi di cache: dopo un'installazione compare entro TTL


def installed_ids() -> set:
    """Insieme dei tool_id realmente installati (con cache breve)."""
    now = time.time()
    if _INSTALLED["ids"] is not None and now - _INSTALLED["t"] < INSTALL_TTL:
        return _INSTALLED["ids"]

    ids = {tid for tid, t in TOOLS.items() if t.get("mode") == "native"}
    termux_bins, proot_bins = detection_targets()

    for tid, b in termux_bins.items():
        if shutil.which(b):
            ids.add(tid)

    # Un'unica invocazione di proot per controllare tutti i binari del Debian.
    if proot_bins and shutil.which("proot-distro"):
        wanted = sorted(set(proot_bins.values()))
        script = "for b in " + " ".join(wanted) + \
                 '; do command -v "$b" >/dev/null 2>&1 && echo "$b"; done'
        try:
            r = subprocess.run(list(PROOT) + ["bash", "-lc", script],
                               capture_output=True, text=True, timeout=25)
            found = set(r.stdout.split())
            for tid, b in proot_bins.items():
                if b in found:
                    ids.add(tid)
        except (subprocess.SubprocessError, OSError):
            pass

    _INSTALLED["ids"] = ids
    _INSTALLED["t"] = now
    return ids


@app.get("/api/tools")
def list_tools():
    """Elenco dei tool per la UI, con flag 'installed' per ciascuno."""
    data = tools_by_category()
    inst = installed_ids()
    for tools in data.values():
        for t in tools:
            t["installed"] = t["id"] in inst
    return data


@app.post("/api/tools/refresh")
def refresh_tools():
    """Forza un nuovo rilevamento (utile subito dopo aver installato un tool)."""
    _INSTALLED["ids"] = None
    return list_tools()


@app.get("/api/profiles")
def list_profiles():
    """Profili (set di tool installabili insieme), stile distro NexusSec-OS."""
    return profiles_list()


@app.post("/api/run")
def run_oneshot(req: RunRequest):
    """Esegue un tool one-shot (Termux o proot) e ne restituisce l'output."""
    tool = TOOLS.get(req.tool)
    if tool is None:
        raise HTTPException(404, "Tool sconosciuto.")
    if tool.get("works") is False:
        raise HTTPException(400, tool.get("reason", "Non disponibile su telefono stock."))

    # Tool "nativi": richiesta HTTP diretta dal server, senza proot.
    if tool["mode"] == "native":
        target = None
        if tool.get("target"):
            try:
                target = validate_target(tool["target"], req.target or "")
            except ValueError as e:
                raise HTTPException(400, str(e))
        rc, out, err = run_native(req.tool, target)
        return JSONResponse({"returncode": rc, "stdout": out, "stderr": err})

    if tool["mode"] != "oneshot":
        raise HTTPException(400, "Questo tool e' interattivo: usa /api/terminal.")

    try:
        inner = inner_command(req.tool, req.target, req.anon)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Se il comando esce via Tor, assicurati che Tor sia attivo.
    if req.anon or tool.get("force_anon"):
        ensure_tor()

    # Prefisso a seconda del runtime: vuoto per Termux, proot per il Debian minimale.
    prefix = exec_prefix(req.tool)
    if prefix:
        _require("proot-distro")
    argv = prefix + inner

    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=ONESHOT_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"Timeout dopo {ONESHOT_TIMEOUT}s.")

    return JSONResponse({
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    })


@app.post("/api/terminal/{tool_id}")
def open_terminal(tool_id: str):
    """Avvia (lazy) un'istanza ttyd per un tool interattivo e ne ritorna l'URL."""
    tool = TOOLS.get(tool_id)
    if tool is None:
        raise HTTPException(404, "Tool sconosciuto.")
    if tool.get("works") is False:
        raise HTTPException(400, tool.get("reason", "Non disponibile su telefono stock."))
    if tool["mode"] != "interactive":
        raise HTTPException(400, "Questo tool e' one-shot: usa /api/run.")
    _require("ttyd")
    prefix = exec_prefix(tool_id)
    if prefix:
        _require("proot-distro")

    # I terminali che usano proxychains richiedono Tor attivo.
    if any("proxychains4" in part for part in tool["cmd"]):
        ensure_tor()

    # Riusa l'istanza se ancora viva.
    existing = _ttyd_procs.get(tool_id)
    if existing and existing[0].poll() is None:
        return {"url": f"http://{HOST}:{existing[1]}"}

    port = TTYD_BASE_PORT + len(_ttyd_procs)
    # ttyd: -i localhost, -W abilita l'input da tastiera, -t per un tema scuro.
    ttyd_cmd = [
        "ttyd", "-i", HOST, "-p", str(port), "-W",
        "-t", "theme={\"background\":\"#000000\"}",
        *prefix, *tool["cmd"],
    ]
    proc = subprocess.Popen(ttyd_cmd)
    _ttyd_procs[tool_id] = (proc, port)
    return {"url": f"http://{HOST}:{port}"}


@atexit.register
def _cleanup() -> None:
    for proc, _ in _ttyd_procs.values():
        if proc.poll() is None:
            proc.terminate()
    if _tor_proc and _tor_proc.poll() is None:
        _tor_proc.terminate()


# La PWA (static). Montata per ultima cosi' le rotte /api/* hanno precedenza.
if WEBAPP_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEBAPP_DIR), html=True), name="webapp")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
