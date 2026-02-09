import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="GME Multiplier", layout="wide")

# Utilizziamo il percorso corrente per cercare i file nel repository
DATA_PATH = os.getcwd()

def load_price_data(year, freq="60"):
    """Cerca e carica i file Excel dal repository per l'anno e la frequenza specificata."""
    files = [f for f in os.listdir(DATA_PATH) if f.lower().endswith(('.xlsx', '.xls'))]
    dfs = []
    year_str = str(year)
    
    for f in files:
        if year_str in f:
            # Dal 2025+ separiamo orario (_60 o senza suffisso) da 15min (_15)
            if year >= 2025:
                if freq == "15" and "_15" not in f: continue
                if freq == "60" and "_15" in f: continue
            
            try:
                xl = pd.ExcelFile(os.path.join(DATA_PATH, f))
                # Cerca il foglio "Prezzi-Prices" (case-insensitive)
                target_sheet = next((s for s in xl.sheet_names if s.strip().lower() == "prezzi-prices"), None)
                if target_sheet:
                    dfs.append(xl.parse(target_sheet))
            except:
                continue
    return pd.concat(dfs, ignore_index=True) if dfs else None

st.title("⚡ Moltiplicatore Prezzi GME vs Curve di Carico")

# Selezione Anno e Mercato
selected_year = st.sidebar.selectbox("Seleziona Anno", list(range(2004, 2027)), index=21)

# Caricamento dinamico mercati
p_data_60 = load_price_data(selected_year, "60")

if p_data_60 is not None:
    p_data_60.columns = [str(c).replace('\n', ' ').strip() for c in p_data_60.columns]
    ignore = ['Data', 'Date', 'Ora', 'Hour', 'Periodo', 'Period', 'N°', 'N.']
    market_options = [c for c in p_data_60.columns if not any(x in c for x in ignore)]
    selected_market = st.sidebar.selectbox("Seleziona Mercato", market_options)
    
    curve_file = st.file_uploader("Allega Curva di Carico CSV (e-distribuzione)", type=['csv'])

    if st.button("Esegui Calcolo"):
        if curve_file:
            # Caricamento curva
            df_curve = pd.read_csv(curve_file, sep=';', decimal=',')
            df_curve['Giorno'] = pd.to_datetime(df_curve['Giorno'], dayfirst=True)
            
            # Colonne chiave file prezzi
            date_col = next(c for c in p_data_60.columns if 'Data' in c or 'Date' in c)
            hour_col = next(c for c in p_data_60.columns if 'Ora' in c or 'Hour' in c)
            
            # Per 2025+ carichiamo i prezzi a 15min
            p_data_15 = load_price_data(selected_year, "15") if selected_year >= 2025 else None
            if p_data_15 is not None:
                p_data_15.columns = [str(c).replace('\n', ' ').strip() for c in p_data_15.columns]
                period_col = next(c for c in p_data_15.columns if 'Periodo' in c or 'Period' in c)

            results = []
            for _, row_c in df_curve.iterrows():
                fmt_date = int(row_c['Giorno'].strftime('%Y%m%d'))
                day_p60 = p_data_60[p_data_60[date_col] == fmt_date]
                if day_p60.empty: continue
                
                day_p15 = p_data_15[p_data_15[date_col] == fmt_date] if p_data_15 is not None else None
                
                for hour in range(1, 25):
                    # Prezzo orario
                    p_h_row = day_p60[day_p60[hour_col] == hour]
                    if p_h_row.empty: continue
                    price_h = p_h_row[selected_market].values[0]
                    
                    # Quarti d'ora della curva (colonne 1-4 per ora 1, etc.)
                    q_vals = row_c.iloc[(hour-1)*4 + 1 : (hour-1)*4 + 5].replace(',', '.', regex=True).astype(float).values
                    
                    hourly_res = {
                        "Data": row_c['Giorno'].date(),
                        "Ora": hour,
                        "Energia_Totale_MWh": sum(q_vals),
                        "Costo_Prezzo_Orario": sum(q_vals * price_h)
                    }
                    
                    # Colonna extra TIDE (15min) per 2025+
                    if selected_year >= 2025 and day_p15 is not None:
                        costo_15 = 0
                        for i, q in enumerate(q_vals):
                            p_idx = (hour-1)*4 + (i+1)
                            p_15_v = day_p15[day_p15[period_col] == p_idx][selected_market].values
                            if len(p_15_v) > 0:
                                costo_15 += (q * p_15_v[0])
                        hourly_res["Costo_Prezzo_15min_TIDE"] = costo_15
                        
                    results.append(hourly_res)
            
            final_df = pd.DataFrame(results)
            final_df['Mese'] = pd.to_datetime(final_df['Data']).dt.strftime('%Y-%m')
            summary = final_df.groupby('Mese').sum(numeric_only=True).drop(columns=['Ora'])
            
            st.success("Elaborazione completata!")
            st.write("### Riepilogo Mensile")
            st.dataframe(summary)
            
            # Download
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False, sheet_name='Dettaglio')
                summary.to_excel(writer, sheet_name='Mensile')
            st.download_button("📥 Scarica Report XLSX", output.getvalue(), file_name=f"Analisi_{selected_year}.xlsx")
        else:
            st.warning("Carica il file della curva di carico per procedere.")
else:
    st.error(f"Nessun file Excel per l'anno {selected_year} trovato nel repository. Verifica che i file siano nella root e contengano l'anno nel nome.")
