"""A toy clinical decision support app.

Run:  streamlit run app.py

How Streamlit works, in one sentence: every time the user clicks or types
something, Streamlit runs this whole script again from top to bottom and
redraws the page. Things that must survive between runs (like a value the
user typed) are kept in st.session_state.

This is a technical demo. It is NOT meant to be used for clinical decisions.
"""
import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np
import streamlit as st

import prediction

DB_FILE = Path(__file__).parent / "ehr.db"

st.set_page_config(page_title="NSCLC CDSS Demo", page_icon="🫁", layout="wide")
st.title("NSCLC Clinical Decision Support Demo")
st.write("Welkom bij dit CDSS voor oncologen met NSCLC-patiënten. Selecteer een patiënt om de overlevingskans binnen de komende 5 jaar te laten voorspellen door het model,"
         " druk op 'Open behandeladvies' om advies te krijgen over behandelingen, of scroll naar beneden om andere patiënt- en"
         " tumorkenmerken te proberen voor de geselecteerde patiënt.")
st.warning("Technische demo, niet bedoeld voor echte klinische beslissingen.")

# 1. Check that the files we need are there
if not DB_FILE.exists():
    st.error("ehr.db not found. Run `python setup_database.py` first (see the README).")
    st.stop()
if not prediction.MODEL_FILE.exists():
    st.error("model.keras not found. Train your model and save it as model.keras "
             "in the same folder as app.py (see the README).")
    st.stop()


# 2. Load the model (once) and the patients (on every run)
@st.cache_resource(max_entries=1)  # load the model only once, not on every click...
def get_model(file_modified_time):  # ...but again whenever model.keras is replaced
    return prediction.load_model()


def load_patients():
    """Read all patients from the database, as {id: {column: value}}."""
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM patient ORDER BY id").fetchall()
    return {row["id"]: dict(row) for row in rows}


patients = load_patients()
if not patients:
    st.warning("The database has no patients. Check database.sql and run setup_database.py.")
    st.stop()

try:
    model = get_model(prediction.MODEL_FILE.stat().st_mtime)
except ImportError as error:
    st.error("TensorFlow is not installed in the Python environment that runs this app. "
             "Activate your virtual environment and run `pip install -r requirements.txt`. "
             f"(Error: {error})")
    st.stop()
except Exception as error:
    st.error("model.keras exists but could not be loaded. Was it saved with "
             "`model.save('model.keras')`, using the same TensorFlow version as in "
             f"requirements.txt? See Troubleshooting in the README. (Error: {error})")
    st.stop()

try:
    all_inputs = np.vstack([prediction.make_input(p) for p in patients.values()])
except ValueError as error:
    st.error(f"Problem with the patient data: {error}")
    st.stop()

problem = prediction.check_model(model, all_inputs)
if problem:
    st.error("Your model does not fit this app yet. " + problem)
    st.stop()

# The blood pressure typed in by the user. None = use the value from the database.
st.session_state.setdefault("userstage", None)
st.session_state.setdefault("userage", None)

def forget_userinput():
    st.session_state.userstage = None
    st.session_state.userage = None

col1, col2 = st.columns(2)

# 3. The page
with col1:
    st.subheader("Patiënten")
    patient_id = st.radio(
        "Selecteer een patiënt uit de database",
        options=list(patients),
        format_func=lambda pid: patients[pid]["display_name"],
        on_change=forget_userinput,  # a new patient starts without a typed-in value
    )
    current_patient = patients[patient_id]

with col2:
    st.write("") # Create whitespace to better fit the page
    st.write("")
    st.write("")
    userstage = st.session_state.userstage
    userage = st.session_state.userage
    p = prediction.get_prediction(model, current_patient, stadium=userstage, leeft=userage)
    st.caption("Dit is de output van het model. De output van 0-1 geeft de voorspelde overlijdenskans binnen 5 jaar.")
    st.metric("Voorspelde overlijdenskans binnen 5 jaar:", f"{p:.2f}")
    if st.button("Open behandeladvies voor deze patiënt", type="primary"):
        st.session_state["treatment_patient_id"] = patient_id
        st.switch_page("pages/3_Behandeladvies.py")

