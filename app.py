import streamlit as st
import pandas as pd
import re
import io
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Matplotlib Backend Fix
plt_backend = 'Agg'
try:
    import matplotlib.pyplot as plt
    plt.switch_backend(plt_backend)
except:
    pass

# =============================================================================
# 1. AYARLAR
# =============================================================================
st.set_page_config(page_title="Nixrad Operasyon", layout="wide")

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
    'akasya': 0.75, 'aspar': 1.05, 'lizyantus': 0.750, 'kumbaros': 0.856
}

HAVLUPAN_BORU_CETVELI = {
    'lizyantus': {70: 6, 100: 8, 120: 10, 150: 12},
    'kumbaros': {70: 5, 100: 7, 120: 8, 150: 10}
}

RENKLER = ["BEYAZ", "ANTRASIT", "SIYAH", "KROM", "ALTIN", "GRI", "KIRMIZI"]

# =============================================================================
# 2. YARDIMCI FONKSİYONLAR
# =============================================================================

def tr_clean_for_pdf(text):
    if not isinstance(text, str): return str(text)
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
    return f"{model_adi} {boyut} {renk}".strip()

def get_standart_paket_icerigi(tip, model_adi):
    amb = "GENEL AMBALAJLAMA (Karton+ balon + Strec)"
    if tip == 'HAVLUPAN': return [(1, "Adet", "1/2 PURJOR"), (1, "Takim", "3 LU HAVLUPAN MONTAJ SETI"), (3, "Adet", "DUBEL"), (3, "Adet", "MONTAJ VIDASI"), (1, "Set", amb)]
    else:
        ayak = f"{tr_clean_for_pdf(model_adi)} AYAK TAKIMI" if model_adi != "STANDART" else "RADYATOR AYAK TAKIMI"
        return [(1, "Adet", "1/2 KOR TAPA"), (1, "Adet", "1/2 PURJOR"), (1, "Takim", ayak), (8, "Adet", "DUBEL"), (8, "Adet", "MONTAJ VIDASI"), (1, "Set", amb)]

def agirlik_hesapla(stok_adi, genislik_cm, yukseklik_cm, model_key):
    if model_key not in MODEL_AGIRLIKLARI: return 0
    if model_key not in ['lizyantus', 'kumbaros']:
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
    else:
        boru_sayisi = 0
        if model_key in HAVLUPAN_BORU_CETVELI:
            if int(yukseklik_cm) in HAVLUPAN_BORU_CETVELI[model_key]:
                boru_sayisi = HAVLUPAN_BORU_CETVELI[model_key][int(yukseklik_cm)]
            else:
                div = 12.5 if model_key == 'lizyantus' else 15.0
                boru_sayisi = round(yukseklik_cm / div)
        else: boru_sayisi = round(yukseklik_cm / 7.5)
        ref_agirlik = MODEL_AGIRLIKLARI.get(model_key, 0)
        genislik_katsayisi = genislik_cm / 50.0
        agirlik = boru_sayisi * ref_agirlik * genislik_katsayisi
        return round(agirlik, 2)

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
    is_havlupan_name = 'havlupan' in stok_adi_islenen or any(z in stok_adi_islenen for z in ZORUNLU_HAVLUPANLAR)
    tip = 'HAVLUPAN' if is_havlupan_name else 'RADYATOR'
    reçete = get_standart_paket_icerigi(tip, tr_upper(bulunan_model_adi))
    paylar = AYARLAR[tip].copy()
    if bulunan_model_key == 'prag':
        paylar['PAY_DERINLIK'] = 2.0
    boyutlar = re.search(r'(\d+)\s*[/xX]\s*(\d+)', stok_adi)
    if boyutlar:
        v1, v2 = int(boyutlar.group(1)) / 10, int(boyutlar.group(2)) / 10
        if tip == 'HAVLUPAN': genislik, yukseklik = v1, v2
        else: yukseklik, genislik = v1, v2
        k_en, k_boy, k_derin = genislik + paylar['PAY_GENISLIK'], yukseklik + paylar['PAY_YUKSEKLIK'], base_derinlik + paylar['PAY_DERINLIK']
        desi = round((k_en * k_boy * k_derin) / 3000, 2)
        agirlik_sonuc = agirlik_hesapla(stok_adi, genislik, yukseklik, bulunan_model_key)
        return {
            'Adet': int(adet), 'Reçete': reçete,
            'Etiket': {'kisa_isim': isim_kisalt(stok_adi), 'boyut_str': f"{k_en}x{k_boy}x{k_derin}cm", 'desi_val': desi},
            'Toplam_Desi': desi * adet, 'Toplam_Agirlik': agirlik_sonuc * adet,
            'Ürün': isim_kisalt(stok_adi), 'Ölçü': f"{k_en}x{k_boy}x{k_derin}cm",
            'Birim_Desi': desi, 'Toplam_Agirlik_Gosterim': round(agirlik_sonuc * adet, 1)
        }
    return None

