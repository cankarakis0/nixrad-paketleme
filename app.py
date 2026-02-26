import streamlit as st
import pandas as pd
import re
import io
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
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
            'Adet': int(adet), 
            'Reçete': reçete,
            'Etiket': {'kisa_isim': isim_kisalt(stok_adi), 'boyut_str': f"{k_en}x{k_boy}x{k_derin}cm", 'desi_val': desi},
            'Toplam_Desi': desi * adet, 
            'Toplam_Agirlik': agirlik_sonuc * adet,
            'Ürün': isim_kisalt(stok_adi),
            'Ölçü': f"{k_en}x{k_boy}x{k_derin}cm",
            'Birim_Desi': desi,
            'Toplam_Agirlik_Gosterim': round(agirlik_sonuc * adet, 1)
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
    if 'prag' in model_lower:
        paylar['PAY_DERINLIK'] = 2.0
    
    k_en, k_boy, k_derin = genislik + paylar['PAY_GENISLIK'], yukseklik + paylar['PAY_YUKSEKLIK'], base_derinlik + paylar['PAY_DERINLIK']
    desi = round((k_en * k_boy * k_derin) / 3000, 2)
    birim_kg = agirlik_hesapla("", genislik, yukseklik, model_key)
    return desi, f"{k_en}x{k_boy}x{k_derin}cm", round(birim_kg * adet, 2)

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
    alici_ad = tr_clean_for_pdf(musteri_bilgileri.get('AD_SOYAD', '.....'))
    alici_tel = musteri_bilgileri.get('TELEFON', '.....')
    
    # A4 Fis icin Adres ve Il/Ilce birlestirme
    clean_adres = tr_clean_for_pdf(musteri_bilgileri.get('ADRES', 'Adres Girilmedi'))
    a4_il_ilce = tr_clean_for_pdf(musteri_bilgileri.get('IL_ILCE', ''))
    if a4_il_ilce:
        clean_adres += f"<br/><b>{a4_il_ilce.upper()}</b>"

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
    t_warn = Table([[warning_title], [warning_para]], colWidths=[19*cm], style=TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.black), ('BOX', (0,0), (-1,-1), 1, colors.black), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('PADDING', (0,0), (-1,-1), 10), ('BOTTOMPADDING', (0,0), (-1,0), 10)]))
    elements.append(t_warn)
    doc.build(elements); buffer.seek(0); return buffer

def create_production_pdf(tum_malzemeler, etiket_listesi, musteri_bilgileri):
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.5*cm, leftMargin=0.5*cm, topMargin=1*cm, bottomMargin=1*cm); elements = []
    styles = getSampleStyleSheet()
    cust_name = tr_clean_for_pdf(musteri_bilgileri.get('AD_SOYAD', 'Isim Girilmedi'))
    elements.append(Paragraph(f"URETIM & PAKETLEME EMRI - {cust_name}", ParagraphStyle('Title', fontSize=16, alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=15)))
    data = [['MALZEME ADI', 'ADET', 'KONTROL']] + [[Paragraph(tr_clean_for_pdf(m), ParagraphStyle('malz_style', fontSize=10, fontName='Helvetica')), f"{int(v)}" if v%1==0 else f"{v:.1f}", "___"] for m, v in tum_malzemeler.items()]
    t = Table(data, colWidths=[14*cm, 2*cm, 3*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('ALIGN', (1,0), (-1,-1), 'CENTER'), ('ALIGN', (2,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('PADDING', (0,0), (-1,-1), 6)]))
    elements.append(t); elements.append(Spacer(1, 1*cm))
    signature_data = [["PAKETLEYEN PERSONEL", "", ""], ["Adi Soyadi: ....................................", "", ""], ["Imza: ....................................", "", ""]]
    t_sig = Table(signature_data, colWidths=[8*cm, 2*cm, 8*cm], style=TableStyle([('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('ALIGN', (0,0), (-1,-1), 'LEFT'), ('BOTTOMPADDING', (0,0), (-1,-1), 10)]))
    elements.append(t_sig); elements.append(Spacer(1, 0.5*cm)); elements.append(Paragraph("-" * 120, ParagraphStyle('sep', alignment=TA_CENTER))); elements.append(Paragraph("ASAGIDAKI ETIKETLERI KESIP KOLILERE YAPISTIRINIZ (6x6 cm)", ParagraphStyle('Small', fontSize=8, alignment=TA_CENTER))); elements.append(Spacer(1, 0.5*cm))
    
    sticker_data, row = [], []
    style_num = ParagraphStyle('n', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=14, textColor=colors.black, fontName='Helvetica-Bold')
    style_cust = ParagraphStyle('c_bold', alignment=TA_CENTER, fontSize=10, fontName='Helvetica-Bold', textColor=colors.black)
    
    for p in etiket_listesi:
        isim, boyut, desi, no = tr_clean_for_pdf(p['kisa_isim']), p['boyut_str'], str(p['desi_val']), str(p['sira_no'])
        cust_short = tr_clean_for_pdf(musteri_bilgileri.get('AD_SOYAD', '')[:25])
        content = [[Paragraph(f"<b>#{no}</b>", style_num)], [Paragraph(f"<b>{isim}</b>", ParagraphStyle('C', alignment=TA_CENTER, fontSize=9))], [Paragraph(f"{boyut}", ParagraphStyle('C', alignment=TA_CENTER, fontSize=8))], [Spacer(1, 0.2*cm)], [Paragraph(f"<b>Desi: {desi}</b>", ParagraphStyle('L', alignment=TA_LEFT, fontSize=11))], [Paragraph(f"<b>{cust_short}</b>", style_cust)]]
        box = Table(content, colWidths=[5.8*cm], rowHeights=[0.8*cm, 1.2*cm, 0.5*cm, 0.5*cm, 0.8*cm, 0.5*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0)]))
        row.append(box)
        if len(row)==3: sticker_data.append(row); row = []
    if row: 
        while len(row)<3: row.append("")
        sticker_data.append(row)
    if sticker_data: elements.append(Table(sticker_data, colWidths=[6.5*cm]*3, style=TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 15)])))
    doc.build(elements); buffer.seek(0); return buffer

