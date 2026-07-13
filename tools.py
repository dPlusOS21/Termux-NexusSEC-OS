"""
tools.py - Registry dei tool e validazione, condiviso tra server.py (backend
reale su Termux) e mock_server.py (backend finto per testare la UI sul PC).

Non importa nulla di esterno: cosi' e' usabile anche senza FastAPI installato.
"""

from __future__ import annotations

import re

# Distro minimale in proot: solo per i pochi tool non disponibili nativamente in
# Termux (whatweb, nikto, metasploit). Debian slim pesa ~200-400 MB, contro i
# ~2 GB di Kali completa.
DISTRO = "debian"

# Prefisso per eseguire un comando dentro la distro proot (Debian).
PROOT = ["proot-distro", "login", DISTRO, "--"]

# Prefisso per instradare un comando TCP attraverso Tor (modalita' "anonima").
# -q = silenzioso. proxychains4 funziona solo con connessioni TCP connect().
# Presente sia in Termux (proxychains-ng) sia nel Debian in proot: la stessa
# stringa funziona in entrambi i runtime, e Tor gira in Termux su 127.0.0.1:9050
# (raggiungibile anche da dentro proot, che condivide la rete con Termux).
PROXYCHAINS = ["proxychains4", "-q"]

# Porta SOCKS locale aperta da Tor (girato nativamente in Termux).
TOR_SOCKS_PORT = 9050

# --------------------------------------------------------------------------- #
# Registry dei tool
# --------------------------------------------------------------------------- #
# mode:    "oneshot"     -> HTTP + output JSON
#          "interactive" -> terminale web via ttyd
#          "native"      -> richiesta HTTP diretta dal server (nessun binario)
# runtime: "termux"      -> eseguito direttamente in Termux (pacchetto nativo)
#          "proot"       -> eseguito nel Debian minimale via proot-distro
#          (assente per i tool "native": non eseguono binari)
# target:  None | "host" | "url"
# cmd:     argv base (senza il target), a cui si aggiunge il target validato.