def manuel_hesapla(model_secimi, genislik, yukseklik, adet=1):
    model_lower = model_secimi.lower()
    is_h = 'havlupan' in model_lower or any(z in model_lower for z in ZORUNLU_HAVLUPANLAR)
    tip = 'HAVLUPAN' if is_h else 'RADYATOR'
    base_derinlik, model_key = 4.5, "standart"
    for m_key, m_val in MODEL_DERINLIKLERI.items():
        if m_key in model_lower: base_derinlik, model_key = m_val, m_key; break
    paylar = AYARLAR[tip].copy()
    if 'prag' in model_lower: paylar['PAY_DERINLIK'] = 2.0
    k_en, k_boy, k_derin = genislik + paylar['PAY_GENISLIK'], yukseklik + paylar['PAY_YUKSEKLIK'], base_derinlik + paylar['PAY_DERINLIK']
    desi = round((k_en * k_boy * k_derin) / 3000, 2)
    birim_kg = agirlik_hesapla("", genislik, yukseklik, model_key)
    return desi, f"{k_en}x{k_boy}x{k_derin}cm", round(birim_kg * adet, 2)

# =============================================================================
# PDF FONKSİYONLARI (ADET SÜTUNU EKLENMİŞ KARGO FİŞİ)
# =============================================================================

def create_thermal_labels_3x6(etiket_listesi, musteri_bilgileri, toplam_etiket_sayisi):
    buffer = io.BytesIO()
    width, height = 60*mm, 30*mm
    c = canvas.Canvas(buffer, pagesize=(width, height))
    logo_url = "https://static.ticimax.cloud/74661/Uploads/HeaderTasarim/Header1/b2d2993a-93a3-4b7f-86be-cd5911e270b6.jpg"

    for p in etiket_listesi:
        try:
            response = requests.get(logo_url)
            logo_img = ImageReader(io.BytesIO(response.content))
            c.drawImage(logo_img, 1*mm, height - 7.5*mm, width=12*mm, height=6*mm, mask='auto')
        except: pass

        no_str = f"{p['sira_no']}/{toplam_etiket_sayisi}"
        gonderen_header = "GONDEREN FIRMA: NIXRAD / KARPAN DIZAYN A.S."
        gonderen_info = "Yeni Cami OSB Mah. 3.Cad. No:1 Kavak/SAMSUN Tel: 0262 658 11 58"
        alici_ad = tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'] or "MUSTERI ADI")
        alici_adres = tr_clean_for_pdf(musteri_bilgileri['ADRES'] or "ADRES GIRILMEDI")
        alici_tel = musteri_bilgileri['TELEFON'] or "TELEFON YOK"
        urun_adi = tr_clean_for_pdf(p['kisa_isim'])
        desi = f"DESI : {p['desi_val']}"

        c.setFont("Helvetica-Bold", 4.5)
        c.drawString(14*mm, height - 3*mm, gonderen_header)
        c.setFont("Helvetica", 3.5)
        c.drawString(14*mm, height - 5*mm, gonderen_info)
        c.setLineWidth(0.15)
        c.line(1*mm, height - 8*mm, width - 1*mm, height - 8*mm)
        c.setFont("Helvetica-Bold", 6)
        c.drawString(2*mm, height - 10.5*mm, f"ALICI MUSTERI: {alici_ad}")
        c.line(1*mm, height - 11.5*mm, width - 1*mm, height - 11.5*mm)
        c.setFont("Helvetica-Bold", 5)
        addr_y = height - 14*mm
        if len(alici_adres) > 60:
            c.drawString(2*mm, addr_y, f"ADRES :{alici_adres[:60]}"); c.drawString(2*mm, addr_y - 2.5*mm, alici_adres[60:120])
        else: c.drawString(2*mm, addr_y, f"ADRES :{alici_adres}")
        c.line(1*mm, height - 18.5*mm, width - 1*mm, height - 18.5*mm)
        c.setFont("Helvetica-Bold", 6)
        c.drawString(2*mm, height - 21*mm, f"TEL : {alici_tel}")
        c.line(1*mm, height - 22*mm, width - 1*mm, height - 22*mm)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(2*mm, height - 25.5*mm, urun_adi)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(2*mm, height - 28.5*mm, desi)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(width - 2*mm, height - 28.5*mm, no_str)
        c.showPage()
    c.save(); buffer.seek(0); return buffer

