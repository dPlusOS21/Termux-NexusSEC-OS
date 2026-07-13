#!/data/data/com.termux/files/usr/bin/bash
#
# install.sh - Bootstrap dell'ambiente "Termux-NexusSEC-OS"
#
# Strategia a TRE LIVELLI per ridurre lo spazio (~200-400 MB invece di ~2 GB):
#   1. Tool "native"  : niente da installare (rdap/whois via HTTP dal server).
#   2. Tool "termux"  : pacchetti nativi Termux (nmap, tor, hydra, john,
#                       aircrack-ng, sqlmap...) - eseguiti direttamente, veloci.
#   3. Tool "proot"   : un Debian MINIMALE via proot-distro, solo per i pochi
#                       tool non disponibili in Termux (whatweb, nikto).
#
# Metasploit e' pesante e non e' nei repo Debian standard: disattivato di
# default, abilitalo (installer ufficiale Rapid7 dentro il Debian) con:
#     INSTALL_METASPLOIT=yes ./install.sh
#
# Idempotente: puoi rilanciarlo, salta cio' che e' gia' fatto.

set -euo pipefail

DISTRO="debian"
INSTALL_METASPLOIT="${INSTALL_METASPLOIT:-no}"

log()  { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; }

# --- 0. Controllo di essere davvero in Termux -------------------------------
if [ -z "${PREFIX:-}" ] || [ ! -d "/data/data/com.termux" ]; then
    err "Questo script va eseguito dentro Termux."
    exit 1
fi

# Installa un pacchetto Termux "best-effort": avvisa ma non interrompe se manca.
pkg_try() {
    if pkg install -y "$1" >/dev/null 2>&1; then
        log "  ok: $1"
    else
        warn "  non installato: $1 (repo non disponibile su questa versione di Termux)"
        MISSING="${MISSING:-} $1"
    fi
}

# --- 1. Base Termux (repo main: deve funzionare) ----------------------------
log "Aggiorno i pacchetti di Termux..."
pkg update -y && pkg upgrade -y

log "Installo i pacchetti base (proot-distro, python, ttyd, git)..."
pkg install -y proot-distro python ttyd git

log "Installo i tool nativi di rete/anonimato (nmap, tor, proxychains, whois, dig)..."
pkg install -y nmap tor proxychains-ng whois curl dnsutils

# --- 2. Tool Termux "extra" (root-repo: best-effort) ------------------------
log "Abilito root-repo e installo i cracker/scanner nativi..."
pkg install -y root-repo >/dev/null 2>&1 || warn "root-repo non abilitato (continuo)"
MISSING=""
for t in hydra john aircrack-ng sqlmap; do
    pkg_try "$t"
done

# --- 3. Dipendenze Python del ponte -----------------------------------------
log "Installo FastAPI + uvicorn (il ponte web)..."
python -m pip install --upgrade pip
python -m pip install "fastapi" "uvicorn[standard]"

# sqlmap: se il pacchetto Termux non c'e', ripiego su pip (e' puro Python).
if ! command -v sqlmap >/dev/null 2>&1; then
    warn "sqlmap non trovato come pacchetto: provo via pip..."
    python -m pip install sqlmap >/dev/null 2>&1 && log "  ok: sqlmap (pip)" \
        || warn "  sqlmap non installato: puoi aggiungerlo dopo con 'pip install sqlmap'"
fi

# --- 4. proxychains di Termux (instrada il TCP via Tor su 127.0.0.1:9050) ----
log "Configuro proxychains di Termux..."
cat > "$PREFIX/etc/proxychains.conf" <<EOF
# Generato da install.sh (Termux-NexusSEC-OS) - instrada il TCP via Tor
strict_chain
proxy_dns
remote_dns_subnet 224
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5 127.0.0.1 9050
EOF

# --- 5. Debian minimale in proot (solo per whatweb / nikto) -----------------
if proot-distro login "$DISTRO" -- true >/dev/null 2>&1; then
    log "Debian ($DISTRO) risulta gia' installato, salto il download."
else
    log "Installo Debian minimale ($DISTRO) via proot-distro (~150-300 MB)..."
    proot-distro install "$DISTRO"
fi

log "Aggiorno gli indici dei pacchetti dentro Debian..."
proot-distro login "$DISTRO" -- apt-get update -y

log "Installo whatweb + nikto (Ruby/Perl, non nativi in Termux)..."
# proxychains4 anche dentro Debian: permette l'anonimato per whatweb/nikto.
proot-distro login "$DISTRO" -- apt-get install -y --no-install-recommends \
    whatweb nikto proxychains4 ca-certificates curl

# Tool Debian "extra" (best-effort: se un pacchetto non c'e', avvisa e prosegue).
log "Installo i tool Debian extra (dnsrecon, wafw00f, wfuzz)..."
for t in dnsrecon wafw00f wfuzz; do
    if proot-distro login "$DISTRO" -- apt-get install -y --no-install-recommends "$t" >/dev/null 2>&1; then
        log "  ok: $t"
    else
        warn "  non installato: $t (non nei repo Debian di questa versione)"
        MISSING="${MISSING:-} $t"
    fi
done

log "Configuro proxychains dentro Debian..."
proot-distro login "$DISTRO" -- bash -c 'cat > /etc/proxychains4.conf <<EOF
# Generato da install.sh (Termux-NexusSEC-OS) - instrada il TCP via Tor
strict_chain
proxy_dns
remote_dns_subnet 224
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5 127.0.0.1 9050
EOF'

# --- 6. Metasploit opzionale (installer ufficiale Rapid7 dentro Debian) -----
if [ "$INSTALL_METASPLOIT" = "yes" ]; then
    log "Installo Metasploit Framework dentro Debian (pesante, puo' fallire su arm64)..."
    proot-distro login "$DISTRO" -- bash -c '
        set -e
        curl -fsSL https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb -o /usr/local/bin/msfinstall
        chmod +x /usr/local/bin/msfinstall
        /usr/local/bin/msfinstall
    ' || warn "Installazione di Metasploit fallita (arch non supportata o rete). Puoi riprovare dopo."
else
    warn "Metasploit NON installato. Per aggiungerlo: INSTALL_METASPLOIT=yes ./install.sh"
fi

# --- 7. Fine ----------------------------------------------------------------
log "Installazione completata."
if [ -n "${MISSING# }" ]; then
    warn "Tool Termux non installati:${MISSING}. Il resto funziona lo stesso."
fi
echo
echo "Per avviare l'interfaccia:"
echo "    python server.py"
echo "Poi apri nel browser del telefono:  http://127.0.0.1:8000"
