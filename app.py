import re
import json
import unicodedata
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
    # Target personali (solo per Terzetto Scherzetto)
    "spending_targets": {"P": 0.10, "D": 0.20, "C": 0.30, "A": 0.40},
}

# Google Drive: file Excel con i fogli P/D/C/A e colonna "name"
FILE_ID = "1fbDUNKOmuxsJ_BAd7Sgm-V4tO5UkXXLE"
DRIVE_XLSX_URL = f"https://drive.google.com/uc?export=download&id={FILE_ID}"

# Secondo file (Tutti): extra metrics (Qt.A, FVM)
FILE2_ID = "1e-0iZhQsavd5_G_KM1ePSXzCJgG0Kn-v"
DRIVE2_XLSX_URL = f"https://drive.google.com/uc?export=download&id={FILE2_ID}"
SHEET2_NAME = "Tutti"

# Campi visibili nella card giocatore (case-insensitive)
FIELD_LABELS = {
    "team": "Squadra",
    "slot": "Slot",
    "fasciafc": "Fascia",
    "pfcrange": "Range Stimato",
    "expectedfantamedia": "Fantamedia Stimata",
}
NAME_COL = "name"  # colonna con il nome del calciatore nel file 1
ROLE_LABELS = {"P": "Porta", "D": "Difesa", "C": "Centrocampo", "A": "Attacco"}

# ===============================
# UTILS DI NORMALIZZAZIONE
# ===============================
def strip_accents(s: str) -> str:
    try:
        s = unicodedata.normalize("NFKD", str(s))
        return s.encode("ascii", "ignore").decode("ascii")
    except Exception:
        return str(s)

def norm_name(s: str) -> str:
    """Normalizza un nome: rimuove accenti, punteggiatura, spazi multipli, lowercase.
    Utile per lookup Slot dal file 1.
    """
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def name_key(s: str) -> str:
    """Chiave robusta per confrontare i nomi tra file 1 e file 2.
    - rimuove accenti
    - minuscolo
    - tiene solo [a-z0-9] (spazi/punteggiatura rimossi) → es. "De Gea" → "degea"
    """
    try:
        s = unicodedata.normalize("NFKD", str(s))
        s = s.encode("ascii", "ignore").decode("ascii")
    except Exception:
        s = str(s)
    s = s.lower()
    return "".join(ch for ch in s if ch.isalnum())