# =============================================================================
# GÜNCELLENMİŞ TERMAL ETİKET (İl/İlçe BOLD ve Dinamik Yazdırma)
# =============================================================================
def create_thermal_labels_8x12_rotated(etiket_listesi, musteri_bilgileri, toplam_etiket_sayisi):
    buffer = io.BytesIO()
    p_width, p_height = 80*mm, 120*mm
    c = canvas.Canvas(buffer, pagesize=(p_width, p_height))
    
    logo_url = "https://static.ticimax.cloud/74661/Uploads/HeaderTasarim/Header1/b2d2993a-93a3-4b7f-86be-cd5911e270b6.jpg"

    for p in etiket_listesi:
        c.saveState()
        c.rotate(90)
        c.translate(0, -p_width)
        d_width, d_height = 120*mm, 80*mm

        # 1. Logo
        try:
            response = requests.get(logo_url)
            logo_img = ImageReader(io.BytesIO(response.content))
            c.drawImage(logo_img, 4*mm, d_height - 14*mm, width=25*mm, height=10*mm, mask='auto')
        except: pass

        no_str = f"PAKET: {p['sira_no']} / {toplam_etiket_sayisi}"
        alici_ad = tr_clean_for_pdf(musteri_bilgileri.get('AD_SOYAD', 'MUSTERI ADI'))
        alici_adres = tr_clean_for_pdf(musteri_bilgileri.get('ADRES', 'ADRES GIRILMEDI'))
        alici_tel = musteri_bilgileri.get('TELEFON', 'TELEFON YOK')
        urun_adi = tr_clean_for_pdf(p['kisa_isim'])
        desi_text = f"DESI : {p['desi_val']}"
        odeme_tipi_val = tr_clean_for_pdf(musteri_bilgileri.get('ODEME_TIPI', 'ALICI')) + " ODEME"
        
        # İl / İlçe bilgisini hazırlama
        il_ilce_metni = tr_clean_for_pdf(musteri_bilgileri.get('IL_ILCE', '')).upper()

        # 2. Gonderen Bilgileri
        c.setFont("Helvetica-Bold", 8)
        c.drawString(45*mm, d_height - 5*mm, "GONDEREN FIRMA: NIXRAD / KARPAN DIZAYN A.S.")
        c.setFont("Helvetica", 7)
        c.drawString(45*mm, d_height - 9*mm, "Yeni Cami OSB Mah. 3.Cad. No:1 Kavak/SAMSUN")
        c.drawString(45*mm, d_height - 13*mm, "Tel: 0262 658 11 58")
        
        c.setLineWidth(0.4)
        c.line(3*mm, d_height - 17*mm, d_width - 3*mm, d_height - 17*mm)
        
        # 3. Alici Musteri
        c.setFont("Helvetica-Bold", 10)
        c.drawString(5*mm, d_height - 23*mm, "ALICI MUSTERI:")
        c.setFont("Helvetica-Bold", 16)
        c.drawString(5*mm, d_height - 31*mm, alici_ad[:70])
        c.line(3*mm, d_height - 34*mm, d_width - 3*mm, d_height - 34*mm)
        
        # 4. Adres (Dinamik Font ve İlçe/İl Kalın Yazdırma)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(5*mm, d_height - 40*mm, "ADRES :")
        
        adres_uzunluk = len(alici_adres)
        
        if adres_uzunluk <= 70:
            adres_font, adres_lead = 14, 16
        elif adres_uzunluk <= 110:
            adres_font, adres_lead = 12, 14
        elif adres_uzunluk <= 160:
            adres_font, adres_lead = 10, 12
        else:
            adres_font, adres_lead = 8, 10
            
        text_obj = c.beginText(24*mm, d_height - 40*mm)
        text_obj.setFont("Helvetica", adres_font)
        text_obj.setLeading(adres_lead)
        
        max_text_width = d_width - 27*mm 
        words = alici_adres.split()
        line = ""
        for word in words:
            if c.stringWidth(line + word, "Helvetica", adres_font) < max_text_width:
                line += word + " "
            else:
                if line == "": 
                    text_obj.textLine(word)
                else:
                    text_obj.textLine(line)
                    line = word + " "
        if line:
            text_obj.textLine(line)
        c.drawText(text_obj)
        
        # --- İL / İLÇEYİ KALIN YAZDIRMA ---
        kalan_y = text_obj.getY() 
        if il_ilce_metni:
            c.setFont("Helvetica-Bold", adres_font + 3) 
            c.drawString(24*mm, kalan_y - 2*mm, il_ilce_metni)
        # -----------------------------------
            
        c.line(3*mm, d_height - 58*mm, d_width - 3*mm, d_height - 58*mm)
        
        # 5. Telefon ve Urun Detay
        c.setFont("Helvetica-Bold", 12)
        c.drawString(5*mm, d_height - 65*mm, f"TEL : {alici_tel}")
        
        c.setFont("Helvetica-Bold", 13)
        c.drawString(5*mm, d_height - 74*mm, urun_adi)

        # 6. Odeme Tipi
        c.setFont("Helvetica-Bold", 13)
        c.drawRightString(d_width - 5*mm, d_height - 65*mm, odeme_tipi_val)
        
        # 7. Desi ve Paket No
        c.setFont("Helvetica-Bold", 12)
        c.drawString(5*mm, d_height - 79*mm, desi_text)
        
        c.setFont("Helvetica-Bold", 15)
        c.drawRightString(d_width - 5*mm, d_height - 79*mm, no_str)
        
        c.restoreState()
        c.showPage()
    
    c.save()
    buffer.seek(0)
    return buffer

