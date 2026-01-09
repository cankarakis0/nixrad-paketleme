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

# Google Sheets Kütüphaneleri
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Matplotlib Backend Fix
plt_backend = 'Agg'
try:
    import matplotlib.pyplot as plt
    plt.switch_backend(plt_backend)
except:
    pass

# =============================================================================
# 1. AYARLAR & VERİTABANI BAĞLANTISI
# =============================================================================
st.set_page_config(page_title="Nixrad by NETMAKER", layout="wide")

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
    'nirvana': 1.10,
    'prag': 0.71,
    'livara': 0.81,
    'livera': 0.81,
    'akasya': 0.75,
    'aspar': 1.05
}

RENKLER = ["BEYAZ", "ANTRASIT", "SIYAH", "KROM", "ALTIN", "GRI", "KIRMIZI"]

# --- GOOGLE SHEETS BAĞLANTISI ---
@st.cache_resource
def init_connection():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # Streamlit Secrets'tan bilgileri alıyoruz
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        return None

def save_to_google_sheets(veriler):
    client = init_connection()
    if client:
        try:
            sheet = client.open("Nixrad Veritabani").sheet1
            sheet.append_rows(veriler)
            return True, "Kayit basarili!"
        except Exception as e:
            return False, f"Hata: {e}"
    else:
        return False, "Baglanti hatasi. Secrets ayarlarini kontrol et."

def get_data_from_google_sheets():
    client = init_connection()
    if client:
        try:
            sheet = client.open("Nixrad Veritabani").sheet1
            data = sheet.get_all_records()
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Veri çekme hatası: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

# =============================================================================
# 2. YARDIMCI FONKSİYONLAR
# =============================================================================

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
    base_derinlik = 4.5
    bulunan_model_adi = "Standart"
    bulunan_model_key = "standart"
    for model, derinlik in MODEL_DERINLIKLERI.items():
        if model in stok_adi_islenen:
            base_derinlik = derinlik; bulunan_model_key = model
            bulunan_model_adi = "Livara" if model == 'livera' else model.capitalize()
            break
            
    is_havlupan_name = 'havlupan' in stok_adi_islenen
    is_zorunlu_model = any(z in stok_adi_islenen for z in ZORUNLU_HAVLUPANLAR)
    tip = 'HAVLUPAN' if is_havlupan_name or is_zorunlu_model else 'RADYATOR'
    
    reçete = get_standart_paket_icerigi(tip, tr_upper(bulunan_model_adi))
    paylar = AYARLAR[tip]
    boyutlar = re.search(r'(\d+)\s*[/xX]\s*(\d+)', stok_adi)
    etiket_verisi, desi_sonuc, agirlik_sonuc = None, 0, 0
    
    if boyutlar:
        val1, val2 = int(boyutlar.group(1)) / 10, int(boyutlar.group(2)) / 10
        if tip == 'HAVLUPAN': genislik, yukseklik = val1, val2
        else: yukseklik, genislik = val1, val2
            
        kutulu_en = genislik + paylar['PAY_GENISLIK']
        kutulu_boy = yukseklik + paylar['PAY_YUKSEKLIK']
        kutulu_derinlik = base_derinlik + paylar['PAY_DERINLIK']
        desi_sonuc = round((kutulu_en * kutulu_boy * kutulu_derinlik) / 3000, 2)
        agirlik_sonuc = agirlik_hesapla(stok_adi, genislik, yukseklik, bulunan_model_key)
        
        etiket_verisi = {
            'kisa_isim': isim_kisalt(stok_adi),
            'boyut_str': f"{kutulu_en}x{kutulu_boy}x{kutulu_derinlik}cm",
            'desi_val': desi_sonuc
        }
    return {
        'Adet': int(adet), 'Reçete': reçete, 'Etiket': etiket_verisi,
        'Toplam_Desi': desi_sonuc * adet, 'Toplam_Agirlik': agirlik_sonuc * adet
    }