def canon_colname(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

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
        pass

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
        st.session_state.settings = SETTINGS.copy()
        def _init_default_squadre() -> List[Squadra]:
            arr = []
            for i in range(st.session_state.settings["num_squadre"]):
                nome = "Terzetto Scherzetto" if i == 0 else f"Squadra {i+1}"
                arr.append(Squadra(nome, st.session_state.settings["crediti"]))
            return arr
        st.session_state.squadre = _init_default_squadre()
        st.session_state.storico_acquisti = []
        default_idx = 0
        for i, t in enumerate(st.session_state.squadre):
            if t.nome == "Terzetto Scherzetto":
                default_idx = i
                break
        st.session_state.my_team_idx = default_idx
        st.session_state.user_team_idx = default_idx
        save_state()
    desired = 10
    if st.session_state.settings.get("num_squadre") != desired:
        st.session_state.settings["num_squadre"] = desired
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
# FUNZIONI DATI GDRIVE (file ruolo P/D/C/A)
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

# Helper: parse range stimato (es. '32-48' → (32,48))
def parse_pfcrange_cell(val):
    try:
        if val is None:
            return (None, None)
        s = str(val)
        nums, buf = [], ''
        for ch in s:
            if ch.isdigit():
                buf += ch
            else:
                if buf:
                    nums.append(int(buf)); buf=''
        if buf:
            nums.append(int(buf))
        if len(nums) >= 2:
            a,b = nums[0], nums[1]
            return (a,b) if a<=b else (b,a)
        if len(nums) == 1:
            return (nums[0], nums[0])
        return (None, None)
    except Exception:
        return (None, None)

# ===============================
# LOOKUP SLOT PER GIOCATORE (da fogli Excel ruolo)
# ===============================
@st.cache_data(show_spinner=False)
def build_slot_lookup() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
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
                name_str = norm_name(row[name_col])
                slot_val = row[slot_col]
                if pd.isna(slot_val) or str(slot_val).strip() == "":
                    continue
                mapping[f"{sheet}|{name_str}"] = str(slot_val)
        except Exception:
            continue
    return mapping

def get_slot_for(nome: str, ruolo: str):
    try:
        return build_slot_lookup().get(f"{ruolo}|{norm_name(nome)}")
    except Exception:
        return None

# ===============================
# DATI EXTRA (file 'Tutti'): Qt.A, FVM
# ===============================
@st.cache_data(show_spinner=False)
def load_all_extra_df() -> pd.DataFrame:
    try:
        df = pd.read_excel(DRIVE2_XLSX_URL, sheet_name=SHEET2_NAME)
        return df
    except ImportError:
        raise RuntimeError("Per leggere file Excel è necessario installare 'openpyxl' (pip install openpyxl)")
    except Exception as e:
        raise RuntimeError(f"Errore lettura file Drive (Tutti): {e}")

@st.cache_data(show_spinner=False)
def build_extra_index() -> Dict[str, Dict[str, object]]:
    """Crea mapping dal file 2 (sheet 'Tutti') usando **esattamente**:
    - Ruolo dalla colonna "R" (prima lettera)
    - Nome dalla colonna "Nome"
    Chiave: "R|name_key(Nome)" → {"Qt.A", "FVM"}
    """
    mapping: Dict[str, Dict[str, object]] = {}
    try:
        df = load_all_extra_df()
        if df is None or df.empty:
            return mapping
        def find_col(targets):
            tset = {str(t).strip().lower() for t in targets}
            for c in df.columns:
                if str(c).strip().lower() in tset:
                    return c
            return None
        nome_col = find_col(["Nome"]) or find_col(["name"])  # fallback prudenziale
        ruolo_col = find_col(["R"])  # obbligatoria
        qta_col  = find_col(["Qt.A", "Qt A", "QTA"])
        fvm_col  = find_col(["FVM"])
        if not nome_col or not ruolo_col:
            return mapping
        name_keys = df[nome_col].astype(str).map(name_key)
        role_first = df[ruolo_col].astype(str).str.strip().str.upper().str[:1]
        for i, row in df.iterrows():
            r = role_first.iloc[i]
            if r not in RUOLI:
                continue
            key = f"{r}|{name_keys.iloc[i]}"
            mapping[key] = {
                "Qt.A": (row[qta_col] if qta_col in df.columns else None) if qta_col else None,
                "FVM": (row[fvm_col] if fvm_col in df.columns else None) if fvm_col else None,
            }
        return mapping
    except Exception:
        return mapping

def get_all_metrics(ruolo: str, nome: str) -> Dict[str, object]:
    try:
        idx = build_extra_index()
        key = f"{(ruolo or '').strip().upper()[:1]}|{name_key(nome)}"
        return idx.get(key, {})
    except Exception:
        return {}

# ===============================
# COLORI % TARGET (barre verdi→rosse)
# ===============================
def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))

def _lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))

def ratio_color_hex(r: float) -> str:
    r = _clamp01(r)
    g_col = (0, 170, 0)   # verde
    r_col = (220, 0, 0)   # rosso
    rr = _lerp(g_col[0], r_col[0], r)
    gg = _lerp(g_col[1], r_col[1], r)
    bb = _lerp(g_col[2], r_col[2], r)
    return f"#{rr:02X}{gg:02X}{bb:02X}"

# ===============================
# AUTO REFRESH (ogni tot secondi, invisibile)
# ===============================
if "settings" in st.session_state:
    st.session_state.settings.setdefault("auto_refresh_enabled", True)
    st.session_state.settings.setdefault("auto_refresh_ms", 5000)

