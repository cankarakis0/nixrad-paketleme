import streamlit as st
import pandas as pd
import re
import io
import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Grafik Kütüphanesi
import altair as alt

# Matplotlib Backend Fix
plt_backend = 'Agg'
try:
    import matplotlib.pyplot as plt
    plt.switch_backend(plt_backend)
except:
    pass

# =============================================================================
# 1. AYARLAR & GÜVENLİK
# =============================================================================
st.set_page_config(page_title="Nixrad Yönetim Paneli", layout="wide", initial_sidebar_state="expanded")

# Şifre Kontrol Fonksiyonu
def check_password():
    """Returns `True` if the user had a correct password."""
    def password_entered():
        if st.session_state["password"] == st.secrets["admin_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Şifreyi hafızada tutma
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Yönetici Şifresi", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Yönetici Şifresi", type="password", on_change=password_entered, key="password")
        st.error("😕 Şifre yanlış")
        return False
    else:
        return True

# Ayarlar
AYARLAR = {
    'HAVLUPAN': {'PAY_GENISLIK': 1.5, 'PAY_YUKSEKLIK': 0.5, 'PAY_DERINLIK': 0.5},
    'RADYATOR': {'PAY_GENISLIK': 3.5, 'PAY_YUKSEKLIK': 0.5, 'PAY_DERINLIK': 3.0}
}
MODEL_DERINLIKLERI = {
    'nirvana': 5.0, 'kumbaros': 4.5, 'floransa': 4.8, 'prag': 4.0,
    'lizyantus': 4.0, 'lisa': 4.5, 'akasya': 4.0, 'hazal': 3.0,
    'aspar': 4.0, 'livara': 4.5, 'livera': 4.5
}
ZORUNLU_HAVLUPANLAR = ['hazal', 'lisa', 'lizyantus', 'kumbaros']
MODEL_AGIRLIKLARI = {
    'nirvana': 1.10, 'prag': 0.71, 'livara': 0.81, 'livera': 0.81,
    'akasya': 0.75, 'aspar': 1.05
}
RENKLER = ["BEYAZ", "ANTRASIT", "SIYAH", "KROM", "ALTIN", "GRI", "KIRMIZI"]

# --- GOOGLE SHEETS BAĞLANTISI ---
@st.cache_resource
def init_connection():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except: return None

def save_to_google_sheets(veriler):
    client = init_connection()
    if client:
        try:
            sheet = client.open("Nixrad Veritabani").sheet1
            sheet.append_rows(veriler)
            return True, "Kayıt Başarılı"
        except Exception as e: return False, str(e)
    return False, "Bağlantı Hatası"

def get_data_from_google_sheets():
    client = init_connection()
    if client:
        try:
            sheet = client.open("Nixrad Veritabani").sheet1
            data = sheet.get_all_records()
            return pd.DataFrame(data)
        except: return pd.DataFrame()
    return pd.DataFrame()

# =============================================================================
# 2. HESAPLAMA FONKSİYONLARI
# =============================================================================
# (Yardımcı fonksiyonlar özetlendi)
def tr_clean_for_pdf(text):
    if not isinstance(text, str): return str(text)
    text = text.replace('\n', '<br/>')
    mapping = {'ğ': 'g', 'Ğ': 'G', 'ş': 's', 'Ş': 'S', 'ı': 'i', 'İ': 'I', 'ç': 'c', 'Ç': 'C', 'ö': 'o', 'Ö': 'O', 'ü': 'u', 'Ü': 'U'}
    for k, v in mapping.items(): text = text.replace(k, v)
    return text
def tr_lower(text): return text.replace('İ', 'i').replace('I', 'ı').lower()
def tr_upper(text): return text.replace('i', 'İ').replace('ı', 'I').upper()

def isim_kisalt(stok_adi):
    stok_upper = tr_upper(stok_adi)
    model_adi = "RADYATOR"
    for m in MODEL_DERINLIKLERI.keys():
        if tr_upper(m) in stok_upper: model_adi = tr_upper(m); break
    boyut_match = re.search(r'(\d+)\s*[/xX]\s*(\d+)', stok_adi)
    boyut = f"{boyut_match.group(1)}/{boyut_match.group(2)}" if boyut_match else ""
    renk = next((r for r in RENKLER if r in stok_upper), "")
    return tr_clean_for_pdf(f"{model_adi} {boyut} {renk}".strip())