def manuel_hesapla(model_secimi, genislik, yukseklik, adet=1):
    model_lower = model_secimi.lower()
    is_havlupan = 'havlupan' in model_lower or any(z in model_lower for z in ZORUNLU_HAVLUPANLAR)
    tip = 'HAVLUPAN' if is_havlupan else 'RADYATOR'
    base_derinlik = 4.5; model_key = "standart"
    for m_key, m_val in MODEL_DERINLIKLERI.items():
        if m_key in model_lower: base_derinlik = m_val; model_key = m_key; break
    paylar = AYARLAR[tip]
    kutulu_en = genislik + paylar['PAY_GENISLIK']
    kutulu_boy = yukseklik + paylar['PAY_YUKSEKLIK']
    kutulu_derinlik = base_derinlik + paylar['PAY_DERINLIK']
    desi = (kutulu_en * kutulu_boy * kutulu_derinlik) / 3000
    birim_kg = agirlik_hesapla("", genislik, yukseklik, model_key)
    return round(desi, 2), f"{kutulu_en}x{kutulu_boy}x{kutulu_derinlik}cm", round(birim_kg * adet, 2)

# =============================================================================
# PDF FONKSİYONLARI (ORİJİNAL KODLAR GERİ GELDİ)
# =============================================================================
def create_cargo_pdf(proje_toplam_desi, toplam_parca, musteri_bilgileri, etiket_listesi):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1*cm, leftMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm)
    elements = []
    
    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle('n', parent=styles['Normal'], fontSize=10, leading=12)
    style_header = ParagraphStyle('h', parent=styles['Normal'], fontSize=14, leading=16, fontName='Helvetica-Bold', textColor=colors.darkred)
    
    gonderen_info = [
        Paragraph("<b>GONDEREN FIRMA:</b>", style_normal),
        Paragraph("NIXRAD / KARPAN DIZAYN A.S.", style_header),
        Paragraph("Yeni Cami OSB Mah. 3.Cad. No:1 Kavak/SAMSUN", style_normal),
        Paragraph("Tel: 0262 658 11 58", style_normal)
    ]
    
    odeme_clean = tr_clean_for_pdf(musteri_bilgileri.get('ODEME_TIPI', 'ALICI'))
    odeme_info = [
        Paragraph("<b>ODEME TIPI:</b>", style_normal),
        Spacer(1, 0.5*cm),
        Paragraph(f"<b>{odeme_clean} ODEMELI</b>", ParagraphStyle('big', fontSize=14, alignment=TA_CENTER, fontName='Helvetica-Bold')),
    ]
    
    t_header = Table([[gonderen_info, odeme_info]], colWidths=[13*cm, 6*cm])
    t_header.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BACKGROUND', (0,0), (-1,-1), colors.whitesmoke)
    ]))
    elements.append(t_header)
    elements.append(Spacer(1, 0.5*cm))
    
    alici_ad = tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD']) if musteri_bilgileri['AD_SOYAD'] else "....."
    alici_tel = musteri_bilgileri['TELEFON'] if musteri_bilgileri['TELEFON'] else "....."
    raw_adres = musteri_bilgileri['ADRES'] if musteri_bilgileri['ADRES'] else "Adres Girilmedi"
    clean_adres = tr_clean_for_pdf(raw_adres)
    
    alici_content = [
        Paragraph("<b>ALICI MUSTERI:</b>", style_normal),
        Paragraph(f"<b>{alici_ad}</b>", ParagraphStyle('alici_ad_huge', fontSize=22, leading=26, fontName='Helvetica-Bold', spaceBefore=6, spaceAfter=12)),
        Paragraph(f"<b>Tel:</b> {alici_tel}", ParagraphStyle('tel_big', fontSize=12, leading=14)),
        Spacer(1, 0.5*cm),
        Paragraph(f"<b>ADRES:</b><br/>{clean_adres}", ParagraphStyle('adres_style_big', fontSize=15, leading=20))
    ]
    
    t_alici = Table([[alici_content]], colWidths=[19*cm])
    t_alici.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 2, colors.black),
        ('PADDING', (0,0), (-1,-1), 15),
    ]))
    elements.append(t_alici)
    elements.append(Spacer(1, 0.5*cm))
    
    elements.append(Paragraph("<b>PAKET ICERIK OZETI:</b>", ParagraphStyle('b', fontSize=10, fontName='Helvetica-Bold')))
    elements.append(Spacer(1, 0.2*cm))
    
    pkt_data = [['Koli No', 'Urun Adi', 'Olcu', 'Desi']]
    for i, pkt in enumerate(etiket_listesi):
        if i < 15: 
            pkt_data.append([
                f"#{pkt['sira_no']}", 
                tr_clean_for_pdf(pkt['kisa_isim']), 
                pkt['boyut_str'], 
                str(pkt['desi_val'])
            ])
            
    t_pkt = Table(pkt_data, colWidths=[2*cm, 11*cm, 4*cm, 2*cm])
    t_pkt.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
    ]))
    elements.append(t_pkt)
    
    elements.append(Spacer(1, 0.5*cm))
    summary_data = [
        [f"TOPLAM PARCA: {toplam_parca}", f"TOPLAM DESI: {proje_toplam_desi:.2f}"]
    ]
    t_sum = Table(summary_data, colWidths=[9.5*cm, 9.5*cm])
    t_sum.setStyle(TableStyle([
        ('ALIGN', (0,0), (0,0), 'LEFT'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 14),
        ('TEXTCOLOR', (1,0), (1,0), colors.blue),
        ('LINEBELOW', (0,0), (-1,-1), 2, colors.black)
    ]))
    elements.append(t_sum)
    elements.append(Spacer(1, 1*cm))
    
    warning_title = Paragraph("<b>DIKKAT KIRILIR !</b>", ParagraphStyle('WT', fontSize=26, alignment=TA_CENTER, textColor=colors.white, fontName='Helvetica-Bold'))
    warning_text = """
    SAYIN MUSTERIMIZ,<br/>
    GELEN KARGONUZUN BULUNDUGU PAKETLERIN SAGLAM VE PAKETLERDE EZIKLIK OLMADIGINI
    KONTROL EDEREK ALINIZ. EKSIK VEYA HASARLI MALZEME VARSA LUTFEN KARGO GOREVLISINE
    AYNI GUN TUTANAK TUTTURUNUZ.
    """
    warning_para = Paragraph(warning_text, ParagraphStyle('warn', alignment=TA_CENTER, textColor=colors.white, fontSize=11, leading=14, fontName='Helvetica-Bold'))
    
    t_warn = Table([[warning_title], [warning_para]], colWidths=[19*cm])
    t_warn.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.red),
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('PADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 10),
    ]))
    elements.append(t_warn)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

