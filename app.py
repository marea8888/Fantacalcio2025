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
# (funzioni helper come prima...)

# -------------------------------
# Sidebar – Utility Lega
# -------------------------------
with st.sidebar:
    st.title("⚙️ Utility Lega")
    if st.button("🔄 Reset lega (ricrea squadre e azzera acquisti)"):
        reset_lega()
        st.warning("Lega resettata.")

# -------------------------------
# Header
# -------------------------------
st.title("Fantacalcio – Gestore Lega")
st.caption("Impostazioni fissate da codice: 9 squadre, 700 crediti, rosa 3P/8D/8C/6A, doppioni NON consentiti.")

# (resto del codice invariato...)

st.markdown("---")
st.caption("Doppioni disattivati per design: un giocatore può appartenere a una sola squadra.")