def get_standart_paket_icerigi(tip, model_adi):
    ambalaj = "GENEL AMBALAJLAMA (Karton+ balon + Strec)"
    if tip == 'HAVLUPAN': return [(1, "Adet", "1/2 PURJOR"), (1, "Takim", "3 LU HAVLUPAN MONTAJ SETI"), (3, "Adet", "DUBEL"), (3, "Adet", "MONTAJ VIDASI"), (1, "Set", ambalaj)]
    else:
        ayak = f"{tr_clean_for_pdf(model_adi)} AYAK TAKIMI" if model_adi != "STANDART" else "RADYATOR AYAK TAKIMI"
        return [(1, "Adet", "1/2 KOR TAPA"), (1, "Adet", "1/2 PURJOR"), (1, "Takim", ayak), (8, "Adet", "DUBEL"), (8, "Adet", "MONTAJ VIDASI"), (1, "Set", ambalaj)]

def agirlik_hesapla(stok_adi, genislik_cm, yukseklik_cm, model_key):
    if model_key not in MODEL_AGIRLIKLARI: return 0
    dilim_match = re.search(r'(\d+)\s*DILIM', tr_upper(stok_adi))
    if dilim_match: dilim_sayisi = int(dilim_match.group(1))
    else:
        if model_key in ['nirvana', 'prag']: dilim_sayisi = round((genislik_cm + 1) / 8)
        elif model_key == 'akasya': dilim_sayisi = round((genislik_cm + 3) / 6)
        elif model_key in ['livara', 'livera']: dilim_sayisi = round((genislik_cm + 0.5) / 6)
        elif model_key == 'aspar': dilim_sayisi = round((genislik_cm + 1) / 10)
        else: return 0
    return round(dilim_sayisi * (yukseklik_cm / 60) * MODEL_AGIRLIKLARI[model_key], 2)

def hesapla_ve_analiz_et(stok_adi, adet):
    if not isinstance(stok_adi, str): return None
    stok_adi_islenen = tr_lower(stok_adi)
    base_derinlik, bulunan_model_key = 4.5, "standart"
    bulunan_model_adi = "Standart"
    for model, derinlik in MODEL_DERINLIKLERI.items():
        if model in stok_adi_islenen:
            base_derinlik, bulunan_model_key = derinlik, model
            bulunan_model_adi = "Livara" if model == 'livera' else model.capitalize()
            break
    tip = 'HAVLUPAN' if 'havlupan' in stok_adi_islenen or any(z in stok_adi_islenen for z in ZORUNLU_HAVLUPANLAR) else 'RADYATOR'
    paylar = AYARLAR[tip]
    boyutlar = re.search(r'(\d+)\s*[/xX]\s*(\d+)', stok_adi)
    
    if boyutlar:
        v1, v2 = int(boyutlar.group(1)) / 10, int(boyutlar.group(2)) / 10
        g, y = (v1, v2) if tip == 'HAVLUPAN' else (v2, v1)
        kutulu = [g + paylar['PAY_GENISLIK'], y + paylar['PAY_YUKSEKLIK'], base_derinlik + paylar['PAY_DERINLIK']]
        desi = round((kutulu[0] * kutulu[1] * kutulu[2]) / 3000, 2)
        kg = agirlik_hesapla(stok_adi, g, y, bulunan_model_key)
        return {
            'Adet': int(adet), 'Reçete': get_standart_paket_icerigi(tip, tr_upper(bulunan_model_adi)),
            'Etiket': {'kisa_isim': isim_kisalt(stok_adi), 'boyut_str': f"{kutulu[0]}x{kutulu[1]}x{kutulu[2]}cm", 'desi_val': desi},
            'Toplam_Desi': desi * adet, 'Toplam_Agirlik': kg * adet
        }
    return None

def manuel_hesapla(model_secimi, genislik, yukseklik, adet=1):
    model_lower = model_secimi.lower()
    tip = 'HAVLUPAN' if 'havlupan' in model_lower or any(z in model_lower for z in ZORUNLU_HAVLUPANLAR) else 'RADYATOR'
    paylar = AYARLAR[tip]
    base_derinlik, model_key = 4.5, "standart"
    for m_key, m_val in MODEL_DERINLIKLERI.items():
        if m_key in model_lower: base_derinlik, model_key = m_val, m_key; break
    
    k_en, k_boy = genislik + paylar['PAY_GENISLIK'], yukseklik + paylar['PAY_YUKSEKLIK']
    k_derin = base_derinlik + paylar['PAY_DERINLIK']
    return round((k_en * k_boy * k_derin) / 3000, 2), f"{k_en}x{k_boy}x{k_derin}cm", round(agirlik_hesapla("", genislik, yukseklik, model_key) * adet, 2)

