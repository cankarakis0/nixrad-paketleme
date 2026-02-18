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

# =============================================================================
# 1. AYARLAR VE VERİ YAPILARI
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

def agirlik_hesapla(stok_adi, genislik_cm, yukseklik_cm, model_key):
    if model_key not in MODEL_AGIRLIKLARI: return 0
    if model_key not in ['lizyantus', 'kumbaros']:
        dilim_match = re.search(r'(\d+)\s*DILIM', tr_upper(stok_adi))
        dilim_sayisi = int(dilim_match.group(1)) if dilim_match else 1
        kg_per_dilim = (yukseklik_cm / 60) * MODEL_AGIRLIKLARI[model_key]
        return round(dilim_sayisi * kg_per_dilim, 2)
    else:
        boru_sayisi = HAVLUPAN_BORU_CETVELI.get(model_key, {}).get(int(yukseklik_cm), round(yukseklik_cm / 12.5))
        return round(boru_sayisi * MODEL_AGIRLIKLARI[model_key] * (genislik_cm / 50.0), 2)

def hesapla_ve_analiz_et(stok_adi, adet):
    if not isinstance(stok_adi, str): return None
    st_lower = tr_lower(stok_adi)
    derinlik, m_key = 4.5, "standart"
    for m, d in MODEL_DERINLIKLERI.items():
        if m in st_lower: derinlik, m_key = d, m; break
    
    tip = 'HAVLUPAN' if ('havlupan' in st_lower or any(z in st_lower for z in ZORUNLU_HAVLUPANLAR)) else 'RADYATOR'
    paylar = AYARLAR[tip].copy()
    if m_key == 'prag': paylar['PAY_DERINLIK'] = 2.0

    boyutlar = re.search(r'(\d+)\s*[/xX]\s*(\d+)', stok_adi)
    if boyutlar:
        v1, v2 = int(boyutlar.group(1)) / 10, int(boyutlar.group(2)) / 10
        g, y = (v1, v2) if tip == 'HAVLUPAN' else (v2, v1)
        k_en, k_boy, k_derin = g + paylar['PAY_GENISLIK'], y + paylar['PAY_YUKSEKLIK'], derinlik + paylar['PAY_DERINLIK']
        desi = round((k_en * k_boy * k_derin) / 3000, 2)
        return {'Adet': int(adet), 'Ürün': isim_kisalt(stok_adi), 'Ölçü': f"{k_en}x{k_boy}x{k_derin}cm", 'Birim_Desi': desi, 'Toplam_Agirlik': round(agirlik_hesapla(stok_adi, g, y, m_key) * adet, 1)}
    return None

# =============================================================================
# 3. PDF VE TERMAL ETİKET (80x100mm)
# =============================================================================

