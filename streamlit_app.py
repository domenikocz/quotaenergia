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
    return "{:,.4f}".format(val).replace(",", "X").replace(".", ",").replace("X", ".")

def get_best_sheet(xl_file):
    sheet_names = xl_file.sheet_names
    for s in sheet_names:
        if "prezzi-prices" in s.lower().replace(" ", ""):
            return s
    for s in sheet_names:
        if "prezzi" in s.lower() or "prices" in s.lower():
            return s
    return sheet_names[0]

@st.cache_data
def load_year_data(year, freq="60"):
    try:
        all_entries = os.listdir(DATA_PATH)
        target_files = [f for f in all_entries if str(year) in f and f.lower().endswith(('.xlsx', '.xls', '.csv'))]
        
        if year >= 2025:
            if freq == "15":
                target_files = [f for f in target_files if "_15" in f]
            else:
                target_files = [f for f in target_files if "_60" in f or ("_15" not in f and "_60" not in f)]
        
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

# --- UI INTERFACCIA ---
st.title("⚡ Energy Cost Calculator (kWh/MWh)")

year = st.sidebar.selectbox("Anno", list(range(2004, 2027)), index=21)
p_data = load_year_data(year, "60")

if p_data is not None:
    p_data.columns = [str(c).replace('\n', ' ').strip() for c in p_data.columns]
    d_col = next(c for c in p_data.columns if 'data' in c.lower() or 'date' in c.lower())
    h_col = next(c for c in p_data.columns if 'ora' in c.lower() or 'hour' in c.lower())
    
    ignore = ['Data', 'Date', 'Ora', 'Hour', 'Periodo', 'Period', 'N°', 'N.']
    markets = [c for c in p_data.columns if not any(x in c.lower() for x in ignore)]
    market = st.sidebar.selectbox("Seleziona Mercato", markets)
    
    curve_file = st.file_uploader("Carica Curva e-distribuzione (CSV)", type=['csv'])

    if st.button("Esegui Calcolo"):
        if curve_file:
            df_c = pd.read_csv(curve_file, sep=';', decimal=',', quotechar='"')
            g_col = [c for c in df_c.columns if 'giorno' in c.lower()][0]
            df_c[g_col] = pd.to_datetime(df_c[g_col], dayfirst=True)
            
            p_data[d_col] = p_data[d_col].astype(str).str.split('.').str[0].str.strip()

            p15 = load_year_data(year, "15") if year >= 2025 else None
            if p15 is not None:
                p15.columns = [str(c).replace('\n', ' ').strip() for c in p15.columns]
                p15[d_col] = p15[d_col].astype(str).str.split('.').str[0].str.strip()
                per_col = next((c for c in p15.columns if 'period' in c.lower() or 'periodo' in c.lower()), None)

            results = []
            for _, row_c in df_c.iterrows():
                dt_str = row_c[g_col].strftime('%Y%m%d')
                day_p = p_data[p_data[d_col] == dt_str]
                if day_p.empty: continue
                
                day_p15 = p15[p15[d_col] == dt_str] if p15 is not None else None

                for h in range(1, 25):
                    try:
                        p_row = day_p[day_p[h_col].astype(float).astype(int) == h]
                        if p_row.empty: continue
                        p_val = p_row[market].values[0]
                        
                        q_vals = row_c.iloc[(h-1)*4 + 1 : (h-1)*4 + 5].apply(
                            lambda x: float(str(x).replace(',', '.')) if isinstance(x, str) else float(x)
                        ).values
                        
                        # Calcolo: (kWh * PrezzoMWh) / 1000
                        res = {
                            "Data": row_c[g_col].date(), 
                            "Ora": h, 
                            "Energia_Tot_kWh": sum(q_vals), 
                            "Costo_Prezzo_Orario": (sum(q_vals) * p_val) / 1000
                        }
                        
                        if year >= 2025 and day_p15 is not None and per_col:
                            c15 = 0
                            for i, q in enumerate(q_vals):
                                p_idx = (h-1)*4 + (i+1)
                                p15_row = day_p15[day_p15[per_col].astype(float).astype(int) == p_idx]
                                if not p15_row.empty:
                                    c15 += (q * p15_row[market].values[0]) / 1000
                            res["Costo_Prezzo_15min_TIDE"] = c15
                        
                        results.append(res)
                    except: continue

            if results:
                final = pd.DataFrame(results)
                
                # Riepilogo Mensile (calcolato prima di rimuovere il riferimento temporale)
                final_for_sum = final.copy()
                final_for_sum['Mese'] = pd.to_datetime(final_for_sum['Data']).dt.strftime('%Y-%m')
                summary = final_for_sum.groupby('Mese').sum(numeric_only=True).drop(columns=['Ora'])
                
                # Formattazione per visualizzazione
                view_df = final.copy()
                for col in view_df.columns:
                    if "Energia" in col or "Costo" in col:
                        view_df[col] = view_df[col].apply(format_euro)

                st.write("### Dettaglio Elaborato")
                st.dataframe(view_df)

                st.write("### Riepilogo Mensile")
                st.table(summary.applymap(format_euro))
                
                buf = BytesIO()
                with pd.ExcelWriter(buf, engine='openpyxl') as w:
                    final.to_excel(w, index=False, sheet_name='Dettaglio')
                    summary.to_excel(w, sheet_name='Sintesi_Mensile')
                st.download_button("📥 Scarica Report XLSX", buf.getvalue(), f"Analisi_{year}.xlsx")
            else:
                st.error("Nessuna corrispondenza trovata.")
else:
    st.error(f"File prezzi per l'anno {year} non trovati.")