# PDF Fonksiyonları (Eski kodun aynısı)
def create_cargo_pdf(proje_toplam_desi, toplam_parca, musteri_bilgileri, etiket_listesi):
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1*cm, leftMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm); elements = []
    styles = getSampleStyleSheet()
    # Header
    elements.append(Table([[
        [Paragraph("<b>GONDEREN FIRMA:</b>", styles['Normal']), Paragraph("NIXRAD / KARPAN DIZAYN A.S.", styles['Normal'])],
        [Paragraph("<b>ODEME TIPI:</b>", styles['Normal']), Paragraph(f"<b>{tr_clean_for_pdf(musteri_bilgileri.get('ODEME_TIPI', 'ALICI'))} ODEMELI</b>", styles['Title'])]
    ]], colWidths=[13*cm, 6*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 1, colors.black), ('GRID', (0,0), (-1,-1), 1, colors.black)])))
    elements.append(Spacer(1, 0.5*cm))
    # Alıcı
    elements.append(Table([[
        [Paragraph("<b>ALICI MUSTERI:</b>", styles['Normal']), Paragraph(f"<b>{tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'])}</b>", styles['Title']), Paragraph(f"<b>Tel:</b> {musteri_bilgileri['TELEFON']}<br/><b>ADRES:</b> {tr_clean_for_pdf(musteri_bilgileri['ADRES'])}", styles['Normal'])]
    ]], colWidths=[19*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 2, colors.black)])))
    elements.append(Spacer(1, 0.5*cm))
    # Paket Listesi
    pkt_data = [['Koli No', 'Urun Adi', 'Olcu', 'Desi']] + [[f"#{p['sira_no']}", tr_clean_for_pdf(p['kisa_isim']), p['boyut_str'], str(p['desi_val'])] for i, p in enumerate(etiket_listesi) if i < 15]
    elements.append(Table(pkt_data, colWidths=[2*cm, 11*cm, 4*cm, 2*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)])))
    elements.append(Spacer(1, 0.5*cm))
    # Özet
    elements.append(Table([[f"TOPLAM PARCA: {toplam_parca}", f"TOPLAM DESI: {proje_toplam_desi:.2f}"]], colWidths=[9.5*cm, 9.5*cm], style=TableStyle([('ALIGN', (1,0), (1,0), 'RIGHT'), ('FONTSIZE', (0,0), (-1,-1), 14)])))
    doc.build(elements); buffer.seek(0); return buffer

def create_production_pdf(tum_malzemeler, etiket_listesi, musteri_bilgileri):
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.5*cm, leftMargin=0.5*cm, topMargin=1*cm, bottomMargin=1*cm); elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"URETIM & PAKETLEME EMRI - {tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'])}", styles['Title']))
    data = [['MALZEME ADI', 'ADET', 'KONTROL']] + [[Paragraph(tr_clean_for_pdf(m), styles['Normal']), f"{int(v)}" if v%1==0 else f"{v:.1f}", "___"] for m, v in tum_malzemeler.items()]
    elements.append(Table(data, colWidths=[14*cm, 2*cm, 3*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)])))
    elements.append(Spacer(1, 1*cm))
    # Etiketler (Kısaltıldı)
    sticker_data = []
    row = []
    for p in etiket_listesi:
        box = Table([[f"#{p['sira_no']}"], [tr_clean_for_pdf(p['kisa_isim'])], [p['boyut_str']], [f"Desi: {p['desi_val']}"]], colWidths=[5.8*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 1, colors.black)]))
        row.append(box)
        if len(row)==3: sticker_data.append(row); row = []
    if row: sticker_data.append(row)
    if sticker_data: elements.append(Table(sticker_data, colWidths=[6.5*cm]*3))
    doc.build(elements); buffer.seek(0); return buffer

# =============================================================================
# 3. ARAYÜZ
# =============================================================================

st.markdown("""# 📦 NIXRAD Üretim & Satış Paneli""", unsafe_allow_html=True)

# Sidebar - Herkes Görebilir
st.sidebar.header("Müşteri Bilgileri")
ad_soyad = st.sidebar.text_input("Firma / Müşteri Adı")
tarih_secimi = st.sidebar.date_input("Tarih", datetime.date.today())
telefon = st.sidebar.text_input("Telefon")
adres = st.sidebar.text_area("Adres")
odeme_tipi = st.sidebar.radio("Ödeme Tipi", ["ALICI", "PEŞİN"], index=0)
musteri_data = {'AD_SOYAD': ad_soyad, 'TELEFON': telefon, 'ADRES': adres, 'ODEME_TIPI': odeme_tipi}

# Sekmeler
tab_dosya, tab_manuel, tab_rapor = st.tabs(["📂 Dosya ile Hesapla", "🧮 Manuel Hesapla", "📊 Yönetim Paneli (Şifreli)"])