def apply_auto_refresh():
    enabled = st.session_state.settings.get("auto_refresh_enabled", True)
    interval_ms = int(st.session_state.settings.get("auto_refresh_ms", 5000))
    if not enabled:
        return
    try:
        from streamlit_autorefresh import st_autorefresh  # type: ignore
        st_autorefresh(interval=interval_ms, key="auto_refresh")
    except Exception:
        st.markdown(
            f"<script>setTimeout(function(){{window.location.reload();}}, {interval_ms});</script>",
            unsafe_allow_html=True,
        )

apply_auto_refresh()

# ===============================
# UI: SIDEBAR – RIEPILOGO (solo Terzetto Scherzetto)
# ===============================
with st.sidebar:
    idx = st.session_state.get("user_team_idx", 0)
    idx = min(idx, len(st.session_state.squadre)-1)
    my_team = st.session_state.squadre[idx] if st.session_state.squadre else None

    st.title(f"📋 {my_team.nome if my_team else 'Rosa'}")

    if my_team:
        st.metric("Crediti rimasti", crediti_rimasti(my_team))
        st.markdown("---")
        spent_map = spesa_per_ruolo(my_team)
        targ_map = target_per_ruolo_dynamic(my_team)
        for r, label in [("P","Portieri"),("D","Difensori"),("C","Centrocampisti"),("A","Attaccanti")]:
            count = len(my_team.rosa[r])
            quota = st.session_state.settings['quote_rosa'][r]
            s = spent_map.get(r, 0)
            t = max(targ_map.get(r, 0), 1)
            ratio = s / t
            pct_int = int(round(100*ratio))
            pct_color = ratio_color_hex(min(ratio,1.0))
            badge_html = f" <span style='background:#DC2626;color:#fff;border-radius:12px;padding:2px 6px;margin-left:6px;'>+{s - t}</span>" if s > t else ""
            header_html = f"<strong>{label} ({count}/{quota}) — {s}/{t} (<span style='color:{pct_color}'>{pct_int}%</span>)</strong>{badge_html}"

            items = []
            for g in my_team.rosa[r]:
                _slot = get_slot_for(g.nome, r)
                if _slot:
                    items.append(f"{g.nome} — Slot: {_slot} ({g.prezzo})")
                else:
                    items.append(f"{g.nome} ({g.prezzo})")
            items_html = "<ul style='margin:6px 0 0 18px;padding:0;'>" + "".join(f"<li>{n}</li>" for n in items) + "</ul>" if items else "<em>nessuno</em>"

            bar_color = ratio_color_hex(min(ratio,1.0))
            width_pct = int(round(min(ratio,1.0)*100))
            border_col = "#FCA5A5" if s > t else "#E5E7EB"
            bg_col = "#FFF6F6" if s > t else "transparent"

            wrapper_html = f"""
            <div style='border:1px solid {border_col}; padding:8px 10px; border-radius:10px; margin-bottom:10px; background:{bg_col};'>
              {header_html}
              <div style='margin-top:6px;background:#eee;width:100%;height:8px;border-radius:6px;overflow:hidden;'>
                <div style='width:{width_pct}%;height:100%;background:{bar_color};'></div>
              </div>
              <div style='margin-top:6px;'>{items_html}</div>
            </div>
            """
            st.markdown(wrapper_html, unsafe_allow_html=True)

        st.markdown("---")
        spesi = my_team.budget - crediti_rimasti(my_team)
        st.caption(f"Budget iniziale: {my_team.budget} • Spesi: {spesi}")

# ===============================
# UI: HEADER + TABS IN ALTO
# ===============================
st.title("Fantacalcio – Gestore Lega")
st.caption(f"Impostazioni fissate da codice: {st.session_state.settings['num_squadre']} squadre, {st.session_state.settings['crediti']} crediti, rosa 3P/8D/8C/6A, doppioni NON consentiti.")