def create_production_pdf(tum_malzemeler, etiket_listesi, musteri_bilgileri):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.5*cm, leftMargin=0.5*cm, topMargin=1*cm, bottomMargin=1*cm)
    elements = []
    styles = getSampleStyleSheet()
    
    cust_name = tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD']) if musteri_bilgileri['AD_SOYAD'] else "Isim Girilmedi"
    elements.append(Paragraph(f"URETIM & PAKETLEME EMRI - {cust_name}", ParagraphStyle('Title', fontSize=16, alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=15)))
    
    data = [['MALZEME ADI', 'ADET', 'KONTROL']]
    style_malz = ParagraphStyle('malz_style', fontSize=10, fontName='Helvetica')
    for malz, mik in tum_malzemeler.items():
        adet = f"{int(mik)}" if mik % 1 == 0 else f"{mik:.1f}"
        malz_clean = tr_clean_for_pdf(malz)
        data.append([Paragraph(malz_clean, style_malz), adet, "___"])
        
    t = Table(data, colWidths=[14*cm, 2*cm, 3*cm])
    t.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('ALIGN', (2,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 1*cm))
    
    signature_data = [
        ["PAKETLEYEN PERSONEL", "", ""],
        ["Adi Soyadi: ....................................", "", ""],
        ["Imza: ....................................", "", ""]
    ]
    t_sig = Table(signature_data, colWidths=[8*cm, 2*cm, 8*cm])
    t_sig.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    elements.append(t_sig)
    
    elements.append(Spacer(1, 0.5*cm))
    elements.append(Paragraph("-" * 120, ParagraphStyle('sep', alignment=TA_CENTER)))
    elements.append(Paragraph("ASAGIDAKI ETIKETLERI KESIP KOLILERE YAPISTIRINIZ (6x6 cm)", ParagraphStyle('Small', fontSize=8, alignment=TA_CENTER)))
    elements.append(Spacer(1, 0.5*cm))
    
    sticker_data = []
    row = []
    style_center = ParagraphStyle('c', parent=styles['Normal'], alignment=TA_CENTER, fontSize=9)
    style_num = ParagraphStyle('n', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=14, textColor=colors.red, fontName='Helvetica-Bold')
    
    for etiket in etiket_listesi:
        isim = tr_clean_for_pdf(etiket['kisa_isim'])
        boyut = etiket['boyut_str']
        desi = str(etiket['desi_val'])
        no = str(etiket['sira_no'])
        cust_clean = tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'][:25]) if musteri_bilgileri['AD_SOYAD'] else ""
        
        inner_content = [
            [Paragraph(f"<b>#{no}</b>", style_num)],
            [Paragraph(f"<b>{isim}</b>", ParagraphStyle('C', alignment=TA_CENTER, fontSize=9))],
            [Paragraph(f"{boyut}", ParagraphStyle('C', alignment=TA_CENTER, fontSize=8))],
            [Spacer(1, 0.2*cm)],
            [Paragraph(f"<b>Desi: {desi}</b>", ParagraphStyle('L', alignment=TA_LEFT, fontSize=11))],
            [Paragraph(f"<i>{cust_clean}</i>", ParagraphStyle('C', alignment=TA_CENTER, fontSize=7, textColor=colors.grey))]
        ]
        
        sticker_box = Table(inner_content, colWidths=[5.8*cm], rowHeights=[0.8*cm, 1.2*cm, 0.5*cm, 0.5*cm, 0.8*cm, 0.5*cm])
        sticker_box.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        
        row.append(sticker_box)
        if len(row) == 3:
            sticker_data.append(row)
            row = []
            
    if row:
        while len(row) < 3: row.append("")
        sticker_data.append(row)
        
    if sticker_data:
        t_stickers = Table(sticker_data, colWidths=[6.5*cm, 6.5*cm, 6.5*cm])
        t_stickers.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 15),
        ]))
        elements.append(t_stickers)
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# =============================================================================
# 3. WEB ARAYÜZÜ
# =============================================================================

