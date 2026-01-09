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

# Google Sheets ve Grafik
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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

# Şifre Kontrol
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["admin_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
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

# Google Sheets Bağlantısı
@st.cache_resource
def init_connection():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except:
        return None

def save_to_google_sheets(veriler):
    client = init_connection()
    if client:
        try:
            sheet = client.open("Nixrad Veritabani").sheet1
            sheet.append_rows(veriler)
            return True, "Kayıt Başarılı!"
        except Exception as e:
            return False, f"Hata: {e}"
    else:
        return False, "Veritabanı bağlantı hatası."

def get_data_from_google_sheets():
    client = init_connection()
    if client:
        try:
            sheet = client.open("Nixrad Veritabani").sheet1
            data = sheet.get_all_records()
            return pd.DataFrame(data)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def delete_row_from_google_sheets(row_index):
    """Belirtilen satır numarasını siler (row_index 0'dan başlar, sheets 1'den başlar + header)"""
    client = init_connection()
    if client:
        try:
            sheet = client.open("Nixrad Veritabani").sheet1
            # Dataframe indexi 0 ise, Sheet'te Header(1) + 1 = 2. satırdır.
            # Gspread delete_rows indexi 1 tabanlıdır.
            sheet.delete_rows(row_index + 2) 
            return True, "Silindi"
        except Exception as e:
            return False, str(e)
    return False, "Bağlantı yok"

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
HESAPLANACAK_RADYATORLER = list(MODEL_AGIRLIKLARI.keys())
RENKLER = ["BEYAZ", "ANTRASIT", "SIYAH", "KROM", "ALTIN", "GRI", "KIRMIZI"]

# =============================================================================
# 2. YARDIMCI FONKSİYONLAR
# =============================================================================

def safe_float_convert(val):
    try:
        if isinstance(val, (int, float)): return float(val)
        val_str = str(val).strip()
        if '.' in val_str and ',' in val_str: val_str = val_str.replace('.', '').replace(',', '.')
        elif ',' in val_str: val_str = val_str.replace(',', '.')
        val_str = re.sub(r'[^\d.]', '', val_str)
        return float(val_str)
    except: return 0.0

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
    boyut = ""
    boyut_match = re.search(r'(\d+)\s*[/xX]\s*(\d+)', stok_adi)
    if boyut_match: boyut = f"{boyut_match.group(1)}/{boyut_match.group(2)}"
    renk = ""
    for r in RENKLER: 
        if r in stok_upper: renk = r; break
    return tr_clean_for_pdf(f"{model_adi} {boyut} {renk}".strip())

def get_standart_paket_icerigi(tip, model_adi):
    ambalaj = "GENEL AMBALAJLAMA (Karton+ balon + Strec)"
    if tip == 'HAVLUPAN':
        return [(1, "Adet", "1/2 PURJOR"), (1, "Takim", "3 LU HAVLUPAN MONTAJ SETI"), (3, "Adet", "DUBEL"), (3, "Adet", "MONTAJ VIDASI"), (1, "Set", ambalaj)]
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
    kg_per_dilim = (yukseklik_cm / 60) * MODEL_AGIRLIKLARI[model_key]
    return round(dilim_sayisi * kg_per_dilim, 2)

def hesapla_ve_analiz_et(stok_adi, adet):
    if not isinstance(stok_adi, str): return None
    stok_adi_islenen = tr_lower(stok_adi)
    base_derinlik = 4.5; bulunan_model_adi = "Standart"; bulunan_model_key = "standart"
    for model, derinlik in MODEL_DERINLIKLERI.items():
        if model in stok_adi_islenen:
            base_derinlik = derinlik; bulunan_model_key = model
            bulunan_model_adi = "Livara" if model == 'livera' else model.capitalize()
            break
    is_h = 'havlupan' in stok_adi_islenen or any(z in stok_adi_islenen for z in ZORUNLU_HAVLUPANLAR)
    tip = 'HAVLUPAN' if is_h else 'RADYATOR'
    paylar = AYARLAR[tip]
    boyutlar = re.search(r'(\d+)\s*[/xX]\s*(\d+)', stok_adi)
    
    if boyutlar:
        v1, v2 = int(boyutlar.group(1)) / 10, int(boyutlar.group(2)) / 10
        g, y = (v1, v2) if tip == 'HAVLUPAN' else (v2, v1)
        k_en, k_boy = g + paylar['PAY_GENISLIK'], y + paylar['PAY_YUKSEKLIK']
        k_derin = base_derinlik + paylar['PAY_DERINLIK']
        desi = round((k_en * k_boy * k_derin) / 3000, 2)
        kg = agirlik_hesapla(stok_adi, g, y, bulunan_model_key)
        
        return {
            'Adet': int(adet), 'Reçete': get_standart_paket_icerigi(tip, tr_upper(bulunan_model_adi)),
            'Etiket': {'kisa_isim': isim_kisalt(stok_adi), 'boyut_str': f"{k_en}x{k_boy}x{k_derin}cm", 'desi_val': desi},
            'Toplam_Desi': desi * adet, 'Toplam_Agirlik': kg * adet
        }
    return None

def manuel_hesapla(model_secimi, genislik, yukseklik, adet=1):
    model_lower = model_secimi.lower()
    is_h = 'havlupan' in model_lower or any(z in model_lower for z in ZORUNLU_HAVLUPANLAR)
    tip = 'HAVLUPAN' if is_h else 'RADYATOR'
    base_derinlik = 4.5; model_key = "standart"
    for m_key, m_val in MODEL_DERINLIKLERI.items():
        if m_key in model_lower: base_derinlik = m_val; model_key = m_key; break
    paylar = AYARLAR[tip]
    k_en, k_boy = genislik + paylar['PAY_GENISLIK'], yukseklik + paylar['PAY_YUKSEKLIK']
    k_derin = base_derinlik + paylar['PAY_DERINLIK']
    desi = (k_en * k_boy * k_derin) / 3000
    kg = agirlik_hesapla("", genislik, yukseklik, model_key)
    return round(desi, 2), f"{k_en}x{k_boy}x{k_derin}cm", round(kg * adet, 2)

# =============================================================================
# PDF FONKSİYONLARI
# =============================================================================
def create_cargo_pdf(proje_toplam_desi, toplam_parca, musteri_bilgileri, etiket_listesi):
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1*cm, leftMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm); elements = []
    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle('n', parent=styles['Normal'], fontSize=10, leading=12)
    style_header = ParagraphStyle('h', parent=styles['Normal'], fontSize=14, leading=16, fontName='Helvetica-Bold', textColor=colors.darkred)
    gonderen_info = [Paragraph("<b>GONDEREN FIRMA:</b>", style_normal), Paragraph("NIXRAD / KARPAN DIZAYN A.S.", style_header), Paragraph("Yeni Cami OSB Mah. 3.Cad. No:1 Kavak/SAMSUN", style_normal), Paragraph("Tel: 0262 658 11 58", style_normal)]
    odeme_clean = tr_clean_for_pdf(musteri_bilgileri.get('ODEME_TIPI', 'ALICI'))
    odeme_info = [Paragraph("<b>ODEME TIPI:</b>", style_normal), Spacer(1, 0.5*cm), Paragraph(f"<b>{odeme_clean} ODEMELI</b>", ParagraphStyle('big', fontSize=14, alignment=TA_CENTER, fontName='Helvetica-Bold'))]
    t_header = Table([[gonderen_info, odeme_info]], colWidths=[13*cm, 6*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 1, colors.black), ('GRID', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 8), ('BACKGROUND', (0,0), (-1,-1), colors.whitesmoke)]))
    elements.append(t_header); elements.append(Spacer(1, 0.5*cm))
    alici_ad = tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD']) if musteri_bilgileri['AD_SOYAD'] else "....."
    alici_tel = musteri_bilgileri['TELEFON'] if musteri_bilgileri['TELEFON'] else "....."
    clean_adres = tr_clean_for_pdf(musteri_bilgileri['ADRES'] if musteri_bilgileri['ADRES'] else "Adres Girilmedi")
    alici_content = [Paragraph("<b>ALICI MUSTERI:</b>", style_normal), Paragraph(f"<b>{alici_ad}</b>", ParagraphStyle('alici_ad_huge', fontSize=22, leading=26, fontName='Helvetica-Bold', spaceBefore=6, spaceAfter=12)), Paragraph(f"<b>Tel:</b> {alici_tel}", ParagraphStyle('tel_big', fontSize=12, leading=14)), Spacer(1, 0.5*cm), Paragraph(f"<b>ADRES:</b><br/>{clean_adres}", ParagraphStyle('adres_style_big', fontSize=15, leading=20))]
    t_alici = Table([[alici_content]], colWidths=[19*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 2, colors.black), ('PADDING', (0,0), (-1,-1), 15)]))
    elements.append(t_alici); elements.append(Spacer(1, 0.5*cm))
    elements.append(Paragraph("<b>PAKET ICERIK OZETI:</b>", ParagraphStyle('b', fontSize=10, fontName='Helvetica-Bold'))); elements.append(Spacer(1, 0.2*cm))
    pkt_data = [['Koli No', 'Urun Adi', 'Olcu', 'Desi']] + [[f"#{p['sira_no']}", tr_clean_for_pdf(p['kisa_isim']), p['boyut_str'], str(p['desi_val'])] for i, p in enumerate(etiket_listesi) if i < 15]
    t_pkt = Table(pkt_data, colWidths=[2*cm, 11*cm, 4*cm, 2*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('ALIGN', (0,0), (-1,-1), 'LEFT'), ('FONTSIZE', (0,0), (-1,-1), 9)]))
    elements.append(t_pkt); elements.append(Spacer(1, 0.5*cm))
    summary_data = [[f"TOPLAM PARCA: {toplam_parca}", f"TOPLAM DESI: {proje_toplam_desi:.2f}"]]
    t_sum = Table(summary_data, colWidths=[9.5*cm, 9.5*cm], style=TableStyle([('ALIGN', (0,0), (0,0), 'LEFT'), ('ALIGN', (1,0), (1,0), 'RIGHT'), ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 14), ('TEXTCOLOR', (1,0), (1,0), colors.blue), ('LINEBELOW', (0,0), (-1,-1), 2, colors.black)]))
    elements.append(t_sum); elements.append(Spacer(1, 1*cm))
    warning_title = Paragraph("<b>DIKKAT KIRILIR !</b>", ParagraphStyle('WT', fontSize=26, alignment=TA_CENTER, textColor=colors.white, fontName='Helvetica-Bold'))
    warning_text = """SAYIN MUSTERIMIZ,<br/>GELEN KARGONUZUN BULUNDUGU PAKETLERIN SAGLAM VE PAKETLERDE EZIKLIK OLMADIGINI KONTROL EDEREK ALINIZ. EKSIK VEYA HASARLI MALZEME VARSA LUTFEN KARGO GOREVLISINE AYNI GUN TUTANAK TUTTURUNUZ."""
    warning_para = Paragraph(warning_text, ParagraphStyle('warn', alignment=TA_CENTER, textColor=colors.white, fontSize=11, leading=14, fontName='Helvetica-Bold'))
    t_warn = Table([[warning_title], [warning_para]], colWidths=[19*cm], style=TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.red), ('BOX', (0,0), (-1,-1), 1, colors.black), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('PADDING', (0,0), (-1,-1), 10), ('BOTTOMPADDING', (0,0), (-1,0), 10)]))
    elements.append(t_warn)
    doc.build(elements); buffer.seek(0); return buffer

