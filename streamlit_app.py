import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="GME Multiplier - Energy Analysis", layout="wide")

def load_price_file(file):
    """Carica il file sia che sia CSV che Excel."""
    try:
        if file.name.endswith('.csv'):
            return pd.read_csv(file, sep=None, engine='python')
        else:
            return pd.read_excel(file)
    except Exception as e:
        st.error(f"Errore nel caricamento di {file.name}: {e}")
        return None

def process_data(price_files, curve_file, selected_year, market_name):
    # 1. Caricamento Curva di Carico
    df_curve = pd.read_csv(curve_file, sep=';', decimal=',')
    df_curve['Giorno'] = pd.to_datetime(df_curve['Giorno'], dayfirst=True)
    
    # 2. Identificazione file prezzi
    price_60 = None
    price_15 = None
    
    for f in price_files:
        fname = f.name.lower()
        if str(selected_year) in fname:
            if "_15" in fname:
                price_15 = load_price_file(f)
            elif "_60" in fname or selected_year < 2025:
                price_60 = load_price_file(f)

    if price_60 is None:
        st.error(f"Manca il file prezzi orario (_60) per il {selected_year}")
        return None

    # Pulizia colonne
    price_60.columns = [str(c).replace('\n', ' ').strip() for c in price_60.columns]
    date_col = [c for c in price_60.columns if 'Data' in c or 'Date' in c][0]
    hour_col = [c for c in price_60.columns if 'Ora' in c or 'Hour' in c][0]

    results = []

    # 3. Logica di Calcolo
    for _, row_c in df_curve.iterrows():
        current_date = row_c['Giorno']
        fmt_date = int(current_date.strftime('%Y%m%d'))
        
        daily_p60 = price_60[price_60[date_col] == fmt_date]
        if daily_p60.empty: continue

        for hour in range(1, 25):
            # Prezzo orario
            p_h = daily_p60[daily_p60[hour_col] == hour][market_name].values
            price_val = p_h[0] if len(p_h) > 0 else 0
            
            # Quarti d'ora della curva (colonne 1-4 per Ora 1, 5-8 per Ora 2...)
            start_idx = (hour - 1) * 4 + 1
            q_values = row_c.iloc[start_idx : start_idx + 4].values
            energia_ora = sum(q_values)
            costo_orario = sum(q_values * price_val)

            res_row = {
                "Data": current_date.date(),
                "Ora": hour,
                "Energia_MWh": energia_ora,
                "Costo_Prezzo_Orario": costo_orario
            }

            # 4. Calcolo Extra per 2025+ (se disponibile file _15)
            if selected_year >= 2025 and price_15 is not None:
                price_15.columns = [str(c).replace('\n', ' ').strip() for c in price_15.columns]
                period_col = [c for c in price_15.columns if 'Periodo' in c or 'Period' in c][0]
                daily_p15 = price_15[price_15[date_col] == fmt_date]
                
                # Calcola i 4 periodi (es: Ora 1 -> Periodi 1,2,3,4)
                costo_15min_ora = 0
                for i, q_val in enumerate(q_values):
                    periodo_cercato = (hour - 1) * 4 + (i + 1)
                    p_15_val = daily_p15[daily_p15[period_col] == periodo_cercato][market_name].values
                    p_val = p_15_val[0] if len(p_15_val) > 0 else 0
                    costo_15min_ora += (q_val * p_val)
                
                res_row["Costo_Prezzo_15min"] = costo_15min_ora

            results.append(res_row)

    return pd.DataFrame(results)

st.title("⚡ Elaboratore Mercato Elettrico (TIDE Ready)")

with st.sidebar:
    st.header("1. Archivio Prezzi")
    price_files = st.file_uploader("Carica file prezzi (CSV/XLSX)", accept_multiple_files=True)
    
    selected_year = st.selectbox("Anno di riferimento", list(range(2004, 2027)), index=22)
    
    st.header("2. Input Carico")
    curve_file = st.file_uploader("Carica Curva di Carico e-distribuzione", type=['csv'])

    # Selezione Mercato Dinamica
    market_name = "PUN"
    if price_files:
        first_file = load_price_file(price_files[0])
        if first_file is not None:
            cols = [str(c).replace('\n', ' ').strip() for c in first_file.columns]
            # Filtriamo solo colonne che sembrano mercati (escludiamo Data, Ora, Periodo)
            ignore = ['Data', 'Date', 'Ora', 'Hour', 'Periodo', 'Period', 'N°']
            market_options = [c for c in cols if not any(x in c for x in ignore)]
            market_name = st.selectbox("Seleziona Mercato/Zona", market_options)

if st.button("Avvia Elaborazione"):
    if price_files and curve_file:
        df_final = process_data(price_files, curve_file, selected_year, market_name)
        
        if df_final is not None:
            st.success(f"Analisi completata per l'anno {selected_year}")
            
            # Totali Mensili
            df_final['Data'] = pd.to_datetime(df_final['Data'])
            df_final['Mese'] = df_final['Data'].dt.to_period('M').astype(str)
            monthly = df_final.groupby('Mese').sum(numeric_only=True).drop(columns=['Ora'])
            
            st.subheader("Riepilogo Mensile")
            st.dataframe(monthly)
            
            st.subheader("Dettaglio Giornaliero/Orario")
            st.dataframe(df_final)

            # Download
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='Dettaglio_Orario')
                monthly.to_excel(writer, sheet_name='Sintesi_Mensile')
            
            st.download_button("📥 Scarica Report Excel", output.getvalue(), 
                               file_name=f"Analisi_{selected_year}_{market_name}.xlsx")
    else:
        st.warning("Carica i file necessari per procedere.")
