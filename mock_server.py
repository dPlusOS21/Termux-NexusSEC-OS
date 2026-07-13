#!/usr/bin/env python3
"""
mock_server.py - Backend FINTO per testare la webapp sul PC, senza Termux/Kali.

Espone le stesse API di server.py (/api/tools, /api/run, /api/terminal) ma:
  - i tool one-shot restituiscono output SIMULATO (non esegue nulla);
  - i tool interattivi aprono una pagina "terminale finto" invece di ttyd.

Usa solo la libreria standard: nessuna installazione richiesta.

    python3 mock_server.py     # poi apri http://127.0.0.1:8000
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from native import run_native
from tools import TOOLS, inner_command, tools_by_category, validate_target

HOST, PORT = "127.0.0.1", 8000
_MOCK_TOR = {"up": False}       # stato Tor simulato per il mock
WEBAPP_DIR = Path(__file__).parent / "webapp"
CTYPE = {".html": "text/html", ".js": "application/javascript",
         ".json": "application/json", ".css": "text/css", ".svg": "image/svg+xml"}


def mock_output(tool_id: str, target: str | None) -> str:
    """Output simulato ma plausibile per i tool one-shot."""
    t = target or "target"
    if tool_id == "nmap_ping":
        return (f"Starting Nmap 7.94 ( https://nmap.org )\n"
                f"Nmap scan report for {t}\n"
                f"Host is up (0.012s latency).\n"
                f"Nmap scan report for 192.168.1.1\nHost is up.\n"
                f"Nmap scan report for 192.168.1.10\nHost is up.\n"
                f"Nmap done: 256 IP addresses (3 hosts up) scanned in 2.31s\n"
                f"\n[MOCK] output simulato — nessuna scansione reale eseguita.")
    if tool_id == "nmap_quick":
        return (f"Starting Nmap 7.94 ( https://nmap.org )\n"
                f"Nmap scan report for {t}\nHost is up (0.010s latency).\n\n"
                f"PORT     STATE SERVICE\n22/tcp   open  ssh\n"
                f"80/tcp   open  http\n443/tcp  open  https\n\n"
                f"Nmap done: 1 IP address (1 host up) scanned in 1.84s\n"
                f"\n[MOCK] output simulato.")
    if tool_id == "whois":
        return (f"Domain Name: {t.upper()}\nRegistrar: Example Registrar Inc.\n"
                f"Creation Date: 2015-06-01T00:00:00Z\nName Server: ns1.example.net\n"
                f"\n[MOCK] output simulato.")
    if tool_id == "whatweb":
        return (f"{t} [200 OK] Country[ITALY][IT], HTTPServer[nginx], "
                f"nginx, Title[Esempio], IP[203.0.113.7]\n"
                f"\n[MOCK] output simulato.")
    if tool_id == "nikto":
        return (f"- Nikto v2.5.0\n+ Target: {t}\n"
                f"+ Server: nginx\n+ /: X-Frame-Options header non presente.\n"
                f"+ 7891 requests: 0 error(s) and 2 item(s) reported.\n"
                f"\n[MOCK] output simulato.")
    if tool_id == "tor_ip":
        return ('{"IsTor":true,"IP":"185.220.101.42"}\n'
                "\n[MOCK] IP di uscita simulato (un exit node Tor).")
    return f"[MOCK] {tool_id} eseguito su {t}."


TERM_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{{background:#000;color:#0f6;font-family:monospace;padding:14px;margin:0}}
input{{background:#000;color:#0f6;border:0;font-family:monospace;font-size:14px;width:80%;outline:none}}
</style></head><body>
<div id="log">[MOCK] Terminale finto per <b>{name}</b>.<br>
Sul telefono qui girerebbe il tool reale via ttyd dentro Kali.<br><br></div>
<span>$&nbsp;</span><input id="cmd" autofocus autocomplete="off">
<script>
const log=document.getElementById('log'),cmd=document.getElementById('cmd');
cmd.addEventListener('keydown',e=>{{if(e.key==='Enter'){{
 log.innerHTML+='$ '+cmd.value+'<br>[mock] comando non eseguito (ambiente di test).<br>';
 cmd.value='';window.scrollTo(0,document.body.scrollHeight);}}}});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def log_message(self, *_):  # silenzia il log di default
        pass

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/tools":
            return self._json(200, tools_by_category())
        if path == "/api/tor/status":
            return self._json(200, {"up": _MOCK_TOR["up"]})
        if path.startswith("/mock/term/"):
            tid = path.rsplit("/", 1)[-1]
            tool = TOOLS.get(tid)
            name = tool["name"] if tool else tid
            return self._send(200, TERM_PAGE.format(name=name), "text/html")
        # static (webapp)
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (WEBAPP_DIR / rel).resolve()
        if not str(f).startswith(str(WEBAPP_DIR.resolve())) or not f.is_file():
            return self._send(404, "not found", "text/plain")
        return self._send(200, f.read_bytes(), CTYPE.get(f.suffix, "application/octet-stream"))

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}

        if path in ("/api/tor/start", "/api/tor/stop"):
            _MOCK_TOR["up"] = path.endswith("start")
            return self._json(200, {"up": _MOCK_TOR["up"]})

        if path == "/api/run":
            tid = payload.get("tool")
            tool = TOOLS.get(tid)
            if tool is None:
                return self._json(404, {"detail": "Tool sconosciuto."})
            # Tool nativi: eseguiti DAVVERO anche nel mock (sono solo HTTP).
            if tool["mode"] == "native":
                target = None
                if tool.get("target"):
                    try:
                        target = validate_target(tool["target"], payload.get("target") or "")
                    except ValueError as e:
                        return self._json(400, {"detail": str(e)})
                rc, out, err = run_native(tid, target)
                return self._json(200, {"returncode": rc, "stdout": out, "stderr": err})
            if tool["mode"] != "oneshot":
                return self._json(400, {"detail": "Tool interattivo."})
            anon = bool(payload.get("anon"))
            try:
                # valida target e coerenza della richiesta anon (stessa logica del reale)
                inner_command(tid, payload.get("target"), anon)
            except ValueError as e:
                return self._json(400, {"detail": str(e)})
            out = mock_output(tid, payload.get("target"))
            if anon or tool.get("force_anon"):
                out = "[via Tor] " + out
            return self._json(200, {"returncode": 0, "stdout": out, "stderr": ""})

        if path.startswith("/api/terminal/"):
            tid = path.rsplit("/", 1)[-1]
            tool = TOOLS.get(tid)
            if tool is None:
                return self._json(404, {"detail": "Tool sconosciuto."})
            if tool["mode"] != "interactive":
                return self._json(400, {"detail": "Tool one-shot."})
            return self._json(200, {"url": f"/mock/term/{tid}"})

        return self._json(404, {"detail": "not found"})


if __name__ == "__main__":
    print(f"[MOCK] Termux-NexusSEC-OS UI su http://{HOST}:{PORT}  (Ctrl+C per fermare)")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