def create_production_pdf(tum_malzemeler, etiket_listesi, musteri_bilgileri):
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.5*cm, leftMargin=0.5*cm, topMargin=1*cm, bottomMargin=1*cm); elements = []
    styles = getSampleStyleSheet()
    cust_name = tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD']) if musteri_bilgileri['AD_SOYAD'] else "Isim Girilmedi"
    elements.append(Paragraph(f"URETIM & PAKETLEME EMRI - {cust_name}", ParagraphStyle('Title', fontSize=16, alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=15)))
    data = [['MALZEME ADI', 'ADET', 'KONTROL']] + [[Paragraph(tr_clean_for_pdf(m), ParagraphStyle('malz_style', fontSize=10, fontName='Helvetica')), f"{int(v)}" if v%1==0 else f"{v:.1f}", "___"] for m, v in tum_malzemeler.items()]
    t = Table(data, colWidths=[14*cm, 2*cm, 3*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('ALIGN', (1,0), (-1,-1), 'CENTER'), ('ALIGN', (2,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('PADDING', (0,0), (-1,-1), 6)]))
    elements.append(t); elements.append(Spacer(1, 1*cm))
    signature_data = [["PAKETLEYEN PERSONEL", "", ""], ["Adi Soyadi: ....................................", "", ""], ["Imza: ....................................", "", ""]]
    t_sig = Table(signature_data, colWidths=[8*cm, 2*cm, 8*cm], style=TableStyle([('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('ALIGN', (0,0), (-1,-1), 'LEFT'), ('BOTTOMPADDING', (0,0), (-1,-1), 10)]))
    elements.append(t_sig); elements.append(Spacer(1, 0.5*cm)); elements.append(Paragraph("-" * 120, ParagraphStyle('sep', alignment=TA_CENTER))); elements.append(Paragraph("ASAGIDAKI ETIKETLERI KESIP KOLILERE YAPISTIRINIZ (6x6 cm)", ParagraphStyle('Small', fontSize=8, alignment=TA_CENTER))); elements.append(Spacer(1, 0.5*cm))
    sticker_data, row = [], []
    style_num = ParagraphStyle('n', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=14, textColor=colors.red, fontName='Helvetica-Bold')
    for p in etiket_listesi:
        isim, boyut, desi, no = tr_clean_for_pdf(p['kisa_isim']), p['boyut_str'], str(p['desi_val']), str(p['sira_no'])
        cust = tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'][:25]) if musteri_bilgileri['AD_SOYAD'] else ""
        content = [[Paragraph(f"<b>#{no}</b>", style_num)], [Paragraph(f"<b>{isim}</b>", ParagraphStyle('C', alignment=TA_CENTER, fontSize=9))], [Paragraph(f"{boyut}", ParagraphStyle('C', alignment=TA_CENTER, fontSize=8))], [Spacer(1, 0.2*cm)], [Paragraph(f"<b>Desi: {desi}</b>", ParagraphStyle('L', alignment=TA_LEFT, fontSize=11))], [Paragraph(f"<i>{cust}</i>", ParagraphStyle('C', alignment=TA_CENTER, fontSize=7, textColor=colors.grey))]]
        box = Table(content, colWidths=[5.8*cm], rowHeights=[0.8*cm, 1.2*cm, 0.5*cm, 0.5*cm, 0.8*cm, 0.5*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0)]))
        row.append(box)
        if len(row)==3: sticker_data.append(row); row = []
    if row: 
        while len(row)<3: row.append("")
        sticker_data.append(row)
    if sticker_data: elements.append(Table(sticker_data, colWidths=[6.5*cm]*3, style=TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 15)])))
    doc.build(elements); buffer.seek(0); return buffer

