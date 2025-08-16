import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Fantacalcio – Gestore Lega", page_icon="⚽", layout="wide", initial_sidebar_state="collapsed")

# -------------------------------
# Modello dati
# -------------------------------
RUOLI = ["P", "D", "C", "A"]
QUOTE_ROSA = {"P": 3, "D": 8, "C": 8, "A": 6}

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
        s.rosa = {r: [Giocatore(**g) for g in d["rosa"].get(r, [])] for r in RUOLI}
        return s

# -------------------------------
# Stato iniziale
# -------------------------------
SETTINGS = {
    "num_squadre": 9,
    "crediti": 700,
    "quote_rosa": QUOTE_ROSA.copy(),
    "no_doppioni": True,
}

if "settings" not in st.session_state:
    st.session_state.settings = SETTINGS.copy()

if "squadre" not in st.session_state:
    def _init_default_squadre():
        s = []
        for i in range(st.session_state.settings["num_squadre"]):
            nome = "Terzetto Scherzetto" if i == 0 else f"Squadra {i+1}"
            s.append(Squadra(nome, st.session_state.settings["crediti"]))
        return s
    st.session_state.squadre: List[Squadra] = _init_default_squadre()

if "storico_acquisti" not in st.session_state:
    st.session_state.storico_acquisti: List[dict] = []

# -------------------------------
# Helper
# -------------------------------
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
    return True

def rimuovi_giocatore(team: Squadra, ruolo: str, giocatore_nome: str) -> bool:
    elenco = team.rosa[ruolo]
    for i, g in enumerate(elenco):
        if g.nome == giocatore_nome:
            elenco.pop(i)
            return True
    return False

def reset_lega():
    def _init_default_squadre():
        s = []
        for i in range(st.session_state.settings["num_squadre"]):
            nome = "Terzetto Scherzetto" if i == 0 else f"Squadra {i+1}"
            s.append(Squadra(nome, st.session_state.settings["crediti"]))
        return s
    st.session_state.squadre = _init_default_squadre()
    st.session_state.storico_acquisti = []

# -------------------------------
# Header
# -------------------------------
st.title("Fantacalcio – Gestore Lega")
st.caption("Impostazioni fissate da codice: 9 squadre, 700 crediti, rosa 3P/8D/8C/6A, doppioni NON consentiti.")

# -------------------------------
# Asta corrente – selezione ruolo e lettera alfabetica
# -------------------------------
col_a, col_b = st.columns([1,1])
with col_a:
    st.subheader("Ruolo in asta")
    ruolo_asta = st.radio("Seleziona il ruolo per cui si sta svolgendo l'asta", RUOLI, index=0, horizontal=True, key="ruolo_asta")
with col_b:
    st.subheader("Lettera estratta")
    lettera_input = st.text_input("Inserisci la lettera alfabetica estratta (A–Z)", value=st.session_state.get("lettera_estratta", ""), max_chars=1)
    # Normalizza a maiuscolo
    lettera_norm = (lettera_input or "").upper()
    st.session_state["lettera_estratta"] = lettera_norm
    if lettera_norm:
        st.info(f"Asta per ruolo **{ruolo_asta}** con lettera **{lettera_norm}**.")
    else:
        st.info(f"Asta per ruolo **{ruolo_asta}**. Inserisci una lettera per procedere con le regole che definirai.")

# -------------------------------
# Tabs principali
# -------------------------------
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

st.markdown("---")
st.caption("Doppioni disattivati per design: un giocatore può appartenere a una sola squadra.")
