import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Energy Multiplier GME & E-Distribuzione", layout="wide")

## --- FUNZIONI DI CALCOLO ---

def process_data(price_files, curve_file, selected_year, market_col):
    # 1. Caricamento Curva di Carico (15 min)
    # Assumiamo formato: Giorno; 00:00-00:15; ...
    df_curve = pd.read_csv(curve_file, sep=';', decimal=',')
    df_curve['Giorno'] = pd.to_datetime(df_curve['Giorno'], dayfirst=True)
    
    # 2. Caricamento Prezzi (Cerca il file corrispondente all'anno tra quelli caricati)
    price_df = pd.DataFrame()
    for f in price_files:
        if str(selected_year) in f.name:
            # Gestione CSV (caricati via Streamlit)
            price_df = pd.read_csv(f)
            break
    
    if price_df.empty:
        st.error(f"File prezzi per l'anno {selected_year} non trovato tra gli allegati.")
        return None

    # Normalizzazione nomi colonne prezzi
    price_df.columns = [c.replace('\n', ' ').strip() for c in price_df.columns]
    date_col = [c for c in price_df.columns if 'Data' in c][0]
    hour_col = [c for c in price_df.columns if 'Ora' in c][0]
    
    results = []

    # 3. Logica di Calcolo
    if selected_year < 2025:
        # LOGICA PRE-2025: Prezzo Orario * 4 Quarti d'ora
        for _, row_c in df_curve.iterrows():
            current_date = row_c['Giorno']
            formatted_date = int(current_date.strftime('%Y%m%d'))
            
            # Filtra prezzi per quel giorno
            daily_prices = price_df[price_df[date_col] == formatted_date]
            
            for hour in range(1, 25):
                p_hour = daily_prices[daily_prices[hour_col] == hour][market_col].values
                if len(p_hour) > 0:
                    price = p_hour[0]
                    # Prendi i 4 quarti d'ora corrispondenti (es. Ora 1 = colonne 1,2,3,4 della curva)
                    start_col = (hour - 1) * 4 + 1
                    q_values = row_c.iloc[start_col : start_col + 4].values
                    total_cost = sum(q_values * price)
                    results.append({
                        "Data": current_date.date(),
                        "Ora": hour,
                        "Costo_Totale": total_cost,
                        "Energia_Tot": sum(q_values)
                    })
    else:
        # LOGICA 2025+: Prezzo 15min * Quarto d'ora corrispondente
        # Nota: Si assume che il file prezzi 2025+ abbia la colonna 'Periodo' (1-96)
        period_col = "Periodo / Period"
        for _, row_c in df_curve.iterrows():
            current_date = row_c['Giorno']
            formatted_date = int(current_date.strftime('%Y%m%d'))
            daily_prices = price_df[price_df[date_col] == formatted_date]
            
            day_total = 0
            for period in range(1, 97):
                p_period = daily_prices[daily_prices[period_col] == period][market_col].values
                if len(p_period) > 0:
                    price = p_period[0]
                    q_value = row_c.iloc[period] # Colonna corrispondente al quarto d'ora
                    day_total += (q_value * price)
            
            results.append({
                "Data": current_date.date(),
                "Costo_Totale_15min": day_total
            })

    return pd.DataFrame(results)

## --- INTERFACCIA STREAMLIT ---

st.title("⚡ Moltiplicatore Prezzi GME vs Curve di Carico")

with st.sidebar:
    st.header("Configurazione")
    selected_year = st.selectbox("Seleziona Anno", list(range(2004, 2027)), index=21)
    # Lista mercati (esempi basati sui tuoi file)
    market_col = st.selectbox("Seleziona Mercato", ["PUN", "NORD", "CNOR", "CSUD", "SUD", "SICI", "SARD"])
    
    st.subheader("1. Carica File Prezzi (Database)")
    price_files = st.file_uploader("Allega i CSV dei prezzi (es. Anno 2024_Prezzi.csv)", accept_multiple_files=True)
    
    st.subheader("2. Carica Curva di Carico")
    curve_file = st.file_uploader("Allega CSV e-distribuzione (15 min)", type=['csv'])

if st.button("Esegui Calcolo"):
    if price_files and curve_file:
        res_df = process_data(price_files, curve_file, selected_year, market_col)
        
        if res_df is not None:
            st.success("Elaborazione completata!")
            
            # Riepilogo mensile
            res_df['Data'] = pd.to_datetime(res_df['Data'])
            res_df['Mese'] = res_df['Data'].dt.strftime('%Y-%m')
            monthly_summary = res_df.groupby('Mese').sum(numeric_only=True)
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Dettaglio Giornaliero")
                st.dataframe(res_df)
            with col2:
                st.subheader("Riepilogo Mensile")
                st.dataframe(monthly_summary)
            
            # Download Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                res_df.to_excel(writer, index=False, sheet_name='Dettaglio')
                monthly_summary.to_excel(writer, sheet_name='Riepilogo_Mensile')
            
            st.download_button(
                label="📥 Scarica Risultati (XLSX)",
                data=output.getvalue(),
                file_name=f"Report_Energia_{selected_year}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.warning("Assicurati di aver caricato sia i file prezzi che la curva di carico.")
