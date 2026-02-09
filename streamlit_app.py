import streamlit as st
import pandas as pd
import os
from io import BytesIO

st.set_page_config(page_title="GME Multiplier", layout="wide")

DATA_PATH = os.getcwd()

def get_best_sheet(xl_file):
    sheet_names = xl_file.sheet_names
    for s in sheet_names:
        if "prezzi" in s.lower() or "prices" in s.lower():
            return s
    return sheet_names[0]

@st.cache_data
def load_year_data(year, freq="60"):
    try:
        all_entries = os.listdir(DATA_PATH)
        target_files = [f for f in all_entries if str(year) in f and f.lower().endswith(('.xlsx', '.xls'))]
        
        if year >= 2025:
            if freq == "15":
                target_files = [f for f in target_files if "_15" in f]
            else:
                target_files = [f for f in target_files if "_60" in f or ("_15" not in f and year >= 2025)]
        
        if not target_files: return None

        dfs = []
        for f in target_files:
            xl = pd.ExcelFile(os.path.join(DATA_PATH, f))
            df = xl.parse(get_best_sheet(xl))
            dfs.append(df)
        return pd.concat(dfs, ignore_index=True) if dfs else None
    except:
        return None

st.title("⚡ Energy Cost Calculator")

year = st.sidebar.selectbox("Anno", list(range(2004, 2027)), index=21)
p_data = load_year_data(year, "60")

if p_data is not None:
    p_data.columns = [str(c).replace('\n', ' ').strip() for c in p_data.columns]
    d_col = next(c for c in p_data.columns if 'data' in c.lower() or 'date' in c.lower())
    h_col = next(c for c in p_data.columns if 'ora' in c.lower() or 'hour' in c.lower())
    
    # Pulizia mercati
    ignore = ['Data', 'Date', 'Ora', 'Hour', 'Periodo', 'Period', 'N°', 'N.']
    markets = [c for c in p_data.columns if not any(x in c for x in ignore)]
    market = st.sidebar.selectbox("Mercato", markets)
    
    curve_file = st.file_uploader("Carica Curva (CSV)", type=['csv'])

    if st.button("Calcola"):
        if curve_file:
            df_c = pd.read_csv(curve_file, sep=';', decimal=',')
            df_c['Giorno'] = pd.to_datetime(df_c['Giorno'], dayfirst=True)
            
            # Normalizzazione date prezzi
            p_data[d_col] = p_data[d_col].astype(str).str.split('.').str[0].str.strip()

            p15 = load_year_data(year, "15") if year >= 2025 else None
            if p15 is not None:
                p15.columns = [str(c).replace('\n', ' ').strip() for c in p15.columns]
                p15[d_col] = p15[d_col].astype(str).str.split('.').str[0].str.strip()
                per_col = next(c for c in p15.columns if 'period' in c.lower() or 'periodo' in c.lower())

            results = []
            for _, row_c in df_c.iterrows():
                dt_str = row_c['Giorno'].strftime('%Y%m%d')
                day_p = p_data[p_data[d_col] == dt_str]
                
                if day_p.empty: continue
                
                day_p15 = p15[p15[d_col] == dt_str] if p15 is not None else None

                for h in range(1, 25):
                    try:
                        p_val = day_p[day_p[h_col] == h][market].values[0]
                        # Estrazione valori 15min e pulizia
                        q_vals = row_c.iloc[(h-1)*4 + 1 : (h-1)*4 + 5].apply(lambda x: float(str(x).replace(',', '.'))).values
                        
                        res = {"Data": row_c['Giorno'].date(), "Ora": h, "Energia_MWh": sum(q_vals), "Costo_Orario": sum(q_vals * p_val)}
                        
                        if year >= 2025 and day_p15 is not None:
                            c15 = 0
                            for i, q in enumerate(q_vals):
                                p15_val = day_p15[day_p15[per_col] == ((h-1)*4 + (i+1))][market].values[0]
                                c15 += (q * p15_val)
                            res["Costo_15min_TIDE"] = c15
                        results.append(res)
                    except: continue

            if results:
                final = pd.DataFrame(results)
                final['Mese'] = pd.to_datetime(final['Data']).dt.strftime('%Y-%m')
                summary = final.groupby('Mese').sum(numeric_only=True).drop(columns=['Ora'])
                
                st.write("### Riepilogo Mensile")
                st.table(summary)
                st.write("### Dettaglio")
                st.dataframe(final)
                
                buf = BytesIO()
                with pd.ExcelWriter(buf, engine='openpyxl') as w:
                    final.to_excel(w, index=False, sheet_name='Dettaglio')
                    summary.to_excel(w, sheet_name='Sintesi')
                st.download_button("📥 Scarica Excel", buf.getvalue(), f"Risultato_{year}.xlsx")
            else:
                st.error("Nessuna corrispondenza trovata. Controlla che le date nella curva (es. 01/08/2025) siano presenti nei file dei prezzi.")
else:
    st.error(f"File Excel non trovati per il {year}.")
    with st.expander("Controlla file nel repository"):
        st.write(os.listdir(DATA_PATH))