# =============================================================================
# 3. WEB ARAYÜZÜ
# =============================================================================

st.markdown("""# 📦 NIXRAD Paketleme Sistemi \n ### by [NETMAKER](https://netmaker.com.tr/)""", unsafe_allow_html=True)

st.sidebar.header("Musteri Bilgileri")
ad_soyad = st.sidebar.text_input("Adi Soyadi / Firma Adi")
tarih_secimi = st.sidebar.date_input("İşlem Tarihi", datetime.date.today())
telefon = st.sidebar.text_input("Telefon Numarasi")
adres = st.sidebar.text_area("Adres (Enter ile alt satira gecebilirsiniz)")
odeme_tipi = st.sidebar.radio("Odeme Tipi", ["ALICI", "PESIN"], index=0)
musteri_data = {'AD_SOYAD': ad_soyad, 'TELEFON': telefon, 'ADRES': adres, 'ODEME_TIPI': odeme_tipi}

# SEKMELER (TABS)
tab_dosya, tab_manuel, tab_rapor = st.tabs(["📂 Dosya ile Hesapla", "🧮 Manuel Hesaplayıcı", "📊 Yönetim & Rapor (Şifreli)"])

# --- TAB 1: DOSYA YÜKLEME ---
with tab_dosya:
    uploaded_file = st.file_uploader("Dia Excel/CSV Dosyasini Yukleyin", type=['xls', 'xlsx', 'csv'])

    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                try: df_raw = pd.read_csv(uploaded_file, encoding='utf-8')
                except: df_raw = pd.read_csv(uploaded_file, encoding='cp1254')
            else:
                df_raw = pd.read_excel(uploaded_file)
                
            header_index = -1
            for i, row in df_raw.iterrows():
                if "Stok Adı" in " ".join([str(v) for v in row.values]): header_index = i; break
            
            if header_index != -1:
                new_header = df_raw.iloc[header_index]
                df = df_raw[header_index + 1:].copy()
                df.columns = [str(col).strip() for col in new_header]
                try: df = df[['Stok Adı', 'Miktar']]
                except: df = df.iloc[:, [0, 2]]; df.columns = ['Stok Adı', 'Miktar']
                
                # TUTAR VE ŞEHİR SÜTUNLARINI BUL
                col_tutar = None
                col_sehir = None
                for c in df_raw.iloc[header_index].values:
                    c_str = str(c)
                    if any(x in c_str for x in ["Net Tutar", "Tutar", "Toplam"]): col_tutar = c_str
                    if any(x in c_str.lower() for x in ["il/ilçe", "şehir", "sehir", "il"]): col_sehir = c_str
                
                # Dataframe'e ekle
                if col_tutar:
                     try: df[col_tutar] = df_raw[header_index + 1:][col_tutar].values
                     except: col_tutar = None
                if col_sehir:
                     try: df[col_sehir] = df_raw[header_index + 1:][col_sehir].values
                     except: col_sehir = None

                df = df.dropna(subset=['Stok Adı'])
                
                tum_malzemeler, etiket_listesi = {}, []
                proje_toplam_desi, toplam_parca, global_counter = 0, 0, 1
                proje_toplam_kg, proje_toplam_tutar = 0, 0
                
                tablo_verisi = []
                db_kayitlari = []
                
                for index, row in df.iterrows():
                    try: adet = float(row['Miktar'])
                    except: adet = 0
                    
                    # Tutar Okuma
                    birim_tutar = 0
                    if col_tutar:
                        try: birim_tutar = safe_float_convert(row[col_tutar])
                        except: birim_tutar = 0
                    
                    # Şehir Okuma
                    sehir = ""
                    if col_sehir:
                        sehir = str(row[col_sehir]) if pd.notna(row[col_sehir]) else ""
                    
                    stok_adi = str(row['Stok Adı']); stok_lower = tr_lower(stok_adi)
                    
                    if adet > 0:
                        is_vana_accessory = ('vana' in stok_lower) and ('nirvana' not in stok_lower)
                        is_other_accessory = any(x in stok_lower for x in ['volan', 'tapa', 'aksesuar', 'set', 'termo', 'köşe'])
                        
                        if is_vana_accessory or is_other_accessory:
                             key = f"{stok_adi} (Adet)"
                             tum_malzemeler[key] = tum_malzemeler.get(key, 0) + adet
                        
                        elif 'radyatör' in stok_lower or 'havlupan' in stok_lower or 'radyator' in stok_lower:
                            analiz = hesapla_ve_analiz_et(stok_adi, adet)
                            if analiz and analiz['Etiket']:
                                for miktar, birim, ad in analiz['Reçete']:
                                    key = f"{ad} ({birim})"
                                    tum_malzemeler[key] = tum_malzemeler.get(key, 0) + (miktar * adet)
                                
                                proje_toplam_desi += analiz['Toplam_Desi']
                                proje_toplam_kg += analiz['Toplam_Agirlik'] 
                                toplam_parca += int(adet)
                                proje_toplam_tutar += birim_tutar
                                
                                urun_adi = analiz['Etiket']['kisa_isim']
                                urun_olcu = analiz['Etiket']['boyut_str']
                                
                                tablo_verisi.append({
                                    "Ürün": urun_adi,
                                    "Adet": int(adet),
                                    "Ölçü": urun_olcu,
                                    "Desi": analiz['Etiket']['desi_val'],
                                    "Ağırlık (KG)": f"{analiz['Toplam_Agirlik']:.1f}",
                                    "Tutar": f"{birim_tutar:,.2f} TL"
                                })
                                
                                # Veritabanı Kaydı (Şehir Eklendi)
                                db_kayitlari.append([
                                    str(tarih_secimi), ad_soyad, urun_adi, urun_olcu, int(adet), birim_tutar, sehir, "Excel"
                                ])
                                
                                for _ in range(int(adet)):
                                    etiket_kopyasi = analiz['Etiket'].copy()
                                    etiket_kopyasi['sira_no'] = global_counter
                                    etiket_listesi.append(etiket_kopyasi)
                                    global_counter += 1

                st.divider()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("📦 Toplam Koli", toplam_parca)
                c2.metric("⚖️ Toplam Desi", f"{proje_toplam_desi:.2f}")
                c3.metric("🏗️ Toplam Ağırlık", f"{proje_toplam_kg:.2f} KG") 
                c4.metric("💰 Dosya Tutarı", f"{proje_toplam_tutar:,.2f} TL")
                st.divider()
                
                # KAYIT BUTONU
                if ad_soyad and st.button("💾 Hesabı Veritabanına İşle", type="primary"):
                    if db_kayitlari:
                        basari, mesaj = save_to_google_sheets(db_kayitlari)
                        if basari: st.success("✅ Veritabanına Kaydedildi!"); st.balloons()
                        else: st.error(mesaj)
                    else:
                        st.warning("Kaydedilecek ürün yok.")

                col_table1, col_table2 = st.columns(2)
                with col_table1:
                    st.subheader("1. Koli Listesi (Detaylı)")
                    if tablo_verisi:
                        st.dataframe(pd.DataFrame(tablo_verisi), hide_index=True, use_container_width=True)
                with col_table2:
                    st.subheader("2. Malzeme Cek Listesi")
                    if tum_malzemeler:
                        malz_items = [{"Malzeme": k, "Adet": int(v) if v%1==0 else v} for k,v in tum_malzemeler.items()]
                        df_malz = pd.DataFrame(malz_items)
                        st.dataframe(df_malz, hide_index=True, use_container_width=True)

                st.divider()
                st.subheader("🖨️ Cikti Al")
                col_pdf1, col_pdf2 = st.columns(2)
                
                pdf_cargo = create_cargo_pdf(proje_toplam_desi, toplam_parca, musteri_data, etiket_listesi)
                col_pdf1.download_button(label="📄 1. KARGO FISI (A4)", data=pdf_cargo, file_name="Kargo_Fisi.pdf", mime="application/pdf", use_container_width=True)

                pdf_production = create_production_pdf(tum_malzemeler, etiket_listesi, musteri_data)
                col_pdf2.download_button(label="🏭 2. URETIM & ETIKETLER", data=pdf_production, file_name="Uretim_ve_Etiketler.pdf", mime="application/pdf", use_container_width=True)
                
            else:
                st.error("Dosyada 'Stok Adı' basligi bulunamadi.")
        except Exception as e:
            st.error(f"Hata: {e}")

