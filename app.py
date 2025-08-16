import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict
from pathlib import Path

import pandas as pd
import streamlit as st

# ===============================
# CONFIG APP
# ===============================
st.set_page_config(
    page_title="Fantacalcio – Gestore Lega",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===============================
# COSTANTI & SETTINGS (bloccati da codice)
# ===============================
RUOLI = ["P", "D", "C", "A"]
QUOTE_ROSA = {"P": 3, "D": 8, "C": 8, "A": 6}
SETTINGS = {
    "num_squadre": 9,
    "crediti": 700,
    "quote_rosa": QUOTE_ROSA.copy(),
    "no_doppioni": True,  # un giocatore può appartenere ad una sola squadra
}

# Google Drive: file Excel con i fogli P/D/C/A e colonna "name"
FILE_ID = "1fbDUNKOmuxsJ_BAd7Sgm-V4tO5UkXXLE"
DRIVE_XLSX_URL = f"https://drive.google.com/uc?export=download&id={FILE_ID}"

# Campi da visualizzare nella card giocatore (case-insensitive)
FIELD_LABELS = {
    "team": "Squadra",
    "slot": "Slot",
    "fasciafc": "Fascia",
    "pfcrange": "Range Stimato",
    "expectedfantamedia": "Fantamedia Stimata",
}
NAME_COL = "name"  # colonna con il nome del calciatore

# ===============================
# DATA MODEL
# ===============================
@dataclass
class Giocatore:
    nome: str
    ruolo: str
    prezzo: int

@dataclass
class Squadra:
    nome: str
    budget: int
    rosa: Dict[str, List[Giocatore]] = field(default_factory=lambda: {r: [] for r in RUOLI})

    def to_dict(self):
        return {
            "nome": self.nome,
            "budget": self.budget,
            "rosa": {r: [asdict(g) for g in self.rosa[r]] for r in RUOLI},
        }

    @staticmethod
    def from_dict(d: dict) -> "Squadra":
        s = Squadra(d["nome"], d["budget"]) 
        s.rosa = {r: [Giocatore(**g) for g in d.get("rosa", {}).get(r, [])] for r in RUOLI}
        return s

# ===============================
# PERSISTENZA SU FILE (memoria fino al reboot)
# ===============================
PERSIST_PATH = Path("lega_state.json")

def save_state():
    try:
        payload = {
            "settings": st.session_state.get("settings", SETTINGS.copy()),
            "squadre": [s.to_dict() for s in st.session_state.get("squadre", [])],
            "storico": st.session_state.get("storico_acquisti", []),
            "my_team_idx": st.session_state.get("my_team_idx", 0),
        }
        PERSIST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # evita crash se il file non è scrivibile

def load_state():
    try:
        if PERSIST_PATH.exists():
            data = json.loads(PERSIST_PATH.read_text(encoding="utf-8"))
            st.session_state.settings = data.get("settings", SETTINGS.copy())
            st.session_state.squadre = [Squadra.from_dict(d) for d in data.get("squadre", [])]
            st.session_state.storico_acquisti = data.get("storico", [])
            st.session_state.my_team_idx = data.get("my_team_idx", 0)
            return True
    except Exception:
        pass
    return False

# ===============================
# STATO INIZIALE (bootstrap una sola volta)
# ===============================
if "_boot" not in st.session_state:
    loaded = load_state()
    if not loaded:
        # Settings fissi
        st.session_state.settings = SETTINGS.copy()
        # Squadre di default
        def _init_default_squadre() -> List[Squadra]:
            arr = []
            for i in range(st.session_state.settings["num_squadre"]):
                nome = "Terzetto Scherzetto" if i == 0 else f"Squadra {i+1}"
                arr.append(Squadra(nome, st.session_state.settings["crediti"]))
            return arr
        st.session_state.squadre = _init_default_squadre()
        st.session_state.storico_acquisti = []
        # Segui di default Terzetto Scherzetto
        default_idx = 0
        for i, t in enumerate(st.session_state.squadre):
            if t.nome == "Terzetto Scherzetto":
                default_idx = i
                break
        st.session_state.my_team_idx = default_idx
        save_state()
    st.session_state._boot = True

# ===============================
# FUNZIONI LEGA
# ===============================

def quote_rimaste(team: Squadra) -> Dict[str, int]:
    return {r: st.session_state.settings["quote_rosa"][r] - len(team.rosa[r]) for r in RUOLI}


def rosa_completa(team: Squadra) -> bool:
    return all(len(team.rosa[r]) >= st.session_state.settings["quote_rosa"][r] for r in RUOLI)


def crediti_rimasti(team: Squadra) -> int:
    spesi = sum(g.prezzo for r in RUOLI for g in team.rosa[r])
    return team.budget - spesi


def elenco_giocatori_global() -> List[str]:
    return [g.nome for team in st.session_state.squadre for r in RUOLI for g in team.rosa[r]]


def aggiungi_giocatore(team: Squadra, nome: str, ruolo: str, prezzo: int) -> bool:
    if not nome.strip() or ruolo not in RUOLI or prezzo < 0:
        return False
    if st.session_state.settings["no_doppioni"] and nome in elenco_giocatori_global():
        return False
    if quote_rimaste(team)[ruolo] <= 0:
        return False
    if crediti_rimasti(team) < prezzo:
        return False
    team.rosa[ruolo].append(Giocatore(nome.strip(), ruolo, prezzo))
    st.session_state.storico_acquisti.append({
        "squadra": team.nome,
        "giocatore": nome.strip(),
        "ruolo": ruolo,
        "prezzo": prezzo,
    })
    save_state()
    return True


def rimuovi_giocatore(team: Squadra, ruolo: str, giocatore_nome: str) -> bool:
    elenco = team.rosa[ruolo]
    for i, g in enumerate(elenco):
        if g.nome == giocatore_nome:
            elenco.pop(i)
            save_state()
            return True
    return False

# ===============================
# FUNZIONI DATI GDRIVE
# ===============================
@st.cache_data(show_spinner=False)
def load_sheet_from_drive(sheet_name: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(DRIVE_XLSX_URL, sheet_name=sheet_name)
        return df
    except ImportError:
        raise RuntimeError("Per leggere file Excel è necessario installare 'openpyxl' (pip install openpyxl)")

@st.cache_data(show_spinner=False)
def rotate_from_letter(df: pd.DataFrame, col_name: str, letter: str) -> pd.DataFrame:
    if col_name not in df.columns:
        return df
    base = df.sort_values(col_name, key=lambda s: s.astype(str).str.upper()).reset_index(drop=True)
    if not letter or len(letter) != 1 or not letter.isalpha():
        return base
    initials = base[col_name].astype(str).str.strip().str.upper().str[0]
    letter = letter.upper()
    alphabet = [chr(c) for c in range(ord('A'), ord('Z')+1)]
    order = alphabet[alphabet.index(letter):] + alphabet[:alphabet.index(letter)]
    frames = [base[initials == ch] for ch in order]
    rotated = pd.concat(frames, ignore_index=True)
    rotated = pd.concat([rotated, base[~initials.isin(alphabet)]], ignore_index=True)
    return rotated

# ===============================
# AUTO REFRESH (ogni tot secondi, invisibile)
# ===============================
# Valori di default (non esposti a UI, restano in memoria finché non riavvii)
if "settings" in st.session_state:
    st.session_state.settings.setdefault("auto_refresh_enabled", True)
    st.session_state.settings.setdefault("auto_refresh_ms", 5000)  # 5 secondi


def apply_auto_refresh():
    """Forza il rerun della pagina automaticamente ogni N ms.
    Usa streamlit-autorefresh se disponibile, altrimenti fallback JS.
    """
    enabled = st.session_state.settings.get("auto_refresh_enabled", True)
    interval_ms = int(st.session_state.settings.get("auto_refresh_ms", 5000))
    if not enabled:
        return
    try:
        from streamlit_autorefresh import st_autorefresh  # type: ignore
        st_autorefresh(interval=interval_ms, key="auto_refresh")
    except Exception:
        # Fallback senza dipendenze
        st.markdown(
            f"<script>setTimeout(function(){{window.location.reload();}}, {interval_ms});</script>",
            unsafe_allow_html=True,
        )

# Applica subito l'auto refresh
apply_auto_refresh()

# ===============================
# UI: SIDEBAR – RIEPILOGO (aggiornato in tempo reale)
# ===============================
with st.sidebar:
    st.title("📋 Riepilogo Squadra")

    st.session_state.my_team_idx = min(st.session_state.my_team_idx, len(st.session_state.squadre)-1)
    idx_options = list(range(len(st.session_state.squadre)))
    sel_idx = st.selectbox(
        "Segui squadra",
        idx_options,
        index=st.session_state.my_team_idx,
        format_func=lambda i: st.session_state.squadre[i].nome,
    )
    st.session_state.my_team_idx = sel_idx
    my_team = st.session_state.squadre[sel_idx] if st.session_state.squadre else None

    if my_team:
        st.metric("Crediti rimasti", crediti_rimasti(my_team))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("P", f"{len(my_team.rosa['P'])}/{st.session_state.settings['quote_rosa']['P']}")
        c2.metric("D", f"{len(my_team.rosa['D'])}/{st.session_state.settings['quote_rosa']['D']}")
        c3.metric("C", f"{len(my_team.rosa['C'])}/{st.session_state.settings['quote_rosa']['C']}")
        c4.metric("A", f"{len(my_team.rosa['A'])}/{st.session_state.settings['quote_rosa']['A']}")
        st.markdown("---")
        for r, label in [("P","Portieri"),("D","Difensori"),("C","Centrocampisti"),("A","Attaccanti")]:
            names = [f"{g.nome} ({g.prezzo})" for g in my_team.rosa[r]]
            if names:
                st.markdown(f"**{label}**")
                for n in names:
                    st.write("• ", n)
            else:
                st.markdown(f"**{label}**: _nessuno_")
        st.markdown("---")
        spesi = my_team.budget - crediti_rimasti(my_team)
        st.caption(f"Budget iniziale: {my_team.budget} • Spesi: {spesi}")

# ===============================
# UI: HEADER
# ===============================
st.title("Fantacalcio – Gestore Lega")
st.caption("Impostazioni fissate da codice: 9 squadre, 700 crediti, rosa 3P/8D/8C/6A, doppioni NON consentiti.")

# ===============================
# UI: ASTA – RUOLO & LETTERA
# ===============================
col_a, col_b = st.columns([1,1])
with col_a:
    st.subheader("Ruolo in asta")
    ruolo_asta = st.radio(
        "Seleziona il ruolo per cui si sta svolgendo l'asta",
        RUOLI,
        index=0,
        horizontal=True,
        key="ruolo_asta",
    )
with col_b:
    st.subheader("Lettera estratta")
    lettera_input = st.text_input(
        "Inserisci la lettera alfabetica estratta (A–Z)",
        value=st.session_state.get("lettera_estratta", ""),
        max_chars=1,
    )
    st.session_state["lettera_estratta"] = (lettera_input or "").upper()

# ===============================
# UI: CARD GIOCATORE – UNO ALLA VOLTA CON ASSEGNAZIONE DIRETTA
# ===============================
st.markdown("### 🎠 Calciatori (uno alla volta, in ordine dalla lettera estratta)")
try:
    df_raw = load_sheet_from_drive(ruolo_asta)
    if df_raw.empty:
        st.warning(f"Il foglio '{ruolo_asta}' è vuoto.")
    else:
        if NAME_COL not in df_raw.columns:
            st.error(f"Nel foglio '{ruolo_asta}' non esiste la colonna '{NAME_COL}'.")
        else:
            df_view = rotate_from_letter(df_raw, NAME_COL, st.session_state.get("lettera_estratta", ""))
            df_view[NAME_COL] = df_view[NAME_COL].astype(str).fillna("").str.strip()

            key_idx = f"car_idx_{ruolo_asta}"
            if key_idx not in st.session_state:
                st.session_state[key_idx] = 0
            total = len(df_view)

            # NAV
            c_nav1, c_nav2, c_nav3 = st.columns([1,3,1])
            with c_nav1:
                if st.button("◀︎", use_container_width=True, key=f"prev_{ruolo_asta}"):
                    st.session_state[key_idx] = max(0, st.session_state[key_idx] - 1)
            with c_nav2:
                st.write(f"Mostrato {st.session_state[key_idx]+1} di {total}")
            with c_nav3:
                if st.button("▶︎", use_container_width=True, key=f"next_{ruolo_asta}"):
                    st.session_state[key_idx] = min(total-1, st.session_state[key_idx] + 1)

            idx = st.session_state[key_idx]
            rec = df_view.iloc[idx]

            # CARD
            with st.container(border=True):
                st.subheader(rec[NAME_COL])
                st.caption(f"Ruolo: {ruolo_asta}")

                # Mostra SOLO i campi richiesti (case-insensitive)
                cols_lower = {c.lower(): c for c in df_view.columns}
                for key_lower, label in FIELD_LABELS.items():
                    real_col = cols_lower.get(key_lower)
                    if not real_col:
                        continue
                    val = rec[real_col]
                    if pd.isna(val) or str(val).strip() == "":
                        continue
                    st.write(f"**{label}**: {val}")

                st.markdown("---")
                st.subheader("📝 Assegna a squadra")
                team_options = list(range(len(st.session_state.squadre)))
                sel_team_idx = st.selectbox(
                    "Scegli squadra",
                    team_options,
                    index=min(st.session_state.my_team_idx, len(team_options)-1) if team_options else 0,
                    format_func=lambda i: st.session_state.squadre[i].nome if team_options else "",
                    key=f"sel_team_{ruolo_asta}_{idx}"
                )
                prezzo_sel = st.number_input("Prezzo di aggiudicazione", min_value=0, step=1, key=f"prezzo_{ruolo_asta}_{idx}")
                if st.button("Aggiungi alla squadra", key=f"add_{ruolo_asta}_{idx}"):
                    if st.session_state.squadre:
                        team_sel = st.session_state.squadre[sel_team_idx]
                        ok = aggiungi_giocatore(team_sel, rec[NAME_COL], ruolo_asta, int(prezzo_sel))
                        if ok:
                            st.success(f"{rec[NAME_COL]} aggiunto a {team_sel.nome} per {int(prezzo_sel)}.")
                            st.session_state[key_idx] = min(total-1, st.session_state[key_idx]+1)
                        else:
                            st.error("Impossibile aggiungere il giocatore: controlla crediti/quote/doppioni.")

except Exception as e:
    st.error(str(e))

# ===============================
# UI: TABS PRINCIPALI
# ===============================
tab_riepilogo, tab_acquisti, tab_nomi = st.tabs(["📊 Riepilogo", "🛒 Acquisti", "✏️ Nomi"])

with tab_riepilogo:
    for team in st.session_state.squadre:
        with st.expander(f"{team.nome} – Crediti rimasti: {crediti_rimasti(team)}", expanded=False):
            st.write("Portieri:", [g.nome for g in team.rosa["P"]])
            st.write("Difensori:", [g.nome for g in team.rosa["D"]])
            st.write("Centrocampisti:", [g.nome for g in team.rosa["C"]])
            st.write("Attaccanti:", [g.nome for g in team.rosa["A"]])

with tab_acquisti:
    nome_g = st.text_input("Nome giocatore")
    ruolo_g = st.selectbox("Ruolo", RUOLI)
    prezzo_g = st.number_input("Prezzo", min_value=0, step=1)
    dest_name = st.selectbox("Squadra", [t.nome for t in st.session_state.squadre])
    if st.button("Aggiungi"):
        team = next(t for t in st.session_state.squadre if t.nome == dest_name)
        if aggiungi_giocatore(team, nome_g, ruolo_g, int(prezzo_g)):
            st.success(f"{nome_g} aggiunto a {team.nome}.")
        else:
            st.error("Impossibile aggiungere il giocatore.")

    squadra_r = st.selectbox("Squadra per rimuovere", [t.nome for t in st.session_state.squadre])
    ruolo_r = st.selectbox("Ruolo da cui rimuovere", RUOLI)
    team_r = next(t for t in st.session_state.squadre if t.nome == squadra_r)
    gioc_r = st.selectbox("Giocatore", [g.nome for g in team_r.rosa[ruolo_r]] if team_r.rosa[ruolo_r] else ["—"])
    if st.button("Rimuovi"):
        if gioc_r != "—" and rimuovi_giocatore(team_r, ruolo_r, gioc_r):
            st.success(f"{gioc_r} rimosso da {team_r.nome}.")
        else:
            st.error("Impossibile rimuovere il giocatore.")

with tab_nomi:
    for i, team in enumerate(st.session_state.squadre):
        nuovo_nome = st.text_input(f"Nome squadra {i+1}", value=team.nome, key=f"nome_{i}")
        if nuovo_nome.strip() and nuovo_nome != team.nome:
            altri_nomi = {t.nome for j, t in enumerate(st.session_state.squadre) if j != i}
            if nuovo_nome in altri_nomi:
                st.warning(f"Il nome '{nuovo_nome}' è già in uso.")
            else:
                team.nome = nuovo_nome
                st.success(f"Nome aggiornato: {team.nome}")
                save_state()

st.markdown("---")
st.caption("Doppioni disattivati per design: un giocatore può appartenere a una sola squadra.")