def create_cargo_pdf(proje_toplam_desi, toplam_parca, musteri_bilgileri, ham_tablo_verisi):
    """
    Kargo Fişi - Adet sütunu eklenmiş versiyon.
    ham_tablo_verisi: Düzenlenmiş tablodaki (Ürün, Adet, Ölçü, Birim Desi) verileri içeren liste.
    """
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1*cm, leftMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm); elements = []
    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle('n', parent=styles['Normal'], fontSize=10, leading=12)
    style_header = ParagraphStyle('h', parent=styles['Normal'], fontSize=14, leading=16, fontName='Helvetica-Bold', textColor=colors.darkred)
    gonderen_info = [Paragraph("<b>GONDEREN FIRMA:</b>", style_normal), Paragraph("NIXRAD / KARPAN DIZAYN A.S.", style_header), Paragraph("Yeni Cami OSB Mah. 3.Cad. No:1 Kavak/SAMSUN", style_normal), Paragraph("Tel: 0262 658 11 58", style_normal)]
    odeme_clean = tr_clean_for_pdf(musteri_bilgileri.get('ODEME_TIPI', 'ALICI'))
    odeme_info = [Paragraph("<b>ODEME TIPI:</b>", style_normal), Spacer(1, 0.5*cm), Paragraph(f"<b>{odeme_clean} ODEMELI</b>", ParagraphStyle('big', fontSize=14, alignment=TA_CENTER, fontName='Helvetica-Bold'))]
    t_header = Table([[gonderen_info, odeme_info]], colWidths=[13*cm, 6*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 1, colors.black), ('GRID', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 8), ('BACKGROUND', (0,0), (-1,-1), colors.whitesmoke)]))
    elements.append(t_header); elements.append(Spacer(1, 0.5*cm))
    alici_ad, alici_tel = tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'] or "....."), musteri_bilgileri['TELEFON'] or "....."
    clean_adres = tr_clean_for_pdf(musteri_bilgileri['ADRES'] or "Adres Girilmedi")
    alici_content = [Paragraph("<b>ALICI MUSTERI:</b>", style_normal), Paragraph(f"<b>{alici_ad}</b>", ParagraphStyle('alici_ad_huge', fontSize=22, leading=26, fontName='Helvetica-Bold', spaceBefore=6, spaceAfter=12)), Paragraph(f"<b>Tel:</b> {alici_tel}", ParagraphStyle('tel_big', fontSize=12, leading=14)), Spacer(1, 0.5*cm), Paragraph(f"<b>ADRES:</b><br/>{clean_adres}", ParagraphStyle('adres_style_big', fontSize=15, leading=20))]
    t_alici = Table([[alici_content]], colWidths=[19*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 2, colors.black), ('PADDING', (0,0), (-1,-1), 15)]))
    elements.append(t_alici); elements.append(Spacer(1, 0.5*cm))
    
    # ADET SÜTUNU EKLENMİŞ TABLO
    pkt_data = [['Urun Adi', 'Adet', 'Olcu', 'Desi']] 
    for row in ham_tablo_verisi:
        pkt_data.append([tr_clean_for_pdf(row['Ürün']), str(row['Adet']), row['Ölçü'], str(row['Birim Desi'])])
    
    t_pkt = Table(pkt_data, colWidths=[10*cm, 2*cm, 5*cm, 2*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('ALIGN', (1,0), (1,0), 'CENTER'), ('FONTSIZE', (0,0), (-1,-1), 9)]))
    elements.append(t_pkt); elements.append(Spacer(1, 0.5*cm))
    summary_data = [[f"TOPLAM KOLİ: {int(toplam_parca)}", f"TOPLAM DESİ: {proje_toplam_desi:.2f}"]]
    t_sum = Table(summary_data, colWidths=[9.5*cm, 9.5*cm], style=TableStyle([('ALIGN', (0,0), (0,0), 'LEFT'), ('ALIGN', (1,0), (1,0), 'RIGHT'), ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 14), ('TEXTCOLOR', (1,0), (1,0), colors.blue), ('LINEBELOW', (0,0), (-1,-1), 2, colors.black)]))
    elements.append(t_sum); elements.append(Spacer(1, 1*cm))
    warning_title = Paragraph("<b>DIKKAT KIRILIR !</b>", ParagraphStyle('WT', fontSize=26, alignment=TA_CENTER, textColor=colors.white, fontName='Helvetica-Bold'))
    warning_text = "SAYIN MUSTERIMIZ,<br/>GELEN KARGONUZUN BULUNDUGU PAKETLERIN SAGLAM VE PAKETLERDE EZIKLIK OLMADIGINI KONTROL EDEREK ALINIZ. EKSIK VEYA HASARLI MALZEME VARSA LUTFEN KARGO GOREVLISINE AYNI GUN TUTANAK TUTTURUNUZ."
    t_warn = Table([[warning_title], [Paragraph(warning_text, ParagraphStyle('warn', alignment=TA_CENTER, textColor=colors.white, fontSize=11, leading=14, fontName='Helvetica-Bold'))]], colWidths=[19*cm], style=TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.black), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('PADDING', (0,0), (-1,-1), 10)]))
    elements.append(t_warn); doc.build(elements); buffer.seek(0); return buffer