# --- TAB 2: MANUEL HESAPLAYICI ---
with tab_manuel:
    st.header("🧮 Hızlı Desi Hesaplama Aracı")
    
    if 'manuel_liste' not in st.session_state:
        st.session_state['manuel_liste'] = []

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        display_models = ["Standart Radyatör", "Havlupan"] + [m.capitalize() for m in MODEL_DERINLIKLERI.keys() if m != 'livera']
        secilen_model = st.selectbox("Model Seçin", display_models)
        model_lower = secilen_model.lower()
        is_havlupan = 'havlupan' in model_lower or any(z in model_lower for z in ZORUNLU_HAVLUPANLAR)
        if is_havlupan: l1, l2, v1_d, v2_d = "Genişlik (cm)", "Yükseklik (cm)", 50, 70
        else: l1, l2, v1_d, v2_d = "Yükseklik (cm)", "Genişlik (cm)", 60, 100
        
    with c2: val_1 = st.number_input(l1, min_value=10, value=v1_d)
    with c3: val_2 = st.number_input(l2, min_value=10, value=v2_d)
    with c4: m_adet = st.number_input("Adet", min_value=1, value=1)
        
    if st.button("➕ Listeye Ekle", type="primary"):
        if is_havlupan: g_input, y_input = val_1, val_2
        else: y_input, g_input = val_1, val_2
            
        birim_desi, boyut_str, birim_kg = manuel_hesapla(secilen_model, g_input, y_input, m_adet)
        
        st.session_state['manuel_liste'].append({
            "Model": secilen_model, "Ölçü": f"{g_input} x {y_input}", "Kutu": boyut_str,
            "Adet": m_adet, "Desi": round(birim_desi * m_adet, 2), "KG": f"{birim_kg:.2f}"
        })
        st.success("Eklendi!")

    if st.session_state['manuel_liste']:
        st.divider()
        df_manuel = pd.DataFrame(st.session_state['manuel_liste'])
        st.dataframe(df_manuel, use_container_width=True)
        
        t_adet = df_manuel['Adet'].sum()
        t_desi = df_manuel['Desi'].sum()
        try: t_kg = sum([float(str(x['KG'])) for x in st.session_state['manuel_liste']])
        except: t_kg = 0
        
        c_tot1, c_tot2, c_tot3 = st.columns(3)
        c_tot1.metric("Toplam Parça", t_adet)
        c_tot2.metric("Genel Toplam Desi", f"{t_desi:.2f}")
        c_tot3.metric("Genel Toplam Ağırlık", f"{t_kg:.2f} KG")
        
        if ad_soyad and st.button("💾 Manuel Listeyi Veritabanına Kaydet"):
            man_kayitlar = []
            for item in st.session_state['manuel_liste']:
                # Manuel kayıtta şehir boş gider
                man_kayitlar.append([str(tarih_secimi), ad_soyad, item['Model'], item['Ölçü'], item['Adet'], 0, "", "Manuel"])
            basari, m = save_to_google_sheets(man_kayitlar)
            if basari: st.success("Manuel liste kaydedildi!"); st.session_state['manuel_liste'] = []
            else: st.error(m)
            
        if st.button("🗑️ Listeyi Temizle"):
            st.session_state['manuel_liste'] = []
            st.rerun()