st.divider()

STADIUM_CODES = {
    "0": 0,
    "1A": 1,
    "1B": 2,
    "2A": 3,
    "2B": 4,
    "3A": 5,
    "3B": 6,
    "3C": 7,
    "4": 8,
    "M": 9,
}

results = st.container()  # filled in below, but shown here, above the form
with st.expander("Aangepaste kenmerken invoeren"):
    with st.form("stage_form", clear_on_submit=True):
        st.header("Aangepaste kenmerken invoeren")
        st.subheader("Laat de velden leeg om de echte patiëntwaarden te gebruiken")
        new_stage_label = st.selectbox(
            "Hier kunt u een nieuw stadium selecteren om de invloed op de voorspelling te testen",
            options = list(STADIUM_CODES.keys()),
            index = None,
            placeholder = "Selecteer stadium",
            help = "Selecteer hier een tumorstadium om te testen",
        )
        new_stage = (
            STADIUM_CODES[new_stage_label]
            if new_stage_label is not None
            else None)
        new_age = st.number_input(
        "Hier kunt u een nieuwe leeftijd intypen om de invloed op de voorspelling te testen.",
        min_value=18, max_value=120, value=None, step=1,
        help="Laat dit veld leeg en druk op 'Invoeren in model' om de bekende waarde te gebruiken.",
        )
        if st.form_submit_button("Invoeren in model"):
            st.session_state.userstage = new_stage  # used for this prediction only, not saved
            st.session_state.userage = new_age # Usedfor this prediction only, not saved
            st.rerun()

with results:
    userstage = st.session_state.userstage
    userage = st.session_state.userage
    p = prediction.get_prediction(model, current_patient, stadium=userstage, leeft=userage)

    st.markdown(f"**Huidige patiënt:** {current_patient['display_name']}")
    st.markdown(f"**Gebruiker-ingevoerd stadium:** {userstage if userstage is not None else 'Geen stadium ingevoerd'}")
    st.markdown(f"**Gebruiker-ingevoerde leeftijd:** {userage if userage is not None else 'Geen leeftijd ingevoerd'}")

    # Take only relevant comlumns to show to user
    RELEVANT_FEATURES = [
    'leeft',
    'gesl',
    'tumsoort',
    'diag_basis',
    'morf',
    'gedrag',
    'diffgrad',
    'stadium',
    'chemo',
    'target',
    'rt',
    'SCLC',
    ]

    # Make dictionary for easier displaynames
    RELEVANT_LABELS = {
    'leeft': 'Leeftijd (jaren)',
    'gesl': 'Geslacht (1 = Man, 2 = Vrouw)',
    'tumsoort': 'Tumorsoort (302310 = NSCLC)',
    'diag_basis': 'Diagnostische_basis',
    'morf': 'Morfologie',
    'gedrag': 'Gedrag van de tumor',
    'diffgrad': 'Differentiatiegraad',
    'stadium': 'Stadium',
    'chemo': 'Chemotherapie',
    'target': 'Targetted therapy',
    'rt': 'Radiotherapie',
    'SCLC': 'SCLC (NSCLC = 0)'
    }

    with st.expander("Inputs van de voorspelling"):
        x = prediction.make_input(current_patient, leeft=userage, stadium=userstage,)[0]
        patient_display = current_patient.copy() # Copy patient to make sure original data is not changed

        # Check if user entered custom data
        if userstage is not None:
            patient_display['stadium'] = userstage

        if userage is not None:
            patient_display['leeft'] = userage

        # Turn relevant columns into features
        visible_inputs = [
        (feature, float(value))
        for feature, value in zip(prediction.FEATURES, x)
        if feature in RELEVANT_FEATURES
        ]

        # Show data BEFORE preprocessor changes/normalizes it
        st.table({
        "Input": list(RELEVANT_LABELS.values()),
        "Waarde": [patient_display[feature] for feature in RELEVANT_FEATURES],
        })

st.divider()