def create_production_pdf(tum_malzemeler, etiket_listesi, musteri_bilgileri):
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.5*cm, leftMargin=0.5*cm, topMargin=1*cm, bottomMargin=1*cm); elements = []
    cust_name = tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'] or "Isim Girilmedi")
    elements.append(Paragraph(f"URETIM & PAKETLEME EMRI - {cust_name}", ParagraphStyle('Title', fontSize=16, alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=15)))
    data = [['MALZEME ADI', 'ADET', 'KONTROL']] + [[Paragraph(tr_clean_for_pdf(m), ParagraphStyle('m', fontSize=10)), f"{int(v)}" if v%1==0 else f"{v:.1f}", "___"] for m, v in tum_malzemeler.items()]
    t = Table(data, colWidths=[14*cm, 2*cm, 3*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('ALIGN', (1,0), (-1,-1), 'CENTER')]))
    elements.append(t); elements.append(Spacer(1, 1*cm))
    sticker_data, row = [], []
    for p in etiket_listesi:
        isim, boyut, desi, no, cust = tr_clean_for_pdf(p['kisa_isim']), p['boyut_str'], str(p['desi_val']), str(p['sira_no']), tr_clean_for_pdf((musteri_bilgileri['AD_SOYAD'] or "")[:25])
        content = [[Paragraph(f"<b>#{no}</b>", ParagraphStyle('n', alignment=TA_RIGHT, fontSize=14, fontName='Helvetica-Bold'))], [Paragraph(f"<b>{isim}</b>", ParagraphStyle('C', alignment=TA_CENTER, fontSize=9))], [Paragraph(f"{boyut}", ParagraphStyle('C', alignment=TA_CENTER, fontSize=8))], [Spacer(1, 0.2*cm)], [Paragraph(f"<b>Desi: {desi}</b>", ParagraphStyle('L', alignment=TA_LEFT, fontSize=11))], [Paragraph(f"<b>{cust}</b>", ParagraphStyle('cb', alignment=TA_CENTER, fontSize=10, fontName='Helvetica-Bold'))]]
        box = Table(content, colWidths=[5.8*cm], rowHeights=[0.8*cm, 1.2*cm, 0.5*cm, 0.5*cm, 0.8*cm, 0.5*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        row.append(box)
        if len(row)==3: sticker_data.append(row); row = []
    if row: row.extend([""] * (3 - len(row))); sticker_data.append(row)
    if sticker_data: elements.append(Table(sticker_data, colWidths=[6.5*cm]*3, style=TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 15)])))
    doc.build(elements); buffer.seek(0); return buffer

# =============================================================================
# 3. WEB ARAYÜZÜ
# =============================================================================