# --- TAB 3: YÖNETİM & RAPORLAR (GELİŞMİŞ) ---
with tab_rapor:
    if check_password():
        st.success("🔓 Yönetici Paneli")
        df_rapor = get_data_from_google_sheets()
        
        if not df_rapor.empty:
            # Veri Tiplerini Düzelt
            df_rapor['Tarih'] = pd.to_datetime(df_rapor['Tarih'], dayfirst=True, errors='coerce')
            df_rapor['Tutar'] = pd.to_numeric(df_rapor['Tutar'], errors='coerce').fillna(0)
            df_rapor['Adet'] = pd.to_numeric(df_rapor['Adet'], errors='coerce').fillna(0)
            # Tarih formatına çevrilemeyenler (Manuel yazılanlar vs) için bugünün tarihi atayalım veya filtreleyelim
            df_rapor = df_rapor.dropna(subset=['Tarih'])
            df_rapor['Ay_Yil'] = df_rapor['Tarih'].dt.strftime('%Y-%m') # Sıralama için YYYY-MM
            df_rapor['Gorunum_Ay'] = df_rapor['Tarih'].dt.strftime('%B %Y') # Türkçe Ay İsimleri (Server diline göre değişebilir)

            # --- FİLTRELER ---
            st.subheader("🔍 Rapor Filtreleri")
            c_f1, c_f2 = st.columns(2)
            
            # Ay Seçimi
            aylar_listesi = sorted(df_rapor['Ay_Yil'].unique(), reverse=True)
            secilen_ay = c_f1.selectbox("Dönem Seçiniz (Ay/Yıl)", ["Tümü"] + aylar_listesi)
            
            # Müşteri Seçimi
            musteriler = sorted(df_rapor['Musteri'].astype(str).unique())
            secilen_musteri = c_f2.selectbox("Müşteri Seçiniz", ["Tümü"] + musteriler)
            
            # Filtreleme İşlemi
            df_filtered = df_rapor.copy()
            if secilen_ay != "Tümü":
                df_filtered = df_filtered[df_filtered['Ay_Yil'] == secilen_ay]
            if secilen_musteri != "Tümü":
                df_filtered = df_filtered[df_filtered['Musteri'] == secilen_musteri]
                
            st.divider()
            
            # --- KPI KARTLARI ---
            top_ciro = df_filtered['Tutar'].sum()
            top_adet = df_filtered['Adet'].sum()
            uniq_sehir = df_filtered['Sehir'].nunique() if 'Sehir' in df_filtered.columns else 0
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("💰 Seçili Dönem Ciro", f"{top_ciro:,.2f} TL")
            k2.metric("📦 Satılan Ürün", f"{top_adet} Adet")
            k3.metric("🏙️ Farklı Şehir", uniq_sehir)
            k4.metric("📝 Kayıt Sayısı", len(df_filtered))
            
            st.markdown("---")
            
            # --- GRAFİKLER (TABS) ---
            tab_g1, tab_g2, tab_g3 = st.tabs(["📈 Ürün Analizi", "🗺️ Şehir Analizi", "📅 Zaman Analizi"])
            
            with tab_g1:
                st.subheader("En Çok Satılan Modeller")
                model_data = df_filtered.groupby('Model')['Adet'].sum().reset_index().sort_values('Adet', ascending=False)
                st.bar_chart(model_data, x='Model', y='Adet')
                
            with tab_g2:
                if 'Sehir' in df_filtered.columns:
                    st.subheader("Şehirlere Göre Dağılım")
                    sehir_data = df_filtered.groupby('Sehir')['Adet'].sum().reset_index().sort_values('Adet', ascending=False)
                    st.bar_chart(sehir_data, x='Sehir', y='Adet')
                else:
                    st.warning("Veritabanında Şehir sütunu bulunamadı.")
            
            with tab_g3:
                st.subheader("Günlük Satış Trendi")
                time_data = df_filtered.groupby('Tarih')['Tutar'].sum().reset_index()
                st.line_chart(time_data, x='Tarih', y='Tutar')

            st.divider()
            
            # --- DETAYLI TABLO ---
            st.subheader("📋 Detaylı Satış Listesi")
            st.dataframe(df_filtered, use_container_width=True)
            
            # --- VERİ SİLME PANELİ ---
            st.error("🗑️ Kayıt Silme Alanı")
            with st.expander("Veri Silmek İçin Tıklayın (Dikkat!)"):
                st.write("Aşağıdaki listeden silmek istediğiniz kaydın solundaki kutucuğu değil, **Index numarasını** (en soldaki sayı) not edip aşağıya yazın.")
                # Tüm veriyi göster (Index'i ile beraber)
                st.dataframe(df_rapor.sort_values('Tarih', ascending=False).reset_index(), use_container_width=True)
                
                row_to_delete = st.number_input("Silinecek Satırın Index Numarası (Orijinal Tablodaki)", min_value=0, step=1)
                
                if st.button("❌ Seçili Satırı Kalıcı Olarak Sil"):
                    basari, msj = delete_row_from_google_sheets(row_to_delete)
                    if basari:
                        st.success("Satır silindi! Sayfa yenileniyor...")
                        st.rerun()
                    else:
                        st.error(f"Silinemedi: {msj}")
            
        else:
            st.info("Veritabanı şu an boş.")
