import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="GME Multiplier", layout="wide")

# Percorso radice del repository
DATA_PATH = os.getcwd()

def format_euro(val):
    """Formatta i numeri in stile europeo: 17.303,4262"""
    if pd.isna(val): return ""
    # Formatta con 4 decimali, usa virgola per decimali e punto per migliaia
    return "{:,.4f}".format(val).replace(",", "X").replace(".", ",").replace("X", ".")

def get_best_sheet(xl_file):
    """Trova il foglio prezzi nei file Excel."""
    sheet_names = xl_file.sheet_names
    for s in sheet_names:
        if "prezzi-prices" in s.lower().replace(" ", ""):
            return s
    for s in sheet_names:
        if "prezzi" in s.lower() or "prices" in s.lower():
            return s
    return sheet_names[0]

@st.cache_data
def load_year_data(year):
    """Carica i file dal repository usando la stessa regola per tutti gli anni."""
    try:
        all_entries = os.listdir(DATA_PATH)
        # Cerca file che contengono l'anno e hanno estensione Excel o CSV
        target_files = [f for f in all_entries if f"Anno {year}" in f and f.lower().endswith(('.xlsx', '.xls', '.csv'))]
        
        if not target_files: return None

        combined_dfs = []
        for f in target_files:
            full_path = os.path.join(DATA_PATH, f)
            try:
                if f.lower().endswith('.csv'):
                    df = pd.read_csv(full_path, sep=None, engine='python')
                else:
                    xl = pd.ExcelFile(full_path)
                    df = xl.parse(get_best_sheet(xl))
                combined_dfs.append(df)
            except:
                continue
        return pd.concat(combined_dfs, ignore_index=True) if combined_dfs else None
    except:
        return None

# --- INTERFACCIA ---
st.title("⚡ Energy Cost Calculator")

year = st.sidebar.selectbox("Anno", list(range(2004, 2027)), index=21)
p_data = load_year_data(year)

if p_data is not None:
    # Pulizia nomi colonne Prezzi
    p_data.columns = [str(c).replace('\n', ' ').strip() for c in p_data.columns]
    
    try:
        d_col = next(c for c in p_data.columns if 'data' in c.lower() or 'date' in c.lower())
        h_col = next(c for c in p_data.columns if 'ora' in c.lower() or 'hour' in c.lower())
    except StopIteration:
        st.error("Colonne Data/Ora non trovate nel file prezzi.")
        st.stop()
    
    ignore = ['Data', 'Date', 'Ora', 'Hour', 'Periodo', 'Period', 'N°', 'N.']
    markets = [c for c in p_data.columns if not any(x in c.lower() for x in ignore)]
    market = st.sidebar.selectbox("Seleziona Mercato", markets)
    
    curve_file = st.file_uploader("Carica Curva e-distribuzione (CSV)", type=['csv'])

    if st.button("Esegui Calcolo"):
        if curve_file:
            try:
                # Caricamento curva: Giorno;00:00-00:15...
                df_c = pd.read_csv(curve_file, sep=';', decimal=',', quotechar='"')
                g_col = [c for c in df_c.columns if 'giorno' in c.lower()][0]
                df_c[g_col] = pd.to_datetime(df_c[g_col], dayfirst=True)
            except Exception as e:
                st.error(f"Errore caricamento curva: {e}")
                st.stop()
            
            # Normalizzazione date prezzi (formato YYYYMMDD)
            p_data[d_col] = p_data[d_col].astype(str).str.split('.').str[0].str.strip()

            results = []
            for _, row_c in df_c.iterrows():
                dt_str = row_c[g_col].strftime('%Y%m%d')
                day_p = p_data[p_data[d_col] == dt_str]
                if day_p.empty: continue

                for h in range(1, 25):
                    try:
                        p_row = day_p[day_p[h_col].astype(float).astype(int) == h]
                        if p_row.empty: continue
                        p_val = p_row[market].values[0]
                        
                        # Consumo in kWh dai 4 quarti d'ora
                        q_vals = row_c.iloc[(h-1)*4 + 1 : (h-1)*4 + 5].apply(
                            lambda x: float(str(x).replace(',', '.')) if isinstance(x, str) else float(x)
                        ).values
                        
                        energia_h_kwh = sum(q_vals)
                        # Costo: (kWh * Prezzo_MWh) / 1000
                        costo_h = (energia_h_kwh * p_val) / 1000
                        
                        res = {
                            "Data": row_c[g_col].date(), 
                            "Ora": h, 
                            "Energia_Tot_kWh": energia_h_kwh,
                            "Prezzo_MWh": p_val,
                            "Costo_Prezzo_Orario": costo_h
                        }
                        results.append(res)
                    except: continue

            if results:
                final = pd.DataFrame(results)
                
                # Calcolo riepilogo mensile prima della formattazione
                final_for_sum = final.copy()
                final_for_sum['Mese'] = pd.to_datetime(final_for_sum['Data']).dt.strftime('%Y-%m')
                summary = final_for_sum.groupby('Mese').sum(numeric_only=True).drop(columns=['Ora', 'Prezzo_MWh'])
                
                # Visualizzazione a video con formattazione europea
                view_df = final.copy()
                for col in ["Energia_Tot_kWh", "Prezzo_MWh", "Costo_Prezzo_Orario"]:
                    view_df[col] = view_df[col].apply(format_euro)

                st.write("### Dettaglio Orario")
                st.dataframe(view_df)

                st.write("### Riepilogo Mensile")
                st.table(summary.applymap(format_euro))
                
                # Export Excel (mantiene i numeri per i calcoli ma i fogli sono separati)
                buf = BytesIO()
                with pd.ExcelWriter(buf, engine='openpyxl') as w:
                    final.to_excel(w, index=False, sheet_name='Dettaglio')
                    summary.to_excel(w, sheet_name='Sintesi_Mensile')
                
                st.download_button(
                    label="📥 Scarica Report XLSX",
                    data=buf.getvalue(),
                    file_name=f"Analisi_{year}_{market}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("Nessuna corrispondenza trovata tra le date della curva e i prezzi.")
else:
    st.error(f"File prezzi 'Anno {year}' non trovato nel repository.")
