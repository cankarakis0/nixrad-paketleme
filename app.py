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
# 1. AYARLAR & HESAPLAMA MANTIĞI (DOKUNULMADI)
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

def tr_clean_for_pdf(text):
    if not isinstance(text, str): return str(text)
    text = text.replace('\n', ' ')
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

def agirlik_hesapla(stok_adi, genislik_cm, yukseklik_cm, model_key):
    if model_key not in MODEL_AGIRLIKLARI: return 0
    if model_key not in ['lizyantus', 'kumbaros']:
        dilim_match = re.search(r'(\d+)\s*DILIM', tr_upper(stok_adi))
        dilim_sayisi = int(dilim_match.group(1)) if dilim_match else 1
        kg_per_dilim = (yukseklik_cm / 60) * MODEL_AGIRLIKLARI[model_key]
        return round(dilim_sayisi * kg_per_dilim, 2)
    else:
        div = 12.5 if model_key == 'lizyantus' else 15.0
        boru_sayisi = round(yukseklik_cm / div)
        agirlik = boru_sayisi * MODEL_AGIRLIKLARI.get(model_key, 0) * (genislik_cm / 50.0)
        return round(agirlik, 2)

def hesapla_ve_analiz_et(stok_adi, adet):
    if not isinstance(stok_adi, str): return None
    stok_adi_islenen = tr_lower(stok_adi)
    base_derinlik, bulunan_model_key = 4.5, "standart"
    for model, derinlik in MODEL_DERINLIKLERI.items():
        if model in stok_adi_islenen:
            base_derinlik, bulunan_model_key = derinlik, model
            break
    tip = 'HAVLUPAN' if ('havlupan' in stok_adi_islenen or any(z in stok_adi_islenen for z in ZORUNLU_HAVLUPANLAR)) else 'RADYATOR'
    paylar = AYARLAR[tip].copy()
    if bulunan_model_key == 'prag': paylar['PAY_DERINLIK'] = 2.0
    boyutlar = re.search(r'(\d+)\s*[/xX]\s*(\d+)', stok_adi)
    if boyutlar:
        v1, v2 = int(boyutlar.group(1)) / 10, int(boyutlar.group(2)) / 10
        genislik, yukseklik = (v1, v2) if tip == 'HAVLUPAN' else (v2, v1)
        k_en, k_boy, k_derin = genislik + paylar['PAY_GENISLIK'], yukseklik + paylar['PAY_YUKSEKLIK'], base_derinlik + paylar['PAY_DERINLIK']
        desi = round((k_en * k_boy * k_derin) / 3000, 2)
        agirlik_sonuc = agirlik_hesapla(stok_adi, genislik, yukseklik, bulunan_model_key)
        return {
            'Adet': int(adet), 'Etiket': {'kisa_isim': isim_kisalt(stok_adi), 'boyut_str': f"{k_en}x{k_boy}x{k_derin}cm", 'desi_val': desi},
            'Toplam_Desi': desi * adet, 'Toplam_Agirlik': agirlik_sonuc * adet,
            'Ürün': isim_kisalt(stok_adi), 'Ölçü': f"{k_en}x{k_boy}x{k_derin}cm", 'Birim_Desi': desi, 'Toplam_Agirlik_Gosterim': round(agirlik_sonuc * adet, 1)
        }
    return None

def manuel_hesapla(model_secimi, genislik, yukseklik, adet=1):
    model_lower = model_secimi.lower()
    tip = 'HAVLUPAN' if ('havlupan' in model_lower or any(z in model_lower for z in ZORUNLU_HAVLUPANLAR)) else 'RADYATOR'
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
# 2. PDF TASARIMI (YENİLENMİŞ VE TAM DİNAMİK)
# =============================================================================