# =============================================================================
# 3. WEB ARAYÜZÜ
# =============================================================================

st.markdown(
    """
    # 📦 NIXRAD Operasyon Paneli 
    ### by [NETMAKER](https://netmaker.com.tr/)
    """, 
    unsafe_allow_html=True
)

st.sidebar.header("Müşteri Bilgileri")
ad_soyad = st.sidebar.text_input("Adı Soyadı / Firma Adı")
telefon = st.sidebar.text_input("Telefon Numarası")

# Adres ve İl/İlçe girişi (Tek Kutuya Düşürüldü)
adres = st.sidebar.text_area("Açık Adres (İl ve İlçe Hariç)")
il_ilce = st.sidebar.text_input("İl / İlçe")

odeme_tipi = st.sidebar.radio("Ödeme Tipi", ["ALICI", "PEŞİN"], index=0)

musteri_data = {
    'AD_SOYAD': ad_soyad, 
    'TELEFON': telefon, 
    'ADRES': adres, 
    'IL_ILCE': il_ilce,
    'ODEME_TIPI': odeme_tipi
}

tab_dosya, tab_manuel = st.tabs(["📂 Dosya ile Hesapla", "🧮 Manuel Hesaplayıcı"])

with tab_dosya:
    uploaded_file = st.file_uploader("Dia Excel/CSV Dosyasını Yükleyin", type=['xls', 'xlsx', 'csv'])

    if 'ham_veri' not in st.session_state: st.session_state['ham_veri'] = []
    if 'malzeme_listesi' not in st.session_state: st.session_state['malzeme_listesi'] = {}

    if uploaded_file:
        if st.button("Dosyayı Analiz Et ve Düzenle"):
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
                    
                    st.session_state['ham_veri'] = [] 
                    st.session_state['malzeme_listesi'] = {} 
                    
                    for index, row in df.iterrows():
                        try: adet = float(row['Miktar'])
                        except: adet = 0
                        stok_adi = str(row['Stok Adı']); stok_lower = tr_lower(stok_adi)
                        
                        if adet > 0:
                            is_vana_accessory = ('vana' in stok_lower) and ('nirvana' not in stok_lower)
                            is_other_accessory = any(x in stok_lower for x in ['volan', 'tapa', 'aksesuar', 'set', 'termo', 'köşe'])
                            
                            if is_vana_accessory or is_other_accessory:
                                 key = f"{stok_adi} (Adet)"
                                 st.session_state['malzeme_listesi'][key] = st.session_state['malzeme_listesi'].get(key, 0) + adet
                            
                            elif 'radyatör' in stok_lower or 'havlupan' in stok_lower or 'radyator' in stok_lower:
                                analiz = hesapla_ve_analiz_et(stok_adi, adet)
                                if analiz:
                                    for miktar, birim, ad in analiz['Reçete']:
                                        key = f"{ad} ({birim})"
                                        st.session_state['malzeme_listesi'][key] = st.session_state['malzeme_listesi'].get(key, 0) + (miktar * adet)
                                    
                                    st.session_state['ham_veri'].append({
                                        "Ürün": analiz['Etiket']['kisa_isim'],
                                        "Adet": int(adet),
                                        "Ölçü": analiz['Etiket']['boyut_str'],
                                        "Birim Desi": analiz['Etiket']['desi_val'],
                                        "Toplam Ağırlık": analiz['Toplam_Agirlik_Gosterim']
                                    })
                else:
                    st.error("Dosyada 'Stok Adı' başlığı bulunamadı.")
            except Exception as e:
                st.error(f"Hata: {e}")

    if st.session_state['ham_veri']:
        st.divider()
        ozet_alani = st.container()
        st.info("📝 Aşağıdaki tablodan Ürün Adı, Adet, Ölçü ve Desi bilgilerini düzenleyebilirsiniz.")
        
        edited_df = st.data_editor(
            pd.DataFrame(st.session_state['ham_veri']),
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Adet": st.column_config.NumberColumn(format="%d"),
                "Birim Desi": st.column_config.NumberColumn(format="%.2f"),
                "Toplam Ağırlık": st.column_config.NumberColumn(format="%.1f")
            }
        )

        toplam_parca = edited_df["Adet"].sum()
        proje_toplam_desi = (edited_df["Birim Desi"] * edited_df["Adet"]).sum()
        proje_toplam_agirlik = edited_df["Toplam Ağırlık"].sum()

        with ozet_alani:
            st.subheader("📊 Proje Özeti")
            c1, c2, c3 = st.columns(3)
            c1.metric("📦 Toplam Koli", int(toplam_parca))
            c2.metric("📐 Toplam Desi", f"{proje_toplam_desi:.2f}")
            c3.metric("⚖️ Toplam Ağırlık", f"{proje_toplam_agirlik:.1f} KG")
            kopyalanacak_metin = f"toplam desi {proje_toplam_desi:.2f}  toplam ağırlık {proje_toplam_agirlik:.1f}"
            st.code(kopyalanacak_metin, language="text")
            st.divider() 

        st.subheader("🛠️ Malzeme Çek Listesi (Düzenlenebilir)")
        malz_df = pd.DataFrame([{"Malzeme": k, "Adet": v} for k,v in st.session_state['malzeme_listesi'].items()])
        edited_malz_df = st.data_editor(
            malz_df,
            key="malzeme_editor",
            num_rows="dynamic",
            use_container_width=True,
            column_config={"Adet": st.column_config.NumberColumn(format="%.1f")}
        )
        final_malzeme_listesi = dict(zip(edited_malz_df['Malzeme'], edited_malz_df['Adet']))

        final_etiket_listesi = []
        global_counter = 1
        for index, row in edited_df.iterrows():
            qty = int(row['Adet'])
            for i in range(qty):
                final_etiket_listesi.append({
                    'sira_no': global_counter,
                    'kisa_isim': row['Ürün'],
                    'boyut_str': row['Ölçü'],
                    'desi_val': row['Birim Desi']
                })
                global_counter += 1

        st.divider()
        st.subheader("🖨️ Düzenlenmiş Çıktı Al")
        col_pdf1, col_pdf2, col_pdf3 = st.columns(3)
        
        pdf_cargo = create_cargo_pdf(proje_toplam_desi, toplam_parca, musteri_data, final_etiket_listesi)
        col_pdf1.download_button(label="📄 1. KARGO FİŞİ (A4)", data=pdf_cargo, file_name="Kargo_Fisi.pdf", mime="application/pdf", use_container_width=True)

        pdf_production = create_production_pdf(final_malzeme_listesi, final_etiket_listesi, musteri_data)
        col_pdf2.download_button(label="🏭 2. ÜRETİM & ETİKETLER", data=pdf_production, file_name="Uretim_ve_Etiketler.pdf", mime="application/pdf", use_container_width=True)

        # GÜNCEL TERMAL BUTON
        pdf_thermal = create_thermal_labels_8x12_rotated(final_etiket_listesi, musteri_data, int(toplam_parca))
        col_pdf3.download_button(label="🏷️ 3. TERMAL ETIKET (Yan)", data=pdf_thermal, file_name="Termal_Etiketler.pdf", mime="application/pdf", use_container_width=True)