def create_thermal_labels_8x10(etiket_listesi, musteri_bilgileri, toplam_etiket_sayisi):
    buffer = io.BytesIO()
    w, h = 80*mm, 100*mm
    c = canvas.Canvas(buffer, pagesize=(w, h))
    
    logo_url = "https://static.ticimax.cloud/74661/Uploads/HeaderTasarim/Header1/b2d2993a-93a3-4b7f-86be-cd5911e270b6.jpg"
    try: logo_img = ImageReader(io.BytesIO(requests.get(logo_url).content))
    except: logo_img = None

    for p in etiket_listesi:
        # Logo ve Firma
        if logo_img: c.drawImage(logo_img, 5*mm, h - 14*mm, width=25*mm, height=8*mm, mask='auto')
        c.setFont("Helvetica-Bold", 8)
        c.drawRightString(w - 5*mm, h - 8*mm, "NIXRAD / KARPAN DIZAYN A.S.")
        c.setFont("Helvetica", 6)
        c.drawRightString(w - 5*mm, h - 11*mm, "Kavak / SAMSUN | 0262 658 11 58")
        c.line(5*mm, h - 16*mm, w - 5*mm, h - 16*mm)

        # Alıcı (BÜYÜK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(5*mm, h - 22*mm, "ALICI:")
        c.setFont("Helvetica-Bold", 15)
        c.drawString(5*mm, h - 30*mm, tr_clean_for_pdf(musteri_bilgileri.get('AD_SOYAD', 'MUSTERI'))[:25])
        
        # Adres
        c.setFont("Helvetica", 10)
        addr = tr_clean_for_pdf(musteri_bilgileri.get('ADRES', 'ADRES YOK'))
        t_obj = c.beginText(5*mm, h - 38*mm)
        t_obj.setLeading(12)
        for i in range(0, len(addr), 35): t_obj.textLine(addr[i:i+35])
        c.drawText(t_obj)

        # Tel ve Çizgi
        c.setFont("Helvetica-Bold", 12)
        c.drawString(5*mm, h - 72*mm, f"TEL: {musteri_bilgileri.get('TELEFON', '')}")
        c.line(5*mm, h - 75*mm, w - 5*mm, h - 75*mm)

        # Ürün ve Desi
        c.setFont("Helvetica-Bold", 11)
        c.drawString(5*mm, h - 82*mm, tr_clean_for_pdf(p['kisa_isim']))
        c.setFont("Helvetica", 10)
        c.drawString(5*mm, h - 88*mm, f"OLCU: {p['boyut_str']}")
        
        c.setFont("Helvetica-Bold", 15)
        c.drawString(5*mm, h - 96*mm, f"DESI: {p['desi_val']}")
        
        # Paket No (EN BÜYÜK)
        c.setFont("Helvetica-Bold", 20)
        c.drawRightString(w - 5*mm, h - 96*mm, f"{p['sira_no']}/{toplam_etiket_sayisi}")
        c.showPage()
    
    c.save(); buffer.seek(0); return buffer

# =============================================================================
# 4. ARAYÜZ
# =============================================================================
st.sidebar.header("Müşteri Bilgileri")
m_ad = st.sidebar.text_input("Ad Soyad / Firma")
m_tel = st.sidebar.text_input("Telefon")
m_adres = st.sidebar.text_area("Adres")
m_data = {'AD_SOYAD': m_ad, 'TELEFON': m_tel, 'ADRES': m_adres}

st.title("📦 NIXRAD Operasyon Paneli")
up_file = st.file_uploader("Dia Excel Dosyası", type=['xlsx', 'xls'])

if 'ham_veri' not in st.session_state: st.session_state['ham_veri'] = []

if up_file and st.button("Dosyayı Analiz Et"):
    df = pd.read_excel(up_file)
    st.session_state['ham_veri'] = []
    for _, row in df.iterrows():
        stok = str(row.get('Stok Adı', ''))
        adet = row.get('Miktar', 0)
        if ('radyatör' in stok.lower() or 'havlupan' in stok.lower()) and adet > 0:
            analiz = hesapla_ve_analiz_et(stok, adet)
            if analiz: st.session_state['ham_veri'].append(analiz)

if st.session_state['ham_veri']:
    edited_df = st.data_editor(pd.DataFrame(st.session_state['ham_veri']), num_rows="dynamic", use_container_width=True)
    
    t_desi = (edited_df['Birim_Desi'] * edited_df['Adet']).sum()
    t_parca = int(edited_df['Adet'].sum())
    
    c1, c2 = st.columns(2)
    c1.metric("Toplam Desi", f"{t_desi:.2f}")
    c2.metric("Toplam Parça", t_parca)

    # Etiket Listesi Hazırlama
    e_list = []
    count = 1
    for _, r in edited_df.iterrows():
        for _ in range(int(r['Adet'])):
            e_list.append({'sira_no': count, 'kisa_isim': r['Ürün'], 'boyut_str': r['Ölçü'], 'desi_val': r['Birim_Desi']})
            count += 1

    if st.button("🏷️ TERMAL ETİKETLERİ OLUŞTUR (8x10 cm)"):
        pdf = create_thermal_labels_8x10(e_list, m_data, t_parca)
        st.download_button("PDF İndir", pdf, "Nixrad_Etiketler.pdf", "application/pdf")