def create_thermal_labels_3x6(etiket_listesi, musteri_bilgileri, toplam_etiket_sayisi):
    buffer = io.BytesIO()
    width, height = 60*mm, 30*mm
    c = canvas.Canvas(buffer, pagesize=(width, height))
    logo_url = "https://static.ticimax.cloud/74661/Uploads/HeaderTasarim/Header1/b2d2993a-93a3-4b7f-86be-cd5911e270b6.jpg"

    # Yazı Stilleri (Kutudan Taşmayı Önleyen Dinamik Yapı)
    style_sheet = getSampleStyleSheet()
    
    # Alıcı İsmi Stili
    style_alici = ParagraphStyle('alici', parent=style_sheet['Normal'], fontSize=7.5, fontName='Helvetica-Bold', leading=8)
    # Adres Stili (Kutuya göre otomatik satır atlar)
    style_adres = ParagraphStyle('adres', parent=style_sheet['Normal'], fontSize=5.5, fontName='Helvetica', leading=6.5)
    # Ürün Stili
    style_urun = ParagraphStyle('urun', parent=style_sheet['Normal'], fontSize=6, fontName='Helvetica', leading=7)

    for p in etiket_listesi:
        # --- ÜST BÖLÜM (LOGO & GÖNDEREN) ---
        try:
            response = requests.get(logo_url, timeout=5)
            logo_img = ImageReader(io.BytesIO(response.content))
            c.drawImage(logo_img, 1*mm, height - 6.5*mm, width=12*mm, height=5*mm, mask='auto')
        except: pass

        c.setFont("Helvetica-Bold", 4.2)
        c.drawString(14*mm, height - 3*mm, "GONDEREN: NIXRAD / KARPAN DIZAYN A.S.")
        c.setFont("Helvetica", 3.5)
        c.drawString(14*mm, height - 5*mm, "Kavak / SAMSUN - 0262 658 11 58")
        
        c.setLineWidth(0.1)
        c.line(1*mm, height - 7.5*mm, width - 1*mm, height - 7.5*mm)

        # --- ORTA BÖLÜM (ALICI & ADRES) ---
        # Paragraph kullanarak otomatik satır kaydırma (Word Wrap) sağlıyoruz
        alici_ad = tr_clean_for_pdf(musteri_bilgileri.get('AD_SOYAD', 'ALICI BELIRTILMEDI'))
        p_alici = Paragraph(f"ALICI: {alici_ad}", style_alici)
        w, h = p_alici.wrap(width - 4*mm, 10*mm) # Genişlik sınırlaması
        p_alici.drawOn(c, 2*mm, height - 8*mm - h)
        
        last_y = height - 8.5*mm - h
        
        alici_adres = tr_clean_for_pdf(musteri_bilgileri.get('ADRES', 'ADRES GIRILMEDI'))
        p_adres = Paragraph(alici_adres, style_adres)
        aw, ah = p_adres.wrap(width - 4*mm, 12*mm) # Adres genişliği
        p_adres.drawOn(c, 2*mm, last_y - ah)

        # --- ALT BÖLÜM (URUN & DESI) ---
        c.line(1*mm, 8.5*mm, width - 1*mm, 8.5*mm)
        
        c.setFont("Helvetica-Bold", 6)
        c.drawString(2*mm, 6.2*mm, f"TEL: {musteri_bilgileri.get('TELEFON', '')}")
        
        urun_adi = tr_clean_for_pdf(p['kisa_isim'])
        p_urun = Paragraph(f"URUN: {urun_adi}", style_urun)
        uw, uh = p_urun.wrap(35*mm, 6*mm)
        p_urun.drawOn(c, 2*mm, 3.5*mm)

        c.setFont("Helvetica-Bold", 8)
        c.drawString(width - 24*mm, 2.5*mm, f"DESI: {p['desi_val']}")
        
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(width - 2*mm, 5.5*mm, f"{p['sira_no']}/{toplam_etiket_sayisi}")

        c.showPage()
    
    c.save()
    buffer.seek(0)
    return buffer

# =============================================================================
# 3. WEB ARAYÜZÜ (STREAMLIT)
# =============================================================================

st.markdown("""# 📦 NIXRAD Operasyon Paneli""", unsafe_allow_html=True)
st.sidebar.header("Musteri Bilgileri")
ad_soyad = st.sidebar.text_input("Adi Soyadi / Firma Adi")
telefon = st.sidebar.text_input("Telefon Numarasi")
adres = st.sidebar.text_area("Adres")
odeme_tipi = st.sidebar.radio("Odeme Tipi", ["ALICI", "PESIN"], index=0)
musteri_data = {'AD_SOYAD': ad_soyad, 'TELEFON': telefon, 'ADRES': adres, 'ODEME_TIPI': odeme_tipi}

tab_dosya, tab_manuel = st.tabs(["📂 Dosya ile Hesapla", "🧮 Manuel Hesaplayıcı"])

with tab_dosya:
    uploaded_file = st.file_uploader("Excel/CSV Yukleyin", type=['xls', 'xlsx', 'csv'])
    if 'ham_veri' not in st.session_state: st.session_state['ham_veri'] = []

    if uploaded_file:
        if st.button("Dosyayı Analiz Et"):
            try:
                df_raw = pd.read_excel(uploaded_file) if not uploaded_file.name.endswith('.csv') else pd.read_csv(uploaded_file)
                # Basit sütun bulma mantığı
                st.session_state['ham_veri'] = []
                for _, row in df_raw.iterrows():
                    analiz = hesapla_ve_analiz_et(str(row.iloc[0]), 1)
                    if analiz: st.session_state['ham_veri'].append(analiz)
            except Exception as e: st.error(f"Hata: {e}")

    if st.session_state['ham_veri']:
        edited_df = st.data_editor(pd.DataFrame(st.session_state['ham_veri']), use_container_width=True)
        final_etiket_listesi = []
        for i, row in edited_df.iterrows():
            final_etiket_listesi.append({'sira_no': i+1, 'kisa_isim': row['Ürün'], 'desi_val': row['Birim_Desi']})
        
        if st.button("🏷️ TERMAL ETIKETI INDIR"):
            pdf = create_thermal_labels_3x6(final_etiket_listesi, musteri_data, len(final_etiket_listesi))
            st.download_button("Dosyayı Kaydet", pdf, "Nixrad_Etiket.pdf", "application/pdf")