TOOLS: dict[str, dict] = {
    # --- Network -----------------------------------------------------------
    "nmap_quick": {
        "name": "Nmap · scansione rapida",
        "category": "Network", "mode": "oneshot", "runtime": "termux", "target": "host",
        "cmd": ["nmap", "-sT", "-T4", "-F"],   # -sT = connect scan: instradabile via Tor
        "anon_ok": True,
        "help": "Porte comuni di un host o range (es. 192.168.1.1 o 192.168.1.0/24)",
    },
    "nmap_ping": {
        "name": "Nmap · host attivi (ping sweep)",
        "category": "Network", "mode": "oneshot", "runtime": "termux", "target": "host",
        "cmd": ["nmap", "-sn"],
        "help": "Elenca gli host vivi in una rete (es. 192.168.1.0/24). NB: usa ICMP/ARP, non passa da Tor.",
    },
    "whois": {
        "name": "Whois",
        "category": "Network", "mode": "oneshot", "runtime": "termux", "target": "host",
        "cmd": ["whois"], "anon_ok": True,
        "help": "Informazioni di registrazione di un dominio (pacchetto nativo Termux)",
    },
    "rdap": {
        "name": "Whois RDAP (senza proot)",
        "category": "Network", "mode": "native", "target": "host",
        "cmd": [],   # nativo: nessun comando shell, il server fa una richiesta HTTPS
        "help": "Dati di un dominio o IP via RDAP (API pubblica). Non richiede proot: funziona subito.",
    },
    "dig": {
        "name": "Dig · lookup DNS",
        "category": "Network", "mode": "oneshot", "runtime": "termux", "target": "host",
        "cmd": ["dig", "+noall", "+answer", "+nocmd"],
        "help": "Record DNS (A) di un dominio. Nativo Termux (dnsutils).",
    },
    "dnsrecon": {
        "name": "DNSRecon · enumerazione DNS",
        "category": "Network", "mode": "oneshot", "runtime": "proot", "target": "host",
        "cmd": ["dnsrecon", "-d"],
        "help": "Enumera record e prova zone transfer di un dominio (via Debian).",
    },
    # --- Web ---------------------------------------------------------------
    "whatweb": {
        "name": "WhatWeb · fingerprint",
        "category": "Web", "mode": "oneshot", "runtime": "proot", "target": "url",
        "cmd": ["whatweb", "--color=never"], "anon_ok": True,
        "help": "Tecnologie usate da un sito (es. https://esempio.it)",
    },
    "nikto": {
        "name": "Nikto · scanner web",
        "category": "Web", "mode": "oneshot", "runtime": "proot", "target": "url",
        "cmd": ["nikto", "-nointeractive", "-h"], "anon_ok": True,
        "help": "Vulnerabilita' note di un web server (es. https://esempio.it)",
    },
    "wafw00f": {
        "name": "wafw00f · rileva WAF",
        "category": "Web", "mode": "oneshot", "runtime": "proot", "target": "url",
        "cmd": ["wafw00f"], "anon_ok": True,
        "help": "Rileva il Web Application Firewall davanti a un sito (via Debian).",
    },
    "sqlmap": {
        "name": "sqlmap (interattivo)",
        "category": "Web", "mode": "interactive", "runtime": "termux", "target": None,
        "cmd": ["bash", "-lc", "sqlmap --wizard || bash"],
        "help": "SQL injection; parte in modalita' wizard",
    },
    "wfuzz": {
        "name": "Wfuzz · fuzzing web (interattivo)",
        "category": "Web", "mode": "interactive", "runtime": "proot", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: wfuzz -w wordlist.txt https://sito/FUZZ'; "
                               "echo 'FUZZ = punto da fuzzare, -w = wordlist'; bash"],
        "help": "Fuzzing di parametri/percorsi web con wordlist (via Debian).",
    },
    # --- Exploitation ------------------------------------------------------
    "metasploit": {
        "name": "Metasploit (console)",
        "category": "Exploitation", "mode": "interactive", "runtime": "proot", "target": None,
        "cmd": ["bash", "-lc", "msfconsole || bash"],
        "help": "Console Metasploit (richiede INSTALL_METASPLOIT=yes)",
    },
    "hydra": {
        "name": "Hydra (interattivo)",
        "category": "Exploitation", "mode": "interactive", "runtime": "termux", "target": None,
        "cmd": ["bash", "-lc", "hydra; bash"],
        "help": "Brute-force di login; usa la shell per comporre il comando",
    },
    # --- Cracking offline --------------------------------------------------
    "aircrack": {
        "name": "Aircrack-ng (crack offline)",
        "category": "Cracking", "mode": "interactive", "runtime": "termux", "target": None,
        "cmd": ["bash", "-lc", "echo 'Crack offline di un .cap gia catturato. Esempio:'; "
                               "echo '  aircrack-ng -w wordlist.txt handshake.cap'; bash"],
        "help": "Solo crack offline di handshake gia' catturati (la cattura non e' possibile su telefono stock)",
    },
    "john": {
        "name": "John the Ripper (interattivo)",
        "category": "Cracking", "mode": "interactive", "runtime": "termux", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: john --wordlist=rockyou.txt hash.txt'; bash"],
        "help": "Cracking di hash da file",
    },
    # --- Anonimato ---------------------------------------------------------
    "tor_ip": {
        "name": "Verifica IP di uscita (Tor)",
        "category": "Anonimato", "mode": "oneshot", "runtime": "termux", "target": None,
        "cmd": ["curl", "-s", "--max-time", "25", "https://check.torproject.org/api/ip"],
        "anon_ok": True, "force_anon": True,
        "help": "Mostra l'IP con cui esci verso l'esterno: attiva Tor e controlla che sia un exit node.",
    },
    "shell_anon": {
        "name": "Shell anonima (via Tor)",
        "category": "Anonimato", "mode": "interactive", "runtime": "termux", "target": None,
        "cmd": ["bash", "-lc", "echo 'Ogni comando TCP qui e instradato via Tor (proxychains).'; "
                               "echo 'Esempio:  curl https://check.torproject.org/api/ip'; "
                               "exec proxychains4 bash -l"],
        "help": "Terminale in cui il traffico TCP passa da Tor. Richiede Tor attivo.",
    },
    # --- Sistema -----------------------------------------------------------
    "shell": {
        "name": "Shell Debian (proot)",
        "category": "Sistema", "mode": "interactive", "runtime": "proot", "target": None,
        "cmd": ["bash", "-l"],
        "help": "Terminale libero dentro il Debian minimale (proot)",
    },

    # ======================================================================= #
    # CATALOGO (catalog=True): tool extra NON installati di default. Compaiono
    # nella UI come "da installare" (toggle 🧰). "repo":"kali" indica che il
    # pacchetto sta nel repo di Kali, non in Debian standard.
    # ======================================================================= #
    # --- Network / OSINT ---------------------------------------------------
    "dnsenum": {
        "name": "DNSenum · enumerazione DNS",
        "category": "Network", "mode": "oneshot", "runtime": "proot", "target": "host",
        "cmd": ["dnsenum"], "catalog": True, "repo": "kali",
        "help": "Tipo: recon DNS. Sottodomini, record e tentativi di zone transfer.",
    },
    "theharvester": {
        "name": "theHarvester · OSINT",
        "category": "Network", "mode": "oneshot", "runtime": "proot", "target": "host",
        "cmd": ["theHarvester", "-b", "all", "-d"], "catalog": True, "repo": "kali",
        "pkg": "theharvester",
        "help": "Tipo: OSINT. Raccoglie email, sottodomini e host da fonti pubbliche.",
    },
    # --- Web ---------------------------------------------------------------
    "wpscan": {
        "name": "WPScan · sicurezza WordPress",
        "category": "Web", "mode": "oneshot", "runtime": "proot", "target": "url",
        "cmd": ["wpscan", "--no-banner", "--url"], "anon_ok": True,
        "catalog": True, "repo": "kali",
        "help": "Tipo: scanner CMS. Vulnerabilita' di siti WordPress (plugin/tema/utenti).",
    },
    "gobuster": {
        "name": "Gobuster · brute dir/DNS",
        "category": "Web", "mode": "interactive", "runtime": "proot", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: gobuster dir -u https://sito -w wordlist.txt'; bash"],
        "catalog": True, "repo": "kali",
        "help": "Tipo: content discovery. Brute force di directory, DNS e vhost via wordlist.",
    },
    "dirb": {
        "name": "Dirb · scanner directory",
        "category": "Web", "mode": "interactive", "runtime": "proot", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: dirb https://sito /usr/share/wordlists/dirb/common.txt'; bash"],
        "catalog": True, "repo": "kali",
        "help": "Tipo: content discovery. Scanner classico di contenuti/directory web.",
    },
    "commix": {
        "name": "Commix · command injection",
        "category": "Web", "mode": "interactive", "runtime": "proot", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: commix -u \"https://sito/page?id=1\"'; bash"],
        "catalog": True, "repo": "kali",
        "help": "Tipo: exploit web. Rileva e sfrutta vulnerabilita' di command injection.",
    },
    # --- Cracking ----------------------------------------------------------
    "hashcat": {
        "name": "Hashcat · cracking hash",
        "category": "Cracking", "mode": "interactive", "runtime": "termux", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: hashcat -m 0 hash.txt wordlist.txt'; bash"],
        "catalog": True,
        "help": "Tipo: password cracking. Cracking di hash ad alte prestazioni (via CPU).",
    },
    "hashid": {
        "name": "hashID · identifica hash",
        "category": "Cracking", "mode": "interactive", "runtime": "termux", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: hashid \"5f4dcc3b5aa765d61d8327deb882cf99\"'; bash"],
        "catalog": True,
        "help": "Tipo: utility. Riconosce il tipo/algoritmo di un hash sconosciuto.",
    },
    "crunch": {
        "name": "Crunch · generatore wordlist",
        "category": "Cracking", "mode": "interactive", "runtime": "proot", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: crunch 6 8 abc123 -o wordlist.txt'; bash"],
        "catalog": True, "repo": "kali",
        "help": "Tipo: utility. Genera wordlist personalizzate per pattern/charset.",
    },
    "cewl": {
        "name": "CeWL · wordlist da sito",
        "category": "Cracking", "mode": "oneshot", "runtime": "proot", "target": "url",
        "cmd": ["cewl"], "anon_ok": True, "catalog": True, "repo": "kali",
        "help": "Tipo: utility. Crea una wordlist dalle parole presenti in un sito.",
    },
    # --- Exploitation ------------------------------------------------------
    "searchsploit": {
        "name": "SearchSploit · Exploit-DB",
        "category": "Exploitation", "mode": "interactive", "runtime": "proot", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: searchsploit apache 2.4'; bash"],
        "catalog": True, "repo": "kali", "pkg": "exploitdb",
        "help": "Tipo: ricerca exploit. Cerca exploit pubblici noti (Exploit-DB), offline.",
    },
    "enum4linux": {
        "name": "enum4linux · enum SMB",
        "category": "Exploitation", "mode": "oneshot", "runtime": "proot", "target": "host",
        "cmd": ["enum4linux", "-a"], "anon_ok": True, "catalog": True, "repo": "kali",
        "help": "Tipo: enumeration. Estrae info da server SMB/Windows (utenti, share).",
    },
    "medusa": {
        "name": "Medusa · brute force login",
        "category": "Exploitation", "mode": "interactive", "runtime": "proot", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: medusa -h 10.0.0.1 -u admin -P pass.txt -M ssh'; bash"],
        "catalog": True, "repo": "kali",
        "help": "Tipo: brute force. Login su servizi di rete (alternativa a Hydra).",
    },
    # --- Sistema / utility -------------------------------------------------
    "exiftool": {
        "name": "ExifTool · metadati file",
        "category": "Sistema", "mode": "interactive", "runtime": "termux", "target": None,
        "cmd": ["bash", "-lc", "echo 'Esempio: exiftool foto.jpg'; bash"],
        "catalog": True,
        "help": "Tipo: forense/OSINT. Legge e modifica i metadati di foto e file.",
    },
}


