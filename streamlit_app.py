import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="GME Multiplier - Energy Analysis", layout="wide")

# I file sono nella root del repository
DATA_PATH = "." 

def load_local_price_file(year, frequency="60"):
    """Cerca e carica tutti i file prezzi per l'anno e la frequenza selezionati."""
    files = [f for f in os.listdir(DATA_PATH) if f.endswith(('.xlsx', '.csv'))]
    
    dfs = []
    year_str = f"Anno {year}"
    
    for f in files:
        if year_str in f:
            # Filtro per frequenza (15 o 60 min) per il 2025+
            if year >= 2025:
                if frequency == "15" and "_15" in f:
                    pass
                elif frequency == "60" and ("_60" in f or ("_15" not in f and "Prices" in f)):
                    pass
                else:
                    continue
            else:
                # Per anni < 2025 cerchiamo i file Prezzi standard
                if "Prices" not in f and "prezzi" not in f.lower() and "_" not in f:
                    # Se non ha "Prices" nel nome ma è l'unico file dell'anno, lo prendiamo
                    pass
                elif "Prices" not in f and "prezzi" not in f.lower():
                    continue
            
            full_path = os.path.join(DATA_PATH, f)
            try:
                if f.endswith('.csv'):
                    # sep=None con engine python rileva automaticamente ; o ,
                    temp_df = pd.read_csv(full_path, sep=None, engine='python')
                else:
                    temp_df = pd.read_excel(full_path)
                dfs.append(temp_df)
            except Exception:
                continue
                
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return None

def process_data(curve_file, selected_year, market_name):
    # 1. Caricamento Curva di Carico (e-distribuzione)
    df_curve = pd.read_csv(curve_file, sep=';', decimal=',')
    df_curve['Giorno'] = pd.to_datetime(df_curve['Giorno'], dayfirst=True)
    
    # 2. Caricamento automatico dal Repository
    price_60 = load_local_price_file(selected_year, "60")
    price_15 = load_local_price_file(selected_year, "15") if selected_year >= 2025 else None

    if price_60 is None:
        st.error(f"Nessun file prezzi trovato per il {selected_year} nel repository.")
        return None

    # Pulizia nomi colonne Prezzi
    price_60.columns = [str(c).replace('\n', ' ').strip() for c in price_60.columns]
    date_col = [c for c in price_60.columns if 'Data' in c or 'Date' in c][0]
    hour_col = [c for c in price_60.columns if 'Ora' in c or 'Hour' in c][0]

    results = []

    # 3. Calcolo
    for _, row_c in df_curve.iterrows():
        current_date = row_c['Giorno']
        fmt_date = int(current_date.strftime('%Y%m%d'))
        
        daily_p60 = price_60[price_60[date_col] == fmt_date]
        if daily_p60.empty: continue

        for hour in range(1, 25):
            # Prezzo orario applicato ai 4 quarti d'ora
            p_h = daily_p60[daily_p60[hour_col] == hour][market_name].values
            price_val = p_h[0] if len(p_h) > 0 else 0
            
            # Quarti d'ora della curva (00:00-00:15 è col 1, etc.)
            start_idx = (hour - 1) * 4 + 1
            q_values = row_c.iloc[start_idx : start_idx + 4].values
            
            energia_ora = sum(q_values)
            costo_orario = sum(q_values * price_val)

            res_row = {
                "Data": current_date.date(),
                "Ora": hour,
                "Energia_MWh": energia_ora,
                "Costo_Orario": costo_orario
            }

            # Calcolo 15 min per TIDE (2025+)
            if selected_year >= 2025 and price_15 is not None:
                price_15.columns = [str(c).replace('\n', ' ').strip() for c in price_15.columns]
                period_col = [c for c in price_15.columns if 'Periodo' in c or 'Period' in c][0]
                daily_p15 = price_15[price_15[date_col] == fmt_date]
                
                costo_15min_ora = 0
                for i, q_val in enumerate(q_values):
                    p_idx = (hour - 1) * 4 + (i + 1)
                    p_15_v = daily_p15[daily_p15[period_col] == p_idx][market_name].values
                    costo_15min_ora += (q_val * (p_15_v[0] if len(p_15_v) > 0 else 0))
                
                res_row["Costo_15min"] = costo_15min_ora

            results.append(res_row)

    return pd.DataFrame(results)

# --- INTERFACCIA STREAMLIT ---
st.title("⚡ Energy Multiplier (GitHub Data Mode)")

selected_year = st.sidebar.selectbox("Anno di analisi", list(range(2004, 2027)), index=22)

# Caricamento dinamico dei mercati dal primo file disponibile
sample_file = load_local_price_file(selected_year)
if sample_file is not None:
    cols = [str(c).replace('\n', ' ').strip() for c in sample_file.columns]
    ignore = ['Data', 'Date', 'Ora', 'Hour', 'Periodo', 'Period', 'N°']
    market_options = [c for c in cols if not any(x in c for x in ignore)]
    market_name = st.sidebar.selectbox("Seleziona Mercato/Zona", market_options)
else:
    st.sidebar.warning(f"File per il {selected_year} non trovati nel repository.")
    market_name = None

curve_file = st.file_uploader("Carica CSV curva di carico (e-distribuzione)", type=['csv'])

if st.button("Elabora"):
    if curve_file and market_name:
        df_res = process_data(curve_file, selected_year, market_name)
        if df_res is not None:
            # Riepilogo Mensile
            df_res['Data'] = pd.to_datetime(df_res['Data'])
            df_res['Mese'] = df_res['Data'].dt.strftime('%Y-%m')
            monthly = df_res.groupby('Mese').sum(numeric_only=True).drop(columns=['Ora'])
            
            st.subheader("Riepilogo Mensile")
            st.dataframe(monthly)
            
            st.subheader("Dettaglio Giornaliero/Orario")
            st.dataframe(df_res)

            # Export
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_res.to_excel(writer, index=False, sheet_name='Dettaglio')
                monthly.to_excel(writer, sheet_name='Sintesi_Mensile')
            
            st.download_button("📥 Scarica Report XLSX", output.getvalue(), 
                               file_name=f"Report_{selected_year}_{market_name}.xlsx")
    else:
        st.warning("Carica la curva di carico per iniziare.")
