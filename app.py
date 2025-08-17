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
    "num_squadre": 10,
    "crediti": 700,
    "quote_rosa": QUOTE_ROSA.copy(),
    "no_doppioni": True,  # un giocatore può appartenere ad una sola squadra
    "spending_targets": {"P": 0.10, "D": 0.20, "C": 0.30, "A": 0.40},
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
ROLE_LABELS = {"P": "Porta", "D": "Difesa", "C": "Centrocampo", "A": "Attacco"}

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
            "user_team_idx": st.session_state.get("user_team_idx", st.session_state.get("my_team_idx", 0)),
        }
        PERSIST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # evita crash se il file non è scrivibile

def load_state():
    try:
        if PERSIST_PATH.exists():
            data = json.loads(PERSIST_PATH.read_text(encoding="utf-8"))
            st.session_state.settings = data.get("settings", SETTINGS.copy())
            st.session_state.settings.setdefault("spending_targets", {"P": 0.10, "D": 0.20, "C": 0.30, "A": 0.40})
            st.session_state.squadre = [Squadra.from_dict(d) for d in data.get("squadre", [])]
            st.session_state.storico_acquisti = data.get("storico", [])
            st.session_state.my_team_idx = data.get("my_team_idx", 0)
            st.session_state.user_team_idx = data.get("user_team_idx", st.session_state.my_team_idx)
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
        st.session_state.user_team_idx = default_idx
        save_state()
    # Allinea il numero di squadre alla nuova regola (10)
    desired = 10
    if st.session_state.settings.get("num_squadre") != desired:
        st.session_state.settings["num_squadre"] = desired
    # Aggiungi squadre mancanti se servono (non rimuove se >10)
    if len(st.session_state.squadre) < desired:
        start_i = len(st.session_state.squadre)
        for i in range(start_i, desired):
            nome = "Terzetto Scherzetto" if i == 0 else f"Squadra {i+1}"
            st.session_state.squadre.append(Squadra(nome, st.session_state.settings["crediti"]))
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


def spesa_per_ruolo(team: Squadra) -> Dict[str, int]:
    return {r: sum(g.prezzo for g in team.rosa[r]) for r in RUOLI}


def target_per_ruolo(team: Squadra) -> Dict[str, int]:
    perc = st.session_state.settings.get("spending_targets", {"P": 0.10, "D": 0.20, "C": 0.30, "A": 0.40})
    return {r: int(round(team.budget * perc.get(r, 0))) for r in RUOLI}


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
    except Exception as e:
        raise RuntimeError(f"Errore lettura file Drive: {e}")

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
# LOOKUP SLOT PER GIOCATORE (da fogli Excel)
# ===============================
@st.cache_data(show_spinner=False)
def build_slot_lookup() -> Dict[str, str]:
    mapping = {}
    for sheet in RUOLI:
        try:
            df = load_sheet_from_drive(sheet)
            if df is None or df.empty:
                continue
            cols_lower = {c.lower(): c for c in df.columns}
            name_col = cols_lower.get('name')
            slot_col = cols_lower.get('slot')
            if not name_col or not slot_col:
                continue
            for _, row in df[[name_col, slot_col]].dropna(subset=[name_col]).iterrows():
                name_str = str(row[name_col]).strip().upper()
                slot_val = row[slot_col]
                if pd.isna(slot_val) or str(slot_val).strip() == "":
                    continue
                mapping[f"{sheet}|{name_str}"] = str(slot_val)
        except Exception:
            continue
    return mapping


def get_slot_for(nome: str, ruolo: str):
    try:
        return build_slot_lookup().get(f"{ruolo}|{str(nome).strip().upper()}")
    except Exception:
        return None

# ===============================
# FOOTER
# ===============================
st.markdown("---")
st.caption("Doppioni disattivati per design: un giocatore può appartenere a una sola squadra.")