def inner_command(tool_id: str, target: str | None, anon: bool) -> list[str]:
    """Costruisce il comando "interno" del tool (senza il prefisso di runtime).

    Aggiunge il target validato e, se richiesto e supportato, il prefisso
    proxychains per instradare il traffico via Tor. Il prefisso di runtime
    (nulla per Termux, proot per Debian) lo aggiunge exec_prefix() nel server.
    Solleva ValueError su input non valido o richieste incoerenti.
    """
    tool = TOOLS.get(tool_id)
    if tool is None:
        raise ValueError("Tool sconosciuto.")

    cmd = list(tool["cmd"])
    if tool.get("target"):
        cmd.append(validate_target(tool["target"], target or ""))

    use_anon = tool.get("force_anon", False) or (anon and tool.get("anon_ok", False))
    if use_anon:
        if not tool.get("anon_ok"):
            raise ValueError("Questo tool non e' instradabile via Tor.")
        cmd = list(PROXYCHAINS) + cmd
    return cmd


# Binario da verificare per sapere se un tool e' realmente installato.
# I tool "native" non hanno binario: sono sempre disponibili.
BIN = {
    "nmap_quick": "nmap", "nmap_ping": "nmap", "whois": "whois", "dig": "dig",
    "whatweb": "whatweb", "nikto": "nikto", "dnsrecon": "dnsrecon", "wafw00f": "wafw00f",
    "sqlmap": "sqlmap", "wfuzz": "wfuzz", "metasploit": "msfconsole", "hydra": "hydra",
    "aircrack": "aircrack-ng", "john": "john", "tor_ip": "curl",
    "shell_anon": "proxychains4", "shell": "bash",
    # catalogo (extra, on-demand)
    "dnsenum": "dnsenum", "theharvester": "theHarvester", "wpscan": "wpscan",
    "gobuster": "gobuster", "dirb": "dirb", "commix": "commix",
    "hashcat": "hashcat", "hashid": "hashid", "crunch": "crunch", "cewl": "cewl",
    "searchsploit": "searchsploit", "enum4linux": "enum4linux", "medusa": "medusa",
    "exiftool": "exiftool",
}