st.markdown("""# 📦 NIXRAD Paketleme Sistemi \n ### by [NETMAKER](https://netmaker.com.tr/)""", unsafe_allow_html=True)

st.sidebar.header("Musteri Bilgileri")
ad_soyad = st.sidebar.text_input("Adi Soyadi / Firma Adi")
tarih_secimi = st.sidebar.date_input("İşlem Tarihi", datetime.date.today())
telefon = st.sidebar.text_input("Telefon Numarasi")
adres = st.sidebar.text_area("Adres")
odeme_tipi = st.sidebar.radio("Odeme Tipi", ["ALICI", "PESIN"], index=0)
musteri_data = {'AD_SOYAD': ad_soyad, 'TELEFON': telefon, 'ADRES': adres, 'ODEME_TIPI': odeme_tipi}

# SEKMELER
tab_dosya, tab_manuel, tab_rapor = st.tabs(["📂 Dosya ile Hesapla", "🧮 Manuel Hesaplayıcı", "📊 Satış Raporları"])

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
                df = df.dropna(subset=['Stok Adı'])
                
                tum_malzemeler, etiket_listesi = {}, []
                proje_toplam_desi, toplam_parca, global_counter, proje_toplam_kg = 0, 0, 1, 0
                tablo_verisi = []
                # Veritabanı için kayıt listesi
                db_kayitlari = []
                
                for index, row in df.iterrows():
                    try: adet = float(row['Miktar'])
                    except: adet = 0
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
                                
                                urun_adi = analiz['Etiket']['kisa_isim']
                                urun_olcu = analiz['Etiket']['boyut_str']
                                
                                tablo_verisi.append({
                                    "Ürün": urun_adi, "Adet": int(adet), "Ölçü": urun_olcu,
                                    "Desi": analiz['Etiket']['desi_val'], "Ağırlık (KG)": f"{analiz['Toplam_Agirlik']:.1f}"
                                })
                                
                                # Veritabanına gidecek satır
                                # Tarih, Musteri, Model, Olcu, Adet, Tutar, Aciklama
                                db_kayitlari.append([
                                    str(tarih_secimi), 
                                    ad_soyad, 
                                    urun_adi, 
                                    urun_olcu, 
                                    int(adet), 
                                    0, # Tutar şimdilik 0 (Dosyadan okuyamıyoruz)
                                    "Dosya Yükleme"
                                ])

                                for _ in range(int(adet)):
                                    etiket_kopyasi = analiz['Etiket'].copy()
                                    etiket_kopyasi['sira_no'] = global_counter
                                    etiket_listesi.append(etiket_kopyasi)
                                    global_counter += 1

                st.divider()
                c1, c2, c3 = st.columns(3)
                c1.metric("📦 Toplam Koli", toplam_parca)
                c2.metric("⚖️ Toplam Desi", f"{proje_toplam_desi:.2f}")
                c3.metric("🏗️ Toplam Ağırlık", f"{proje_toplam_kg:.2f} KG") 
                st.divider()

                # --- VERİTABANI KAYIT BUTONU ---
                if ad_soyad:
                    if st.button("💾 Sonuçları Veritabanına Kaydet", type="primary"):
                        if db_kayitlari:
                            basari, mesaj = save_to_google_sheets(db_kayitlari)
                            if basari: st.success(f"{len(db_kayitlari)} kalem ürün başarıyla kaydedildi! 🎉")
                            else: st.error(mesaj)
                        else:
                            st.warning("Kaydedilecek ürün bulunamadı.")
                else:
                    st.warning("⚠️ Kayıt yapmak için lütfen soldaki menüden Müşteri Adını giriniz.")

                col_table1, col_table2 = st.columns(2)
                with col_table1:
                    st.subheader("1. Koli Listesi")
                    if tablo_verisi: st.dataframe(pd.DataFrame(tablo_verisi), hide_index=True, use_container_width=True)
                with col_table2:
                    st.subheader("2. Malzeme Cek Listesi")
                    if tum_malzemeler:
                        malz_items = [{"Malzeme": k, "Adet": int(v) if v%1==0 else v} for k,v in tum_malzemeler.items()]
                        st.dataframe(pd.DataFrame(malz_items), hide_index=True, use_container_width=True)

                st.divider()
                st.subheader("🖨️ Cikti Al")
                col_pdf1, col_pdf2 = st.columns(2)
                
                pdf_cargo = create_cargo_pdf(proje_toplam_desi, toplam_parca, musteri_data, etiket_listesi)
                col_pdf1.download_button(label="📄 1. KARGO FISI (A4)", data=pdf_cargo, file_name="Kargo_Fisi.pdf", mime="application/pdf", use_container_width=True)

                pdf_production = create_production_pdf(tum_malzemeler, etiket_listesi, musteri_data)
                col_pdf2.download_button(label="🏭 2. URETIM & ETIKETLER", data=pdf_production, file_name="Uretim_ve_Etiketler.pdf", mime="application/pdf", use_container_width=True)
                
            else: st.error("Dosyada 'Stok Adı' basligi bulunamadi.")
        except Exception as e: st.error(f"Hata: {e}")

