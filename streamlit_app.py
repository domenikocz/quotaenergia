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
    try:
        val = float(val)
        # Formatta con 4 decimali, usa virgola per decimali e punto per migliaia
        return "{:,.4f}".format(val).replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return val

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
        # Filtra i file che contengono l'anno e hanno estensione Excel o CSV
        # Ignora i file con "_15" per il 2025/2026 come richiesto per usare la regola oraria
        target_files = [f for f in all_entries if f"Anno {year}" in f and f.lower().endswith(('.xlsx', '.xls', '.csv'))]
        
        if year >= 2025:
            target_files = [f for f in target_files if "_15" not in f]
        
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

# Sidebar per la selezione dell'anno
year = st.sidebar.selectbox("Anno", list(range(2004, 2027)), index=21)
p_data = load_year_data(year)

if p_data is not None:
    # Pulizia nomi colonne Prezzi
    p_data.columns = [str(c).replace('\n', ' ').strip() for c in p_data.columns]
    
    try:
        # Identificazione colonne Data e Ora nei prezzi
        d_col = next(c for c in p_data.columns if 'data' in c.lower() or 'date' in c.lower())
        h_col = next(c for c in p_data.columns if 'ora' in c.lower() or 'hour' in c.lower())
    except StopIteration:
        st.error("Colonne Data/Ora non trovate nel file prezzi.")
        st.stop()
    
    # Identificazione dei mercati disponibili
    ignore = ['Data', 'Date', 'Ora', 'Hour', 'Periodo', 'Period', 'N°', 'N.']
    markets = [c for c in p_data.columns if not any(x in c.lower() for x in ignore)]
    market = st.sidebar.selectbox("Seleziona Mercato/Zona", markets)
    
    # Caricamento file curva di carico
    curve_file = st.file_uploader("Carica Curva e-distribuzione (CSV)", type=['csv'])

    if st.button("Esegui Calcolo"):
        if curve_file:
            try:
                # Caricamento curva con separatore ; e virgola decimale
                df_c = pd.read_csv(curve_file, sep=';', decimal=',', quotechar='"')
                g_col = [c for c in df_c.columns if 'giorno' in c.lower()][0]
                # Conversione data curva in oggetto datetime per matching robusto
                df_c[g_col] = pd.to_datetime(df_c[g_col], dayfirst=True)
            except Exception as e:
                st.error(f"Errore caricamento curva: {e}")
                st.stop()
            
            # Sincronizzazione date file prezzi (trasformazione in datetime)
            try:
                p_data['match_date'] = pd.to_datetime(p_data[d_col].astype(str).str.split('.').str[0], format='%Y%m%d')
            except Exception as e:
                st.error(f"Errore formattazione date nel file prezzi: {e}")
                st.stop()

            results = []
            # Elaborazione riga per riga (ogni riga è un giorno)
            for _, row_c in df_c.iterrows():
                curr_date = row_c[g_col]
                day_p = p_data[p_data['match_date'] == curr_date]
                
                if day_p.empty: continue

                # Elaborazione delle 24 ore
                for h in range(1, 25):
                    try:
                        p_row = day_p[day_p[h_col].astype(float).astype(int) == h]
                        if p_row.empty: continue
                        p_val = p_row[market].values[0]
                        
                        # Estrazione dei 4 quarti d'ora (Energia in kWh)
                        q_vals = row_c.iloc[(h-1)*4 + 1 : (h-1)*4 + 5].apply(
                            lambda x: float(str(x).replace(',', '.')) if isinstance(x, str) else float(x)
                        ).values
                        
                        energia_h_kwh = sum(q_vals)
                        # Calcolo Costo (€): (Energia_kWh * Prezzo_MWh) / 1000
                        costo_h = (energia_h_kwh * p_val) / 1000
                        
                        results.append({
                            "Data": curr_date.date(), 
                            "Ora": h, 
                            "Energia_Tot_kWh": energia_h_kwh,
                            "Prezzo_MWh": p_val,
                            "Costo_Prezzo_Orario": costo_h
                        })
                    except: continue

            if results:
                final = pd.DataFrame(results)
                
                # Calcolo riepilogo mensile prima della formattazione estetica
                final_for_sum = final.copy()
                final_for_sum['Mese'] = pd.to_datetime(final_for_sum['Data']).dt.strftime('%Y-%m')
                summary = final_for_sum.groupby('Mese').sum(numeric_only=True).drop(columns=['Ora', 'Prezzo_MWh'])
                
                # Formattazione europea per la visualizzazione
                view_df = final.copy()
                for col in ["Energia_Tot_kWh", "Prezzo_MWh", "Costo_Prezzo_Orario"]:
                    view_df[col] = view_df[col].apply(format_euro)

                st.write("### Dettaglio Orario")
                st.dataframe(view_df)

                st.write("### Riepilogo Mensile")
                st.table(summary.map(format_euro))
                
                # Esportazione in Excel (mantiene i valori numerici per calcoli successivi)
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
                st.error("Nessuna corrispondenza trovata tra le date della curva e i prezzi. Verifica che i file nel repository coprano il periodo della curva.")
else:
    st.error(f"⚠️ File prezzi 'Anno {year}' non trovato nel repository GitHub.")