# --- TAB 1: DOSYA İLE HESAPLAMA ---
with tab_dosya:
    uploaded_file = st.file_uploader("Dia Excel Dosyasını Yükle", type=['xls', 'xlsx', 'csv'])
    if uploaded_file:
        try:
            df_raw = pd.read_csv(uploaded_file, encoding='utf-8') if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            
            # Başlık Bulma
            header_idx = -1
            for i, r in df_raw.iterrows():
                if "Stok Adı" in " ".join([str(v) for v in r.values]): header_idx = i; break
            
            if header_idx != -1:
                df = df_raw[header_idx+1:].copy()
                df.columns = [str(c).strip() for c in df_raw.iloc[header_idx]]
                
                # Sütunları Belirle (Tutar bulmaya çalışıyoruz)
                col_stok = next((c for c in df.columns if "Stok Adı" in c), None)
                col_miktar = next((c for c in df.columns if "Miktar" in c), None)
                col_tutar = next((c for c in df.columns if any(x in c for x in ["Net Tutar", "Tutar", "Toplam"])), None)
                
                if col_stok and col_miktar:
                    tum_malzemeler, etiket_listesi, db_kayitlari = {}, [], []
                    top_desi, top_parca, top_kg, top_tutar = 0, 0, 0, 0
                    tablo_verisi = []
                    
                    global_counter = 1
                    for _, row in df.iterrows():
                        try: adet = float(row[col_miktar])
                        except: adet = 0
                        
                        # Tutar Okuma (Varsa)
                        birim_tutar = 0
                        if col_tutar:
                            try: birim_tutar = float(row[col_tutar])
                            except: pass
                            
                        stok_adi = str(row[col_stok])
                        
                        if adet > 0:
                            analiz = hesapla_ve_analiz_et(stok_adi, adet)
                            if analiz: # Radyatör/Havlupan ise
                                top_desi += analiz['Toplam_Desi']
                                top_kg += analiz['Toplam_Agirlik']
                                top_parca += int(adet)
                                top_tutar += birim_tutar # Tutarı ekle
                                
                                # Veritabanı Kaydı Hazırla
                                db_kayitlari.append([
                                    str(tarih_secimi), ad_soyad, 
                                    analiz['Etiket']['kisa_isim'], 
                                    analiz['Etiket']['boyut_str'], 
                                    int(adet), 
                                    birim_tutar, # Okunan Tutar
                                    "Excel"
                                ])
                                
                                tablo_verisi.append({
                                    "Ürün": analiz['Etiket']['kisa_isim'], "Adet": int(adet),
                                    "Ölçü": analiz['Etiket']['boyut_str'], "Desi": analiz['Etiket']['desi_val'],
                                    "KG": f"{analiz['Toplam_Agirlik']:.1f}", "Tutar": f"{birim_tutar:.2f} TL"
                                })
                                
                                # Reçete ve Etiketler
                                for m, b, a in analiz['Reçete']: tum_malzemeler[f"{a} ({b})"] = tum_malzemeler.get(f"{a} ({b})", 0) + (m * adet)
                                for _ in range(int(adet)):
                                    e = analiz['Etiket'].copy(); e['sira_no'] = global_counter
                                    etiket_listesi.append(e); global_counter += 1
                                    
                    # SONUÇLARI GÖSTER
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("📦 Koli", top_parca)
                    c2.metric("⚖️ Desi", f"{top_desi:.2f}")
                    c3.metric("🏗️ Ağırlık", f"{top_kg:.2f} KG")
                    c4.metric("💰 Toplam Tutar", f"{top_tutar:,.2f} TL")
                    st.divider()
                    
                    # KAYIT BUTONU (Sadece şifre girildiyse aktif olsun diyebiliriz ama şimdilik herkes kaydedebilsin mi? 
                    # Kullanıcı "Herkes erişemesin" dediği için buraya da şifre koyabiliriz. 
                    # Ama genelde personel hesap yapıp kaydeder, patron rapor bakar.
                    # Şimdilik kayıt açık, rapor kapalı.)
                    
                    if ad_soyad and st.button("💾 Hesabı Veritabanına İşle", type="primary"):
                        if check_password(): # Şifre sorar
                            basari, m = save_to_google_sheets(db_kayitlari)
                            if basari: st.success("✅ Kayıt Başarılı!"); st.balloons()
                            else: st.error(m)
                    
                    st.dataframe(pd.DataFrame(tablo_verisi), use_container_width=True)
                    
                    # PDF Çıktıları
                    c_pdf1, c_pdf2 = st.columns(2)
                    c_pdf1.download_button("📄 Kargo Fişi (PDF)", create_cargo_pdf(top_desi, top_parca, musteri_data, etiket_listesi), "Kargo.pdf", "application/pdf", use_container_width=True)
                    c_pdf2.download_button("🏭 Üretim Emri (PDF)", create_production_pdf(tum_malzemeler, etiket_listesi, musteri_data), "Uretim.pdf", "application/pdf", use_container_width=True)
                    
                else: st.error("Dosyada 'Stok Adı' veya 'Miktar' bulunamadı.")
            else: st.error("Başlık satırı bulunamadı.")
        except Exception as e: st.error(f"Hata: {e}")