# Ordine: Asta come tab predefinito
tab_asta, tab_call, tab_riepilogo, tab_acquisti, tab_nomi = st.tabs([
    "🔨 Asta", "📞 Giocatore a chiamata", "📊 Riepilogo", "🛒 Acquisti", "✏️ Nomi"
])

# ===============================
# TAB: RIEPILOGO (tutte le squadre)
# ===============================
with tab_riepilogo:
    for team in st.session_state.squadre:
        with st.expander(f"{team.nome} – Crediti rimasti: {crediti_rimasti(team)}", expanded=False):
            st.write("Portieri:", [g.nome for g in team.rosa["P"]])
            st.write("Difensori:", [g.nome for g in team.rosa["D"]])
            st.write("Centrocampisti:", [g.nome for g in team.rosa["C"]])
            st.write("Attaccanti:", [g.nome for g in team.rosa["A"]])

# ===============================
# TAB: ACQUISTI MANUALI
# ===============================
with tab_acquisti:
    nome_g = st.text_input("Nome giocatore")
    ruolo_g = st.selectbox("Ruolo", RUOLI)
    prezzo_g = st.number_input("Prezzo", min_value=0, step=1)
    dest_name = st.selectbox("Squadra", [t.nome for t in st.session_state.squadre], key="dest_name_sel")
    if st.button("Aggiungi"):
        team = next(t for t in st.session_state.squadre if t.nome == dest_name)
        if aggiungi_giocatore(team, nome_g, ruolo_g, int(prezzo_g)):
            st.success(f"{nome_g} aggiunto a {team.nome}.")
        else:
            st.error("Impossibile aggiungere il giocatore.")

    squadra_r = st.selectbox("Squadra per rimuovere", [t.nome for t in st.session_state.squadre], key="squadra_r_sel")
    ruolo_r = st.selectbox("Ruolo da cui rimuovere", RUOLI, key="ruolo_r_sel")
    team_r = next(t for t in st.session_state.squadre if t.nome == squadra_r)
    gioc_r = st.selectbox("Giocatore", [g.nome for g in team_r.rosa[ruolo_r]] if team_r.rosa[ruolo_r] else ["—"], key="gioc_r_sel")
    if st.button("Rimuovi"):
        if gioc_r != "—" and rimuovi_giocatore(team_r, ruolo_r, gioc_r):
            st.success(f"{gioc_r} rimosso da {team_r.nome}.")
        else:
            st.error("Impossibile rimuovere il giocatore.")

# ===============================
# TAB: NOMI SQUADRE (rinomina)
# ===============================
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

