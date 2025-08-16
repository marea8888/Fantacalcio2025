import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Fantacalcio – Gestore Lega", page_icon="⚽", layout="wide")

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
if "settings" not in st.session_state:
    st.session_state.settings = {
        "num_squadre": 9,
        "crediti": 700,
        "quote_rosa": QUOTE_ROSA.copy(),
        "no_doppioni": True,
    }

if "squadre" not in st.session_state:
    # Creazione predefinita: "Terzetto Scherzetto", "Squadra 2" ...
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


def aggiungi_giocatore(team: Squadra, nome: str, ruolo: str, prezzo: int, imp_doppioni: bool = True) -> bool:
    # Validazioni
    if not nome.strip():
        st.error("Inserisci un nome valido.")
        return False
    if ruolo not in RUOLI:
        st.error("Ruolo non valido.")
        return False
    if prezzo < 0:
        st.error("Il prezzo non può essere negativo.")
        return False
    if imp_doppioni and nome in elenco_giocatori_global():
        st.error("Giocatore già assegnato ad un'altra squadra (doppioni non consentiti).")
        return False
    if quote_rimaste(team)[ruolo] <= 0:
        st.error(f"La quota per il ruolo {ruolo} è già completa per {team.nome}.")
        return False
    if crediti_rimasti(team) < prezzo:
        st.error(f"Crediti insufficienti. Rimasti {crediti_rimasti(team)}.")
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