# --- TAB 2: MANUEL HESAPLAYICI ---
with tab_manuel:
    st.header("🧮 Hızlı Desi Hesaplama")
    if 'manuel_liste' not in st.session_state: st.session_state['manuel_liste'] = []

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        modeller = ["Standart Radyatör", "Havlupan"] + [m.capitalize() for m in MODEL_DERINLIKLERI.keys() if m != 'livera']
        secilen_model = st.selectbox("Model", modeller)
        is_havlupan = 'havlupan' in secilen_model.lower() or any(z in secilen_model.lower() for z in ZORUNLU_HAVLUPANLAR)
        l1, l2, v1_def, v2_def = ("Genişlik", "Yükseklik", 50, 70) if is_havlupan else ("Yükseklik", "Genişlik", 60, 100)
    with c2: val1 = st.number_input(l1, 10, value=v1_def)
    with c3: val2 = st.number_input(l2, 10, value=v2_def)
    with c4: m_adet = st.number_input("Adet", 1, value=1)
        
    if st.button("➕ Listeye Ekle"):
        g, y = (val1, val2) if is_havlupan else (val2, val1)
        desi, boyut, kg = manuel_hesapla(secilen_model, g, y, m_adet)
        st.session_state['manuel_liste'].append({
            "Model": secilen_model, "Ölçü": f"{g}x{y}", "Kutu": boyut, "Adet": m_adet,
            "Desi": round(desi*m_adet,2), "KG": kg
        })

    if st.session_state['manuel_liste']:
        df_m = pd.DataFrame(st.session_state['manuel_liste'])
        st.dataframe(df_m, use_container_width=True)
        
        try:
            t_adet = df_m['Adet'].sum()
            t_desi = df_m['Desi'].sum()
            t_kg = df_m['KG'].sum()
            
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Toplam Parça", t_adet)
            mc2.metric("Toplam Desi", f"{t_desi:.2f}")
            mc3.metric("Toplam Ağırlık", f"{t_kg:.2f} KG")
        except: pass
        
        # Manuel Kayıt Butonu
        if ad_soyad and st.button("💾 Manuel Listeyi Veritabanına Kaydet"):
            man_kayitlar = []
            for item in st.session_state['manuel_liste']:
                man_kayitlar.append([str(tarih_secimi), ad_soyad, item['Model'], item['Ölçü'], item['Adet'], 0, "Manuel"])
            basari, m = save_to_google_sheets(man_kayitlar)
            if basari: st.success("Manuel liste kaydedildi!"); st.session_state['manuel_liste'] = []
            else: st.error(m)
            
        if st.button("🗑️ Listeyi Temizle"):
             st.session_state['manuel_liste'] = []
             st.rerun()

