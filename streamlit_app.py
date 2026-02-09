import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="GME Multiplier", layout="wide")

# Percorso di lavoro del repository
DATA_PATH = os.getcwd()

def get_best_sheet(xl_file):
    """Trova il foglio più probabile per i prezzi se 'Prezzi-Prices' non esiste."""
    sheet_names = xl_file.sheet_names
    # Priorità al nome esatto
    for s in sheet_names:
        if "prezzi" in s.lower() or "prices" in s.lower():
            return s
    # Altrimenti restituisce il primo foglio
    return sheet_names[0]

@st.cache_data
def load_year_data(year, freq="60"):
    """Carica i file Excel del repository filtrando per anno e frequenza."""
    all_entries = os.listdir(DATA_PATH)
    target_files = [f for f in all_entries if str(year) in f and f.lower().endswith(('.xlsx', '.xls'))]
    
    # Filtro TIDE per 2025/2026
    if year >= 2025:
        if freq == "15":
            target_files = [f for f in target_files if "_15" in f]
        else:
            target_files = [f for f in target_files if "_60" in f or "_15" not in f]

    if not target_files:
        return None

    combined_dfs = []
    for f in target_files:
        try:
            full_path = os.path.join(DATA_PATH, f)
            xl = pd.ExcelFile(full_path)
            sheet = get_best_sheet(xl)
            df = xl.parse(sheet)
            combined_dfs.append(df)
        except Exception as e:
            st.error(f"Errore nel file {f}: {e}")
            continue
    
    return pd.concat(combined_dfs, ignore_index=True) if combined_dfs else None

# --- UI INTERFACCIA ---
st.title("⚡ Energy Cost Calculator")

# Sidebar
year = st.sidebar.selectbox("Anno", list(range(2004, 2027)), index=21)

# Caricamento Prezzi
with st.spinner(f"Ricerca file anno {year} nel repository..."):
    p_data = load_year_data(year, "60")

if p_data is not None:
    # Pulizia nomi colonne
    p_data.columns = [str(c).replace('\n', ' ').strip() for c in p_data.columns]
    
    # Identificazione colonne tecniche
    ignore_cols = ['Data', 'Date', 'Ora', 'Hour', 'Periodo', 'Period', 'N°', 'N.']
    markets = [c for c in p_data.columns if not any(x in c for x in ignore_cols)]
    
    market = st.sidebar.selectbox("Seleziona Mercato/Zona", markets)
    curve_file = st.file_uploader("Carica Curva e-distribuzione (CSV)", type=['csv'])

    if st.button("Esegui Calcolo"):
        if curve_file:
            # Carica curva (Giorno;00:00-00:15...)
            df_c = pd.read_csv(curve_file, sep=';', decimal=',')
            df_c['Giorno'] = pd.to_datetime(df_c['Giorno'], dayfirst=True)
            
            # Trova colonne Data e Ora nel file prezzi
            d_col = next(c for c in p_data.columns if 'data' in c.lower() or 'date' in c.lower())
            h_col = next(c for c in p_data.columns if 'ora' in c.lower() or 'hour' in c.lower())

            # Se 2025+, prova a caricare dati a 15min
            p15 = load_year_data(year, "15") if year >= 2025 else None
            if p15 is not None:
                p15.columns = [str(c).replace('\n', ' ').strip() for c in p15.columns]
                per_col = next(c for c in p15.columns if 'period' in c.lower() or 'periodo' in c.lower())

            results = []
            for _, row_c in df_c.iterrows():
                # Formato GME YYYYMMDD
                curr_date_int = int(row_c['Giorno'].strftime('%Y%m%d'))
                day_prices = p_data[p_data[d_col] == curr_date_int]
                
                if day_prices.empty: continue
                
                day_p15 = p15[p15[d_col] == curr_date_int] if p15 is not None else None

                for h in range(1, 25):
                    # Prezzo Orario
                    p_val = day_prices[day_prices[h_col] == h][market].values[0]
                    # Carico (Colonne da 1 a 4 per ora 1, etc.)
                    q_vals = row_c.iloc[(h-1)*4 + 1 : (h-1)*4 + 5].replace(',', '.', regex=True).astype(float).values
                    
                    row_res = {
                        "Data": row_c['Giorno'].date(),
                        "Ora": h,
                        "Energia_MWh": sum(q_vals),
                        "Costo_Orario": sum(q_vals * p_val)
                    }
                    
                    if year >= 2025 and day_p15 is not None:
                        c15 = 0
                        for i, q in enumerate(q_vals):
                            p_idx = (h-1)*4 + (i+1)
                            p15_val = day_p15[day_p15[per_col] == p_idx][market].values[0]
                            c15 += (q * p15_val)
                        row_res["Costo_15min_TIDE"] = c15
                    
                    results.append(row_res)

            final_df = pd.DataFrame(results)
            final_df['Mese'] = pd.to_datetime(final_df['Data']).dt.strftime('%Y-%m')
            summary = final_df.groupby('Mese').sum(numeric_only=True).drop(columns=['Ora'])

            st.write("### Riepilogo Mensile")
            st.table(summary)
            
            # Export
            out = BytesIO()
            with pd.ExcelWriter(out, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False, sheet_name='Dettaglio')
                summary.to_excel(writer, sheet_name='Sintesi_Mese')
            st.download_button("📥 Scarica Risultati Excel", out.getvalue(), f"Risultati_{year}.xlsx")
        else:
            st.info("Trascina il file delle curve di carico per procedere.")
else:
    st.error(f"⚠️ Impossibile trovare i file Excel per l'anno {year}.")
    st.info("Verifica che i file siano nella cartella principale del repository GitHub e che il nome contenga l'anno (es. 'Anno 2009.xlsx').")
    # Debug per te: mostra cosa vede Streamlit
    with st.expander("Vedi file presenti nel repository"):
        st.write(os.listdir(DATA_PATH))