def detection_targets() -> tuple[dict, dict]:
    """(termux_bins, proot_bins): {tool_id: binario} da verificare per runtime.

    Esclude i tool "native" (sempre disponibili). Usato dal server per marcare
    quali tool sono installati, cosi' la UI mostra un pulsante attivo per ognuno.
    """
    tb, pb = {}, {}
    for tid, t in TOOLS.items():
        if t.get("mode") == "native":
            continue
        b = BIN.get(tid)
        if not b:
            continue
        (tb if t.get("runtime") == "termux" else pb)[tid] = b
    return tb, pb


def exec_prefix(tool_id: str) -> list[str]:
    """Prefisso di esecuzione in base al runtime del tool.

    - "termux": nessun prefisso, il binario gira direttamente in Termux;
    - "proot" (o assente): il comando gira dentro il Debian minimale.
    I tool "native" non eseguono binari e non devono passare da qui.
    """
    tool = TOOLS.get(tool_id)
    if tool is None:
        raise ValueError("Tool sconosciuto.")
    return [] if tool.get("runtime") == "termux" else list(PROOT)


def tools_by_category() -> dict[str, list]:
    """Elenco dei tool per la UI, raggruppati per categoria."""
    out: dict[str, list] = {}
    for tid, t in TOOLS.items():
        out.setdefault(t["category"], []).append(
            {"id": tid, "name": t["name"], "mode": t["mode"],
             "runtime": t.get("runtime"),      # "termux" | "proot" | None (native)
             "bin": BIN.get(tid),              # binario da rilevare
             "pkg": t.get("pkg"),              # pacchetto da installare (se != bin)
             "repo": t.get("repo"),            # "kali" se serve il repo Kali nel Debian
             "catalog": t.get("catalog", False),   # tool extra, mostrato su richiesta
             "target": t["target"], "help": t.get("help", ""),
             "anon_ok": t.get("anon_ok", False), "force_anon": t.get("force_anon", False)}
        )
    return out


# --------------------------------------------------------------------------- #
# Validazione input
# --------------------------------------------------------------------------- #

# host / IP / hostname / CIDR
_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._:-]*[A-Za-z0-9])?(?:/\d{1,3})?$")
# url http(s)
_URL_RE = re.compile(r"^https?://[A-Za-z0-9._:-]+(?:/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?$")


def validate_target(kind: str, value: str) -> str:
    """Ritorna il target ripulito o solleva ValueError se non e' valido."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Target mancante.")
    if value.startswith("-"):
        raise ValueError("Target non valido (non puo' iniziare con '-').")
    if kind == "host" and _HOST_RE.match(value):
        return value
    if kind == "url" and _URL_RE.match(value):
        return value
    raise ValueError(f"Target non valido per il tipo '{kind}'.")