# --- TAB 2: MANUEL ---
with tab_manuel:
    st.header("🧮 Manuel Hesap")
    if 'm_liste' not in st.session_state: st.session_state['m_liste'] = []
    
    c1, c2, c3, c4 = st.columns(4)
    modeller = ["Standart Radyatör", "Havlupan"] + [m.capitalize() for m in MODEL_DERINLIKLERI.keys() if m != 'livera']
    secilen = c1.selectbox("Model", modeller)
    is_h = 'havlupan' in secilen.lower() or any(z in secilen.lower() for z in ZORUNLU_HAVLUPANLAR)
    l1, l2, v1, v2 = ("Genişlik", "Yükseklik", 50, 70) if is_h else ("Yükseklik", "Genişlik", 60, 100)
    val1 = c2.number_input(l1, 10, value=v1); val2 = c3.number_input(l2, 10, value=v2)
    adet = c4.number_input("Adet", 1, value=1)
    
    if st.button("Listeye Ekle"):
        g, y = (val1, val2) if is_h else (val2, val1)
        desi, boy, kg = manuel_hesapla(secilen, g, y, adet)
        st.session_state['m_liste'].append({"Model": secilen, "Ölçü": f"{g}x{y}", "Adet": adet, "Desi": desi*adet, "KG": kg})
        
    if st.session_state['m_liste']:
        df_m = pd.DataFrame(st.session_state['m_liste'])
        st.dataframe(df_m, use_container_width=True)
        if ad_soyad and st.button("💾 Manuel Kaydet"):
            if check_password():
                kayitlar = [[str(tarih_secimi), ad_soyad, r['Model'], r['Ölçü'], r['Adet'], 0, "Manuel"] for r in st.session_state['m_liste']]
                save_to_google_sheets(kayitlar); st.success("Kaydedildi"); st.session_state['m_liste'] = []

# --- TAB 3: YÖNETİM PANELİ (ŞİFRELİ) ---
with tab_rapor:
    if check_password():
        st.success("🔓 Yönetici Girişi Başarılı")
        df = get_data_from_google_sheets()
        
        if not df.empty:
            # Temizleme
            df['Tutar'] = pd.to_numeric(df['Tutar'], errors='coerce').fillna(0)
            df['Adet'] = pd.to_numeric(df['Adet'], errors='coerce').fillna(0)
            
            # Filtreler
            c_fil1, c_fil2 = st.columns(2)
            filtre_mus = c_fil1.selectbox("Müşteri Seç", ["Tümü"] + list(df['Musteri'].unique()))
            if filtre_mus != "Tümü": df = df[df['Musteri'] == filtre_mus]
            
            # KPI Kartları
            top_ciro = df['Tutar'].sum()
            top_adet = df['Adet'].sum()
            top_islem = len(df)
            
            k1, k2, k3 = st.columns(3)
            k1.metric("💰 Toplam Ciro", f"{top_ciro:,.2f} TL")
            k2.metric("📦 Satılan Ürün", f"{top_adet} Adet")
            k3.metric("📝 İşlem Sayısı", top_islem)
            
            st.markdown("---")
            
            # GRAFİKLER
            g1, g2 = st.columns(2)
            
            with g1:
                st.subheader("Ürün Modeli Dağılımı")
                # Pasta Grafiği Verisi
                pie_data = df.groupby('Model')['Adet'].sum().reset_index()
                chart = alt.Chart(pie_data).mark_arc(innerRadius=50).encode(
                    theta=alt.Theta(field="Adet", type="quantitative"),
                    color=alt.Color(field="Model", type="nominal"),
                    tooltip=["Model", "Adet"]
                )
                st.altair_chart(chart, use_container_width=True)
                
            with g2:
                st.subheader("Satış Geçmişi")
                st.dataframe(df.tail(10)[['Tarih','Musteri','Model','Tutar']], use_container_width=True)
        else:
            st.info("Veritabanı boş.")