st.markdown("""# 📦 NIXRAD Operasyon Paneli \n ### by [NETMAKER](https://netmaker.com.tr/)""", unsafe_allow_html=True)
st.sidebar.header("Musteri Bilgileri")
ad_soyad = st.sidebar.text_input("Adi Soyadi / Firma Adi")
telefon = st.sidebar.text_input("Telefon Numarasi")
adres = st.sidebar.text_area("Adres")
odeme_tipi = st.sidebar.radio("Odeme Tipi", ["ALICI", "PESIN"], index=0)
musteri_data = {'AD_SOYAD': ad_soyad, 'TELEFON': telefon, 'ADRES': adres, 'ODEME_TIPI': odeme_tipi}

tab_dosya, tab_manuel = st.tabs(["📂 Dosya ile Hesapla", "🧮 Manuel Hesaplayıcı"])

with tab_dosya:
    uploaded_file = st.file_uploader("Dia Excel/CSV Dosyasini Yukleyin", type=['xls', 'xlsx', 'csv'])
    if 'ham_veri' not in st.session_state: st.session_state['ham_veri'] = []
    if 'malzeme_listesi' not in st.session_state: st.session_state['malzeme_listesi'] = {}

    if uploaded_file and st.button("Dosyayı Analiz Et ve Düzenle"):
        try:
            df_raw = pd.read_csv(uploaded_file, encoding='utf-8') if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            h_idx = -1
            for i, row in df_raw.iterrows():
                if "Stok Adı" in " ".join([str(v) for v in row.values]): h_idx = i; break
            if h_idx != -1:
                new_h = df_raw.iloc[h_idx]
                df = df_raw[h_idx + 1:].copy()
                df.columns = [str(col).strip() for col in new_h]
                try: df = df[['Stok Adı', 'Miktar']]
                except: df = df.iloc[:, [0, 2]]; df.columns = ['Stok Adı', 'Miktar']
                df = df.dropna(subset=['Stok Adı'])
                st.session_state['ham_veri'], st.session_state['malzeme_listesi'] = [], {}
                for _, row in df.iterrows():
                    try: adet = float(row['Miktar'])
                    except: adet = 0
                    stok_adi = str(row['Stok Adı']); stok_l = tr_lower(stok_adi)
                    if adet > 0:
                        if ('vana' in stok_l and 'nirvana' not in stok_l) or any(x in stok_l for x in ['volan', 'tapa', 'aksesuar', 'set']):
                            k = f"{stok_adi} (Adet)"
                            st.session_state['malzeme_listesi'][k] = st.session_state['malzeme_listesi'].get(k, 0) + adet
                        elif any(x in stok_l for x in ['radyatör', 'havlupan', 'radyator']):
                            analiz = hesapla_ve_analiz_et(stok_adi, adet)
                            if analiz:
                                for m, b, a in analiz['Reçete']:
                                    k = f"{a} ({b})"
                                    st.session_state['malzeme_listesi'][k] = st.session_state['malzeme_listesi'].get(k, 0) + (m * adet)
                                st.session_state['ham_veri'].append({"Ürün": analiz['Etiket']['kisa_isim'], "Adet": int(adet), "Ölçü": analiz['Etiket']['boyut_str'], "Birim Desi": analiz['Etiket']['desi_val'], "Toplam Ağırlık": analiz['Toplam_Agirlik_Gosterim']})
        except Exception as e: st.error(f"Hata: {e}")

    if st.session_state['ham_veri']:
        ozet_alani = st.container()
        edited_df = st.data_editor(pd.DataFrame(st.session_state['ham_veri']), num_rows="dynamic", use_container_width=True)
        toplam_parca, p_desi, p_kg = edited_df["Adet"].sum(), (edited_df["Birim Desi"] * edited_df["Adet"]).sum(), edited_df["Toplam Ağırlık"].sum()
        with ozet_alani:
            st.subheader("📊 Proje Özeti")
            c1, c2, c3 = st.columns(3)
            c1.metric("📦 Toplam Koli", int(toplam_parca)); c2.metric("📐 Toplam Desi", f"{p_desi:.2f}"); c3.metric("⚖️ Toplam Ağırlık", f"{p_kg:.1f} KG")
            st.code(f"toplam desi {p_desi:.2f}  toplam ağırlık {p_kg:.1f}", language="text")
        
        edited_malz_df = st.data_editor(pd.DataFrame([{"Malzeme": k, "Adet": v} for k,v in st.session_state['malzeme_listesi'].items()]), num_rows="dynamic", use_container_width=True)
        final_malz = dict(zip(edited_malz_df['Malzeme'], edited_malz_df['Adet']))
        final_etiket, counter = [], 1
        # Tablo verilerini PDF'e göndermek için hazırlıyoruz
        final_tablo_verisi = edited_df.to_dict('records')
        
        for _, row in edited_df.iterrows():
            for _ in range(int(row['Adet'])):
                final_etiket.append({'sira_no': counter, 'kisa_isim': row['Ürün'], 'boyut_str': row['Ölçü'], 'desi_val': row['Birim Desi']})
                counter += 1

        st.divider()
        col_p1, col_p2, col_p3 = st.columns(3)
        # Kargo fişine düzenlenen tablo verisini gönderiyoruz
        col_p1.download_button("📄 1. KARGO FISI (A4)", create_cargo_pdf(p_desi, toplam_parca, musteri_data, final_tablo_verisi), "Kargo_Fisi.pdf", "application/pdf", use_container_width=True)
        col_p2.download_button("🏭 2. URETIM & ETIKET (A4)", create_production_pdf(final_malz, final_etiket, musteri_data), "Uretim_ve_Etiketler.pdf", "application/pdf", use_container_width=True)
        col_p3.download_button("🏷️ 3. TERMAL ETIKET (3x6)", create_thermal_labels_3x6(final_etiket, musteri_data, len(final_etiket)), "Termal_Etiketler.pdf", "application/pdf", use_container_width=True)

