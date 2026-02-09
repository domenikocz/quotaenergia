import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="GME Multiplier", layout="wide")

# Percorso radice del repository
DATA_PATH = os.getcwd() 

def load_price_data(year, freq="60"):
    """Carica i dati cercando i file Excel nel repository."""
    try:
        all_files = os.listdir(DATA_PATH)
    except Exception as e:
        st.error(f"Errore critico di sistema: {e}")
        return None

    dfs = []
    year_str = f"Anno {year}"
    
    # Debug: mostriamo i file trovati se non ne trova nessuno
    valid_files = [f for f in all_files if year_str in f and f.lower().endswith(('.xlsx', '.xls'))]
    
    for f in valid_files:
        # Gestione TIDE 2025+
        if year >= 2025:
            if freq == "15" and "_15" not in f: continue
            if freq == "60" and "_15" in f: continue
        
        full_path = os.path.join(DATA_PATH, f)
        try:
            # Carichiamo il file Excel
            xl = pd.ExcelFile(full_path)
            # Cerchiamo un foglio che contenga 'Prezzi' o 'Prices' (case insensitive)
            target_sheet = None
            for sheet in xl.sheet_names:
                if "prezzi" in sheet.lower() or "prices" in sheet.lower():
                    target_sheet = sheet
                    break
            
            if target_sheet:
                df = xl.parse(target_sheet)
                dfs.append(df)
            else:
                st.warning(f"Foglio prezzi non trovato nel file: {f}")
        except Exception as e:
            st.warning(f"Errore nel leggere {f}: {e}")
                
    return pd.concat(dfs, ignore_index=True) if dfs else None

# --- INTERFACCIA ---
st.title("⚡ Analisi Costi Energetici")

# Sezione Debug (Puoi rimuoverla quando funziona)
with st.expander("🔍 Debug: File rilevati nel repository"):
    st.write(os.listdir(DATA_PATH))

selected_year = st.sidebar.selectbox("Seleziona Anno", list(range(2004, 2027)), index=21)

# Caricamento Prezzi
p_data = load_price_data(selected_year)

if p_data is not None:
    p_data.columns = [str(c).replace('\n', ' ').strip() for c in p_data.columns]
    
    # Pulizia colonne per identificare il mercato
    ignore = ['Data', 'Date', 'Ora', 'Hour', 'Periodo', 'Period', 'N°', 'N.']
    market_options = [c for c in p_data.columns if not any(x in c for x in ignore)]
    
    market_name = st.sidebar.selectbox("Seleziona Mercato", market_options)
    curve_file = st.file_uploader("Carica Curva e-distribuzione (CSV)", type=['csv'])

    if st.button("Calcola"):
        if curve_file:
            # Funzione di calcolo integrata
            df_curve = pd.read_csv(curve_file, sep=';', decimal=',')
            df_curve['Giorno'] = pd.to_datetime(df_curve['Giorno'], dayfirst=True)
            
            # Recupero nomi colonne chiave
            date_col = [c for c in p_data.columns if 'Data' in c or 'Date' in c][0]
            hour_col = [c for c in p_data.columns if 'Ora' in c or 'Hour' in c][0]
            
            results = []
            for _, row_c in df_curve.iterrows():
                fmt_date = int(row_c['Giorno'].strftime('%Y%m%d'))
                day_p = p_data[p_data[date_col] == fmt_date]
                
                if day_p.empty: continue
                
                for hour in range(1, 25):
                    price_val = day_p[day_p[hour_col] == hour][market_name].values[0]
                    # Calcolo sui 4 quarti d'ora
                    q_vals = row_c.iloc[(hour-1)*4 + 1 : (hour-1)*4 + 5].replace(',', '.', regex=True).astype(float).values
                    
                    results.append({
                        "Data": row_c['Giorno'].date(),
                        "Ora": hour,
                        "Energia_MWh": sum(q_vals),
                        "Costo": sum(q_vals * price_val)
                    })
            
            final_df = pd.DataFrame(results)
            st.success("Calcolo Completato!")
            st.dataframe(final_df)
            
            # Download
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("📥 Scarica Risultati", output.getvalue(), file_name="Report.xlsx")
else:
    st.error(f"Nessun file trovato per l'anno {selected_year}. Controlla che i file si chiamino 'Anno {selected_year}...'")