def export_json() -> str:
    payload = {
        "settings": st.session_state.settings,
        "squadre": [t.to_dict() for t in st.session_state.squadre],
        "storico": st.session_state.storico_acquisti,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def import_json(text: str):
    data = json.loads(text)
    st.session_state.settings = data.get("settings", st.session_state.settings)
    st.session_state.squadre = [Squadra.from_dict(d) for d in data.get("squadre", [])]
    st.session_state.storico_acquisti = data.get("storico", [])


def reset_lega():
    # Ricrea le squadre con nomi default
    def _init_default_squadre():
        s = []
        for i in range(st.session_state.settings["num_squadre"]):
            nome = "Terzetto Scherzetto" if i == 0 else f"Squadra {i+1}"
            s.append(Squadra(nome, st.session_state.settings["crediti"]))
        return s
    st.session_state.squadre = _init_default_squadre()
    st.session_state.storico_acquisti = []

# -------------------------------
# Sidebar – Impostazioni Lega
# -------------------------------
with st.sidebar:
    st.title("⚙️ Impostazioni Lega")
    crediti = st.number_input("Crediti per squadra", min_value=1, value=st.session_state.settings["crediti"], step=10)
    num_squadre = st.number_input("Numero squadre", min_value=2, max_value=20, value=st.session_state.settings["num_squadre"], step=1)

    cols = st.columns(4)
    quote_inputs = {}
    for i, r in enumerate(RUOLI):
        with cols[i]:
            quote_inputs[r] = st.number_input(f"{r}", min_value=0, value=st.session_state.settings["quote_rosa"][r], step=1)

    no_doppioni = st.checkbox("Impedisci doppioni (consigliato)", value=st.session_state.settings["no_doppioni"])

    apply = st.button("Applica impostazioni")
    if apply:
        st.session_state.settings["crediti"] = int(crediti)
        st.session_state.settings["num_squadre"] = int(num_squadre)
        st.session_state.settings["quote_rosa"] = {r: int(quote_inputs[r]) for r in RUOLI}
        st.session_state.settings["no_doppioni"] = bool(no_doppioni)
        st.success("Impostazioni aggiornate. Le nuove squadre verranno applicate al reset della lega.")

    st.markdown("---")
    if st.button("🔄 Reset lega (ricrea squadre e azzera acquisti)"):
        reset_lega()
        st.warning("Lega resettata.")

# -------------------------------
# Header
# -------------------------------
st.title("Fantacalcio – Gestore Lega")
st.caption("Crea 9 squadre con 700 crediti e rosa 3P/8D/8C/6A. Rinomina le squadre, gestisci acquisti e rispetta i vincoli.")

# -------------------------------
# Tabs principali
# -------------------------------

tab_riepilogo, tab_acquisti, tab_nomi, tab_esporta = st.tabs([
    "📊 Riepilogo squadre",
    "🛒 Aggiungi/Rimuovi giocatori",
    "✏️ Cambia nomi squadre",
    "📤 Esporta / 📥 Importa",
])

# --- RIEPILOGO ---
with tab_riepilogo:
    for team in st.session_state.squadre:
        with st.expander(f"{team.nome} – Crediti rimasti: {crediti_rimasti(team)}", expanded=False):
            # Metriche
            c1, c2, c3, c4, c5 = st.columns([2,1,1,1,1])
            with c1:
                st.metric("Completata?", "Sì" if rosa_completa(team) else "No")
            for i, r in enumerate(RUOLI, start=2):
                with locals()[f"c{i}"]:
                    st.metric(r, f"{len(team.rosa[r])}/{st.session_state.settings['quote_rosa'][r]}")

            # Roster tables per ruolo
            for r in RUOLI:
                df = pd.DataFrame([asdict(g) for g in team.rosa[r]]) if team.rosa[r] else pd.DataFrame(columns=["nome", "ruolo", "prezzo"])
                st.subheader(f"{r}")
                st.dataframe(df, use_container_width=True)

# --- ACQUISTI ---
with tab_acquisti:
    st.subheader("Aggiungi giocatore")
    col1, col2, col3, col4 = st.columns([2,1,1,2])
    with col1:
        nome_g = st.text_input("Nome giocatore")
    with col2:
        ruolo_g = st.selectbox("Ruolo", RUOLI, index=0)
    with col3:
        prezzo_g = st.number_input("Prezzo", min_value=0, step=1, value=1)
    with col4:
        team_names = [t.nome for t in st.session_state.squadre]
        dest_name = st.selectbox("Assegna a", team_names, index=0)

    if st.button("➕ Aggiungi"):
        team = next(t for t in st.session_state.squadre if t.nome == dest_name)
        ok = aggiungi_giocatore(team, nome_g, ruolo_g, int(prezzo_g), st.session_state.settings["no_doppioni"])
        if ok:
            st.success(f"{nome_g} aggiunto a {team.nome} per {int(prezzo_g)}.")

    st.markdown("---")
    st.subheader("Rimuovi giocatore")
    colr1, colr2, colr3 = st.columns([2,1,2])
    with colr1:
        team_r_name = st.selectbox("Squadra", [t.nome for t in st.session_state.squadre], key="rm_team")
        team_r = next(t for t in st.session_state.squadre if t.nome == team_r_name)
    with colr2:
        ruolo_r = st.selectbox("Ruolo", RUOLI, key="rm_role")
    with colr3:
        gioc_r = st.selectbox(
            "Giocatore",
            [g.nome for g in team_r.rosa[ruolo_r]] if team_r.rosa[ruolo_r] else ["—"],
            key="rm_player",
        )
    if st.button("🗑️ Rimuovi"):
        if gioc_r == "—":
            st.error("Nessun giocatore da rimuovere per questo ruolo.")
        else:
            if rimuovi_giocatore(team_r, ruolo_r, gioc_r):
                st.success(f"{gioc_r} rimosso da {team_r.nome}.")
            else:
                st.error("Operazione non riuscita.")

    st.markdown("---")
    st.subheader("Storico acquisti (sessione)")
    if st.session_state.storico_acquisti:
        st.dataframe(pd.DataFrame(st.session_state.storico_acquisti), use_container_width=True)
    else:
        st.info("Ancora nessun acquisto registrato.")

# --- NOMI ---
with tab_nomi:
    st.write("Rinomina liberamente le squadre. I cambi sono immediati.")
    for i, team in enumerate(st.session_state.squadre):
        nuovo_nome = st.text_input(f"Nome squadra {i+1}", value=team.nome, key=f"nome_{i}")
        if nuovo_nome.strip() and nuovo_nome != team.nome:
            # Verifica che il nome non sia già usato da un'altra squadra
            altri_nomi = {t.nome for j, t in enumerate(st.session_state.squadre) if j != i}
            if nuovo_nome in altri_nomi:
                st.warning(f"Il nome '{nuovo_nome}' è già in uso. Scegli un altro nome.")
            else:
                team.nome = nuovo_nome
                st.success(f"Nome aggiornato: {team.nome}")

# --- ESPORTA / IMPORTA ---
with tab_esporta:
    st.subheader("Esporta la lega in JSON")
    data_json = export_json()
    st.download_button("Scarica JSON", data=data_json, file_name="lega_fantacalcio.json", mime="application/json")

    st.markdown("---")
    st.subheader("Importa da JSON")
    up = st.file_uploader("Carica un file JSON esportato in precedenza", type=["json"])
    if up is not None:
        try:
            import_json(up.read().decode("utf-8"))
            st.success("Import effettuato con successo.")
        except Exception as e:
            st.error(f"Errore nell'import: {e}")

# Footer
st.markdown("---")
st.caption("Suggerimento: attiva 'Impedisci doppioni' per una lega ad 1 cartellino per giocatore.")