with tab_manuel:
    st.header("🧮 Hızlı Desi Hesaplama Aracı")
    if 'manuel_liste' not in st.session_state: st.session_state['manuel_liste'] = []
    cm1, cm2, cm3, cm4 = st.columns(4)
    with cm1:
        secilen_model = st.selectbox("Model Seçin", ["Standart Radyatör", "Havlupan"] + [m.capitalize() for m in MODEL_DERINLIKLERI.keys() if m != 'livera'])
        is_h = 'havlupan' in secilen_model.lower() or any(z in secilen_model.lower() for z in ZORUNLU_HAVLUPANLAR)
    with cm2: v1 = st.number_input("Genişlik (cm)" if is_h else "Yükseklik (cm)", min_value=10, value=50 if is_h else 60)
    with cm3: v2 = st.number_input("Yükseklik (cm)" if is_h else "Genişlik (cm)", min_value=10, value=70 if is_h else 100)
    with cm4: m_adet = st.number_input("Adet", min_value=1, value=1)
    if st.button("➕ Listeye Ekle", type="primary"):
        gi, yi = (v1, v2) if is_h else (v2, v1)
        bd, bs, bk = manuel_hesapla(secilen_model, gi, yi, m_adet)
        st.session_state['manuel_liste'].append({"Ürün": secilen_model, "Adet": m_adet, "Ölçü": bs, "Birim Desi": bd, "Toplam Desi": round(bd*m_adet, 2), "Toplam Ağırlık": f"{bk:.2f} KG"})
    
    if st.session_state['manuel_liste']:
        df_m = pd.DataFrame(st.session_state['manuel_liste'])
        st.dataframe(df_m, use_container_width=True)
        m_etiketler, c = [], 1
        for item in st.session_state['manuel_liste']:
            for _ in range(item['Adet']):
                m_etiketler.append({'sira_no': c, 'kisa_isim': item['Ürün'], 'boyut_str': item['Ölçü'], 'desi_val': item['Birim Desi']})
                c += 1
        
        col_m1, col_m2 = st.columns(2)
        # Manuel liste için Kargo Fişi butonu (Adet sütunlu)
        m_tablo_verisi = df_m.to_dict('records')
        m_toplam_desi = df_m['Toplam Desi'].sum()
        m_toplam_parca = df_m['Adet'].sum()
        col_m1.download_button("📄 MANUEL KARGO FISI", create_cargo_pdf(m_toplam_desi, m_toplam_parca, musteri_data, m_tablo_verisi), "Manuel_Kargo_Fisi.pdf", "application/pdf")
        col_m2.download_button("🏷️ MANUEL TERMAL ETIKET BAS", create_thermal_labels_3x6(m_etiketler, musteri_data, len(m_etiketler)), "Manuel_Etiketler.pdf", "application/pdf")
        
        if st.button("🗑️ Listeyi Temizle"): st.session_state['manuel_liste'] = []; st.rerun()
