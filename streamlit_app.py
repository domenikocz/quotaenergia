import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="GME Multiplier - Energy Analysis", layout="wide")

# Percorso principale del repository GitHub dove risiedono i file Excel
DATA_PATH = "." 

def load_price_data(year, freq="60"):
    """Cerca e carica i dati dal foglio 'Prezzi-Prices' dai file Excel nel repo."""
    all_files = os.listdir(DATA_PATH)
    dfs = []
    year_str = f"Anno {year}"
    
    for f in all_files:
        if year_str in f and f.endswith(('.xlsx', '.xls')):
            # Gestione TIDE 2025+: distingue tra file orari (_60) e quarti d'ora (_15)
            if year >= 2025:
                if freq == "15" and "_15" not in f: continue
                if freq == "60" and "_15" in f: continue
            
            try:
                # Legge specificamente il foglio indicato dall'utente
                df = pd.read_excel(os.path.join(DATA_PATH, f), sheet_name='Prezzi-Prices')
                dfs.append(df)
            except Exception as e:
                continue
                
    return pd.concat(dfs, ignore_index=True) if dfs else None

def process_data(curve_file, year, market):
    # 1. Caricamento Curva di Carico (CSV e-distribuzione)
    try:
        df_curve = pd.read_csv(curve_file, sep=';', decimal=',')
        df_curve['Giorno'] = pd.to_datetime(df_curve['Giorno'], dayfirst=True)
    except Exception as e:
        st.error(f"Errore nel formato della curva di carico: {e}")
        return None
    
    # 2. Caricamento Prezzi Orari (Base per tutti gli anni)
    p60 = load_price_data(year, "60")
    if p60 is None:
        st.error(f"File Excel per l'anno {year} non trovato nel repository.")
        return None
    
    # Pulizia nomi colonne Prezzi
    p60.columns = [str(c).replace('\n', ' ').strip() for c in p60.columns]
    date_col = [c for c in p60.columns if 'Data' in c or 'Date' in c][0]
    hour_col = [c for c in p60.columns if 'Ora' in c or 'Hour' in c][0]

    # 3. Caricamento Prezzi 15 min (Solo per 2025+ se disponibili)
    p15 = load_price_data(year, "15") if year >= 2025 else None
    if p15 is not None:
        p15.columns = [str(c).replace('\n', ' ').strip() for c in p15.columns]
        period_col = [c for c in p15.columns if 'Periodo' in c or 'Period' in c][0]

    results = []

    # 4. Ciclo di calcolo
    for _, row_c in df_curve.iterrows():
        current_date = row_c['Giorno']
        fmt_date = int(current_date.strftime('%Y%m%d'))
        
        # Filtra i prezzi per il giorno specifico
        day_p60 = p60[p60[date_col] == fmt_date]
        if day_p60.empty: continue
        
        day_p15 = p15[p15[date_col] == fmt_date] if p15 is not None else None

        for hour in range(1, 25):
            # Recupero prezzo orario
            p_h_row = day_p60[day_p60[hour_col] == hour]
            if p_h_row.empty: continue
            price_h = p_h_row[market].values[0]
            
            # Estrazione 4 quarti d'ora della curva e conversione numerica
            # Nota: le colonne iniziano dopo 'Giorno'
            q_values = row_c.iloc[(hour-1)*4 + 1 : (hour-1)*4 + 5].apply(
                lambda x: float(str(x).replace(',','.')) if isinstance(x, str) else float(x)
            ).values
            
            energia_ora = sum(q_values)
            costo_orario_base = sum(q_values * price_h)

            row_data = {
                "Data": current_date.date(),
                "Ora": hour,
                "Energia_Totale_MWh": energia_ora,
                "Costo_Prezzo_Orario": costo_orario_base
            }

            # Logica aggiuntiva TIDE per 2025+
            if year >= 2025 and day_p15 is not None:
                costo_15min_tide = 0
                for i, q in enumerate(q_values):
                    periodo = (hour-1)*4 + (i+1)
                    p_15_val = day_p15[day_p15[period_col] == periodo][market].values
                    if len(p_15_val) > 0:
                        costo_15min_tide += (q * p_15_val[0])
                row_data["Costo_Prezzo_15min_TIDE"] = costo_15min_tide
                
            results.append(row_data)
            
    return pd.DataFrame(results)

# --- INTERFACCIA STREAMLIT ---
st.title("⚡ Energy Multiplier - Analisi Mercato Elettrico")

# Sidebar di configurazione
selected_year = st.sidebar.selectbox("Seleziona Anno di Analisi", list(range(2004, 2027)), index=21)

# Caricamento mercati (PUN, Zone) dal primo file disponibile per l'anno
sample_data = load_price_data(selected_year)
if sample_data is not None:
    sample_data.columns = [str(c).replace('\n', ' ').strip() for c in sample_data.columns]
    ignore = ['Data', 'Date', 'Ora', 'Hour', 'Periodo', 'Period', 'N°', 'N.']
    market_options = [c for c in sample_data.columns if not any(x in c for x in ignore)]
    selected_market = st.sidebar.selectbox("Seleziona Mercato/Zona", market_options)
    
    # Upload curva di carico
    curve_file = st.file_uploader("Allega la Curva di Carico e-distribuzione (CSV)", type=['csv'])

    if st.button("Avvia Elaborazione"):
        if curve_file:
            df_final = process_data(curve_file, selected_year, selected_market)
            if df_final is not None:
                st.success(f"Elaborazione completata per l'anno {selected_year} ({selected_market})")
                
                # Raggruppamento Mensile
                df_final['Data'] = pd.to_datetime(df_final['Data'])
                df_final['Mese'] = df_final['Data'].dt.strftime('%Y-%m')
                monthly_summary = df_final.groupby('Mese').sum(numeric_only=True).drop(columns=['Ora'])
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("### Riepilogo Mensile")
                    st.dataframe(monthly_summary)
                with col2:
                    st.write("### Dettaglio Giornaliero/Orario")
                    st.dataframe(df_final)

                # Export Excel
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Dettaglio')
                    monthly_summary.to_excel(writer, sheet_name='Sintesi_Mensile')
                
                st.download_button(
                    label="📥 Scarica Report Excel (.xlsx)",
                    data=output.getvalue(),
                    file_name=f"Analisi_Energia_{selected_year}_{selected_market}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.warning("Carica un file CSV delle curve di carico per procedere.")
else:
    st.sidebar.error(f"Attenzione: file Excel per l'anno {selected_year} non trovati nel repository.")