# --- TAB 3: SATIŞ RAPORLARI (YENİ) ---
with tab_rapor:
    st.header("📊 Satış ve Üretim Raporları")
    df_rapor = get_data_from_google_sheets()
    
    if not df_rapor.empty:
        # Filtreler
        all_musteri = ["Tümü"] + list(df_rapor['Musteri'].unique())
        filtre_musteri = st.selectbox("Müşteri Filtrele", all_musteri)
        
        if filtre_musteri != "Tümü":
            df_rapor = df_rapor[df_rapor['Musteri'] == filtre_musteri]
            
        # Özet Kartlar
        toplam_urun = df_rapor['Adet'].sum()
        toplam_kayit = len(df_rapor)
        en_cok_satilan = df_rapor['Model'].mode()[0] if not df_rapor.empty else "-"
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Toplam Satılan Ürün", toplam_urun)
        k2.metric("Toplam İşlem Sayısı", toplam_kayit)
        k3.metric("En Çok Giden Model", en_cok_satilan)
        
        st.divider()
        
        # Grafikler
        g1, g2 = st.columns(2)
        with g1:
            st.subheader("Modellere Göre Dağılım")
            model_counts = df_rapor['Model'].value_counts()
            st.bar_chart(model_counts)
            
        with g2:
            st.subheader("Son Kayıtlar")
            st.dataframe(df_rapor.tail(10), use_container_width=True)
            
    else:
        st.info("Henüz veritabanında kayıt yok veya bağlantı kurulamadı.")