# ===============================
# TAB: GIOCATORE A CHIAMATA (Qt.A ≤ X, ordinati per Slot→FVM)
# ===============================
with tab_call:
    st.subheader("Giocatore a chiamata")
    c1, c2 = st.columns([2,1])
    with c1:
        ruolo_call = st.radio("Ruolo", RUOLI, horizontal=True, key="ruolo_call")
    with c2:
        qta_max = st.number_input("Qt.A massima (≤)", min_value=0, step=1, key="qta_max_call")

    try:
        df_raw = load_sheet_from_drive(ruolo_call)
        if df_raw.empty or NAME_COL not in df_raw.columns:
            st.info("Dati non disponibili per questo ruolo.")
        else:
            df = df_raw.copy()
            df[NAME_COL] = df[NAME_COL].astype(str).str.strip()
            # Escludi già assegnati
            taken = {str(n).strip().upper() for n in elenco_giocatori_global()}
            df = df[~df[NAME_COL].str.upper().isin(taken)].reset_index(drop=True)

            cols_l = {c.lower(): c for c in df.columns}
            team_c = cols_l.get('team')
            slot_c = cols_l.get('slot')
            range_c = cols_l.get('pfcrange')
            fm_c = cols_l.get('expectedfantamedia')

            # Join con file 2: Qt.A e FVM
            idx_extra = build_extra_index()
            def _get_qta(name: str):
                rec = idx_extra.get(f"{ruolo_call}|{name_key(name)}")
                v = rec.get("Qt.A") if rec else None
                try:
                    return float(v)
                except Exception:
                    return None
            def _get_fvm(name: str):
                rec = idx_extra.get(f"{ruolo_call}|{name_key(name)}")
                v = rec.get("FVM") if rec else None
                try:
                    return float(v)
                except Exception:
                    return None
            df["_QtA"] = df[NAME_COL].map(_get_qta)
            df["_FVM"] = df[NAME_COL].map(_get_fvm)

            # Filtro: Qt.A ≤ valore inserito (ignora i NaN)
            df = df[df["_QtA"].notna() & (df["_QtA"] <= float(qta_max))].copy()

            # Ordina: Slot asc (se presente), poi FVM desc, poi Nome
            if slot_c:
                df["_slot_num"] = pd.to_numeric(df[slot_c].astype(str).str.extract(r"(\d+)")[0], errors='coerce')
            else:
                df["_slot_num"] = pd.NA
            df["_slot_num"] = df["_slot_num"].fillna(9999)

            # Ordina: Slot ↑, poi Qt.A ↓, poi FVM ↓, quindi Nome ↑
            df["_QtA_sort"] = pd.to_numeric(df["_QtA"], errors='coerce').fillna(float('-inf'))
            df["_FVM_sort"] = pd.to_numeric(df["_FVM"], errors='coerce').fillna(float('-inf'))
            df = df.sort_values(["_slot_num", "_QtA_sort", "_FVM_sort", NAME_COL], ascending=[True, False, False, True], kind="mergesort")

            # Output columns
            out_cols = {}
            if slot_c: out_cols["Slot"] = df[slot_c]
            out_cols["Nome"] = df[NAME_COL]
            if team_c: out_cols["Squadra"] = df[team_c]
            out_cols["Qt.A"] = df["_QtA"]
            out_cols["FVM"] = df["_FVM"]
            if range_c: out_cols["Range Stimato"] = df[range_c]
            if fm_c: out_cols["Fantamedia Stimata (file1)"] = df[fm_c]
            df_out = pd.DataFrame(out_cols).reset_index(drop=True)

            st.caption(f"Trovati {len(df_out)} giocatori per {ruolo_call} con Qt.A ≤ {int(qta_max)}")
            st.dataframe(df_out, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(str(e))

# ===============================
# TAB: ASTA – RUOLO & LETTERA + CARD GIOCATORE
# ===============================
with tab_asta:
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

                # Rimuovi calciatori già assegnati
                def _norm(s):
                    return str(s).strip().upper()
                taken = {_norm(n) for n in elenco_giocatori_global()}
                df_view = df_view[~df_view[NAME_COL].map(_norm).isin(taken)].reset_index(drop=True)

                # 🔎 Cerca + Pulisci
                search_key = f"search_{ruolo_asta}"
                clear_flag_key = f"clear_flag_{ruolo_asta}"
                if st.session_state.get(clear_flag_key):
                    st.session_state[search_key] = ""
                    st.session_state[clear_flag_key] = False

                c_search, c_clear = st.columns([4,1])
                with c_search:
                    st.text_input("🔎 Cerca", placeholder="Cerca per nome, squadra o slot…", key=search_key)
                with c_clear:
                    if st.button("Pulisci", key=f"clear_{ruolo_asta}"):
                        st.session_state[clear_flag_key] = True
                        try:
                            st.rerun()
                        except Exception:
                            st.experimental_rerun()

                q = st.session_state.get(search_key, "").strip().lower()
                if q:
                    cols_l = {c.lower(): c for c in df_view.columns}
                    team_c = cols_l.get('team')
                    slot_c = cols_l.get('slot')
                    mask = df_view[NAME_COL].astype(str).str.lower().str.contains(q)
                    if team_c:
                        mask |= df_view[team_c].astype(str).str.lower().str.contains(q)
                    if slot_c:
                        mask |= df_view[slot_c].astype(str).str.lower().str.contains(q)
                    df_view = df_view[mask].reset_index(drop=True)
                st.caption(f"Trovati {len(df_view)} calciatori")

                key_idx = f"car_idx_{ruolo_asta}"
                if key_idx not in st.session_state:
                    st.session_state[key_idx] = 0
                total = len(df_view)
                if total == 0:
                    st.info("Tutti i calciatori disponibili per questo ruolo risultano già assegnati o filtrati.")
                else:
                    st.session_state[key_idx] = min(st.session_state[key_idx], total - 1)

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
                    cols_lower = {c.lower(): c for c in df_view.columns}

                    colL, colR = st.columns([2,1], vertical_alignment="top")

                    with colL:
                        st.subheader(rec[NAME_COL])
                        st.caption(f"Ruolo: {ruolo_asta}")
                        for key_lower, label in FIELD_LABELS.items():
                            real_col = cols_lower.get(key_lower)
                            if not real_col:
                                continue
                            val = rec[real_col]
                            if pd.isna(val) or str(val).strip() == "":
                                continue
                            st.write(f"**{label}**: {val}")

                        # Extra dal file 2 (Tutti): Qt.A & FVM
                        extras = get_all_metrics(ruolo_asta, rec[NAME_COL])
                        qt_extra = extras.get("Qt.A") if extras else None
                        fvm_extra = extras.get("FVM") if extras else None
                        def _valid(v):
                            s = str(v)
                            return not (s.strip()=="" or s.lower()=="nan")
                        if _valid(qt_extra) or _valid(fvm_extra):
                            if _valid(qt_extra):
                                st.write(f"**Qt.A**: {qt_extra}")
                            if _valid(fvm_extra):
                                st.write(f"**FVM**: {fvm_extra}")

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

                        # Commento vs range stimato
                        rng_col = cols_lower.get('pfcrange')
                        rng_val = rec[rng_col] if rng_col else None
                        def _extract_ints(text):
                            if text is None:
                                return []
                            s = str(text)
                            out, buf = [], ""
                            for ch in s:
                                if ch.isdigit():
                                    buf += ch
                                else:
                                    if buf:
                                        out.append(int(buf)); buf = ""
                            if buf:
                                out.append(int(buf))
                            return out
                        nums = _extract_ints(rng_val)
                        low = high = None
                        if len(nums) >= 2:
                            a, b = nums[0], nums[1]
                            low, high = (a, b) if a <= b else (b, a)
                        elif len(nums) == 1:
                            low = high = nums[0]
                        if low is not None and high is not None:
                            price_now = int(prezzo_sel)
                            if price_now <= max(1, int(low * 0.90)):
                                st.success(f"Colpaccio!! 🎯 ({price_now} vs range {low}-{high})")
                            elif price_now < low:
                                st.success(f"Ottimo prezzo ✅ ({price_now} sotto {low}-{high})")
                            elif low <= price_now <= high:
                                st.info(f"Prezzo in linea 👍 ({low}-{high})")
                            elif price_now <= int(high * 1.15):
                                st.warning(f"Sovrapprezzo 🤏 ({price_now} sopra {high})")
                            else:
                                st.error(f"Fuori mercato 💸 ({price_now} >> {high})")

                        # Monitor spesa reparto (solo per la mia squadra)
                        if sel_team_idx == st.session_state.get("user_team_idx", -1):
                            team_sel = st.session_state.squadre[sel_team_idx]
                            curr = spesa_per_ruolo(team_sel).get(ruolo_asta, 0)
                            targ = target_per_ruolo_dynamic(team_sel).get(ruolo_asta, 0)
                            projected = curr + int(prezzo_sel)
                            label_ruolo = ROLE_LABELS.get(ruolo_asta, ruolo_asta)
                            if targ > 0:
                                pct_now = int(round(100*curr/targ))
                                pct_proj = int(round(100*projected/targ))
                                st.info(f"{label_ruolo}: ora {curr}/{targ} ({pct_now}%) • dopo {projected}/{targ} ({pct_proj}%)")
                                if projected > targ:
                                    st.warning(f"Superi il target {label_ruolo} di {projected - targ} crediti.")

                        if st.button("Aggiungi alla squadra", key=f"add_{ruolo_asta}_{idx}"):
                            team_sel = st.session_state.squadre[sel_team_idx]
                            ok = aggiungi_giocatore(team_sel, rec[NAME_COL], ruolo_asta, int(prezzo_sel))
                            if ok:
                                st.success(f"{rec[NAME_COL]} aggiunto a {team_sel.nome} per {int(prezzo_sel)}.")
                                st.session_state[key_idx] = min(total-1, st.session_state[key_idx]+1)
                                try:
                                    st.rerun()
                                except Exception:
                                    st.experimental_rerun()
                            else:
                                st.error("Impossibile aggiungere: controlla crediti/quote/doppioni.")

                    with colR:
                        st.subheader("📊 Disponibilità")
                        # In gara (squadre non complete per questo reparto)
                        try:
                            quota = st.session_state.settings['quote_rosa'][ruolo_asta]
                            incomplete = [
                                (t.nome, max(quota - len(t.rosa[ruolo_asta]), 0))
                                for t in st.session_state.squadre
                                if len(t.rosa[ruolo_asta]) < quota
                            ]
                            squadre_in_gara = len(incomplete)
                            st.markdown("""
                            <style>
                            .tooltip-row{position:relative;padding:4px 2px;}
                            .tooltip-row .hint{cursor:default;}
                            .tooltip-row .tip{visibility:hidden;opacity:0;transition:opacity .15s ease;position:absolute;left:0;top:100%;background:#111;color:#fff;padding:8px 10px;border-radius:8px;z-index:1000;min-width:220px;max-width:420px;box-shadow:0 4px 12px rgba(0,0,0,.2);} 
                            .tooltip-row:hover .tip{visibility:visible;opacity:1;} 
                            .tooltip-row .tip ul{margin:6px 0 0 18px;padding:0;max-height:260px;overflow:auto;} 
                            </style>
                            """, unsafe_allow_html=True)
                            if squadre_in_gara > 0:
                                li = []
                                for name, miss in incomplete:
                                    miss_txt = f"manca {miss}" if miss == 1 else f"mancano {miss}"
                                    li.append(f"<li>{name} — {miss_txt}</li>")
                                items_html = "".join(li)
                                html = f"<div class='tooltip-row'><span class='hint'>• In gara: {squadre_in_gara}</span><div class='tip'><strong>Squadre non complete</strong><ul>{items_html}</ul></div></div>"
                                st.markdown(html, unsafe_allow_html=True)
                            else:
                                st.markdown(f"<div class='tooltip-row'><span class='hint'>• In gara: 0</span></div>", unsafe_allow_html=True)
                        except Exception:
                            st.caption("In gara: n/d")

                        # Disponibilità per Slot (con tooltip dei nomi su hover)
                        slot_col = cols_lower.get('slot')
                        if slot_col and slot_col in df_view.columns:
                            ser = df_view[slot_col].dropna().astype(str).str.strip()
                            if len(ser) == 0:
                                st.write("_Nessun dato disponibile_")
                            else:
                                df_slots = df_view[[slot_col, NAME_COL]].dropna(subset=[slot_col, NAME_COL]).copy()
                                df_slots[slot_col] = df_slots[slot_col].astype(str).str.strip()
                                names_by_slot = {str(sl): list(sub[NAME_COL].astype(str)) for sl, sub in df_slots.groupby(slot_col)}

                                order = pd.DataFrame({'slot': ser}).drop_duplicates()
                                order['slot_num'] = pd.to_numeric(order['slot'], errors='coerce')
                                order = order.sort_values(['slot_num','slot'], na_position='last')
                                counts = ser.value_counts()

                                st.markdown("""
                                <style>
                                .tooltip-row{position:relative;padding:4px 2px;}
                                .tooltip-row .hint{cursor:default;}
                                .tooltip-row .tip{visibility:hidden;opacity:0;transition:opacity .15s ease;position:absolute;left:0;top:100%;background:#111;color:#fff;padding:8px 10px;border-radius:8px;z-index:1000;min-width:220px;max-width:420px;box-shadow:0 4px 12px rgba(0,0,0,.2);} 
                                .tooltip-row:hover .tip{visibility:visible;opacity:1;} 
                                .tooltip-row .tip ul{margin:6px 0 0 18px;padding:0;max-height:260px;overflow:auto;} 
                                </style>
                                """, unsafe_allow_html=True)
                                for val in order['slot']:
                                    cnt = int(counts.get(val, 0))
                                    names = names_by_slot.get(str(val), [])
                                    if names:
                                        item_list = ''.join(f'<li>{n}</li>' for n in names)
                                        html = f"<div class='tooltip-row'><span class='hint'>• Slot {val}: {cnt} disponibili</span><div class='tip'><strong>Giocatori disponibili (Slot {val})</strong><ul>{item_list}</ul></div></div>"
                                    else:
                                        html = f"<div class='tooltip-row'><span class='hint'>• Slot {val}: {cnt} disponibili</span></div>"
                                    st.markdown(html, unsafe_allow_html=True)
                        else:
                            st.caption("Colonna 'Slot' assente nel file.")
    except Exception as e:
        st.error(str(e))

# ===============================
# FOOTER
# ===============================
st.markdown("---")
st.caption("Doppioni disattivati per design: un giocatore può appartenere a una sola squadra.")

def target_per_ruolo_dynamic(team: Squadra) -> Dict[str, int]:
    """
    Ricalcola i target per reparto quando uno o più reparti sono COMPLETI.
    - I reparti COMPLETI vengono 'bloccati' al valore realmente speso.
    - Il budget residuo viene redistribuito tra i reparti NON completi
      PROPORZIONALMENTE alle percentuali originali (normalize).
    - Se nessun reparto è completo, ritorna i target fissi originali.
    """
    perc = st.session_state.settings.get("spending_targets", {"P": 0.10, "D": 0.20, "C": 0.30, "A": 0.40})
    spent = spesa_per_ruolo(team)
    quota = st.session_state.settings["quote_rosa"]
    completed = [r for r in RUOLI if len(team.rosa[r]) >= quota[r]]
    if not completed:
        return target_per_ruolo(team)

    t: Dict[str, int] = {}
    # Blocco i reparti completi al valore speso
    for r in completed:
        t[r] = int(spent.get(r, 0))

    # Budget rimanente da distribuire agli altri reparti
    remaining_roles = [r for r in RUOLI if r not in completed]
    if not remaining_roles:
        # Tutti completi: i target sono i totali spesi
        return t

    remaining_pool = int(team.budget - sum(t.values()))
    if remaining_pool < 0:
        remaining_pool = 0

    # Normalizzo i pesi dei reparti rimanenti secondo le percentuali originali
    total_w = sum(perc.get(r, 0.0) for r in remaining_roles)
    # Se somma 0 (edge case), distribuisco equamente
    if total_w <= 0:
        weights = {r: 1.0/len(remaining_roles) for r in remaining_roles}
    else:
        weights = {r: (perc.get(r, 0.0)/total_w) for r in remaining_roles}

    # Assegna target ai reparti rimanenti
    acc = 0
    for i, r in enumerate(remaining_roles):
        if i < len(remaining_roles)-1:
            val = int(round(remaining_pool * weights[r]))
            t[r] = val
            acc += val
        else:
            # Ultimo reparto: aggiusta eventuale differenza per arrivare esattamente al budget
            t[r] = int(remaining_pool - acc)

    # Sanity: assicurati che la somma sia il budget totale (entro ±1 per arrotondamenti)
    diff = int(team.budget - sum(t.values()))
    if diff != 0:
        # Correggi sul primo reparto non completo
        for r in remaining_roles:
            t[r] = max(0, t[r] + diff)
            break
    return t