with tab_manuel:
    st.header("🧮 Hızlı Desi Hesaplama Aracı")
    if 'manuel_liste' not in st.session_state: st.session_state['manuel_liste'] = []

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        display_models = ["Standart Radyatör", "Havlupan"] + [m.capitalize() for m in MODEL_DERINLIKLERI.keys() if m != 'livera']
        secilen_model = st.selectbox("Model Seçin", display_models)
        model_lower = secilen_model.lower()
        is_havlupan = 'havlupan' in model_lower or any(z in model_lower for z in ZORUNLU_HAVLUPANLAR)
        
        if is_havlupan:
            label_1, label_2 = "Genişlik (cm)", "Yükseklik (cm)"
            val_1_default, val_2_default = 50, 70
        else:
            label_1, label_2 = "Yükseklik (cm)", "Genişlik (cm)"
            val_1_default, val_2_default = 60, 100
        
    with col_m2: val_1 = st.number_input(label_1, min_value=10, value=val_1_default)
    with col_m3: val_2 = st.number_input(label_2, min_value=10, value=val_2_default)
    with col_m4: m_adet = st.number_input("Adet", min_value=1, value=1)
        
    if st.button("➕ Listeye Ekle", type="primary"):
        g_input, y_input = (val_1, val_2) if is_havlupan else (val_2, val_1)
        birim_desi, boyut_str, birim_kg = manuel_hesapla(secilen_model, g_input, y_input, m_adet)
        st.session_state['manuel_liste'].append({
            "Model": secilen_model, "Ölçü (ExB)": f"{g_input} x {y_input}", "Kutulu Ölçü": boyut_str,
            "Adet": m_adet, "Birim Desi": birim_desi, "Toplam Desi": round(birim_desi * m_adet, 2),
            "Toplam Ağırlık": f"{birim_kg:.2f} KG"
        })
        st.success("Eklendi!")

    if st.session_state['manuel_liste']:
        st.divider()
        df_manuel = pd.DataFrame(st.session_state['manuel_liste'])
        st.dataframe(df_manuel, use_container_width=True)
        t_adet = df_manuel['Adet'].sum()
        t_desi = df_manuel['Toplam Desi'].sum()
        try: t_kg = sum([float(x['Toplam Ağırlık'].replace(' KG','')) for x in st.session_state['manuel_liste']])
        except: t_kg = 0
        
        c_tot1, c_tot2, c_tot3 = st.columns(3)
        c_tot1.metric("Toplam Parça", t_adet); c_tot2.metric("Genel Toplam Desi", f"{t_desi:.2f}"); c_tot3.metric("Genel Toplam Ağırlık", f"{t_kg:.2f} KG")
        
        if st.button("🗑️ Listeyi Temizle"):
            st.session_state['manuel_liste'] = []; st.rerun()
