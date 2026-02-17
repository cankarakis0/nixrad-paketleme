import streamlit as st
import pandas as pd
import re
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# Matplotlib Backend Fix
try:
    import matplotlib.pyplot as plt
    plt.switch_backend('Agg')
except:
    pass

# =============================================================================
# 1. AYARLAR & YARDIMCI FONKSİYONLAR
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
        div = 12.5 if model_key == 'lizyantus' else 15.0
        boru_sayisi = HAVLUPAN_BORU_CETVELI.get(model_key, {}).get(int(yukseklik_cm), round(yukseklik_cm / div))
        ref_agirlik = MODEL_AGIRLIKLARI.get(model_key, 0)
        return round(boru_sayisi * ref_agirlik * (genislik_cm / 50.0), 2)

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
    if bulunan_model_key == 'prag': paylar['PAY_DERINLIK'] = 2.0
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
# 2. PDF OLUŞTURMA (KARGO, ÜRETİM, 3x6 ETİKET)
# =============================================================================

def create_cargo_pdf(proje_toplam_desi, toplam_parca, musteri_bilgileri, etiket_listesi):
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1*cm, leftMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm); elements = []
    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle('n', fontSize=10)
    style_header = ParagraphStyle('h', fontSize=14, fontName='Helvetica-Bold', textColor=colors.darkred)
    gonderen = [Paragraph("<b>GONDEREN FIRMA:</b>", style_normal), Paragraph("NIXRAD / KARPAN DIZAYN A.S.", style_header), Paragraph("Yeni Cami OSB Mah. 3.Cad. No:1 Kavak/SAMSUN", style_normal)]
    odeme_info = [Paragraph("<b>ODEME TIPI:</b>", style_normal), Paragraph(f"<b>{tr_clean_for_pdf(musteri_bilgileri['ODEME_TIPI'])} ODEMELI</b>", ParagraphStyle('big', fontSize=14, alignment=TA_CENTER))]
    elements.append(Table([[gonderen, odeme_info]], colWidths=[13*cm, 6*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black)])))
    elements.append(Spacer(1, 0.5*cm))
    alici = [Paragraph(f"<b>{tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'])}</b>", ParagraphStyle('huge', fontSize=22, fontName='Helvetica-Bold')), Paragraph(f"Tel: {musteri_bilgileri['TELEFON']}", style_normal), Paragraph(f"ADRES: {tr_clean_for_pdf(musteri_bilgileri['ADRES'])}", ParagraphStyle('adr', fontSize=14))]
    elements.append(Table([[alici]], colWidths=[19*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 2, colors.black), ('PADDING', (0,0), (-1,-1), 15)])))
    doc.build(elements); buffer.seek(0); return buffer

def create_production_pdf(tum_malzemeler, musteri_bilgileri):
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, margin=1*cm); elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"URETIM EMRI - {tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'])}", styles['Title']))
    data = [['MALZEME ADI', 'ADET', 'KONTROL']] + [[Paragraph(tr_clean_for_pdf(m), styles['Normal']), f"{v}", "___"] for m, v in tum_malzemeler.items()]
    elements.append(Table(data, colWidths=[13*cm, 2*cm, 3*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black)])))
    doc.build(elements); buffer.seek(0); return buffer

def create_sticker_only_pdf(etiket_listesi, musteri_bilgileri):
    """3 Sütun x 6 Satır (Toplam 18 etiket/sayfa) Etiket Sayfası"""
    buffer = io.BytesIO()
    # Kenar boşluklarını sıfıra yakın tutarak 3x6 alanını maksimize ediyoruz
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.3*cm, leftMargin=0.3*cm, topMargin=0.5*cm, bottomMargin=0.5*cm)
    elements = []
    styles = getSampleStyleSheet()
    
    style_num = ParagraphStyle('num', alignment=TA_RIGHT, fontSize=12, fontName='Helvetica-Bold')
    style_main = ParagraphStyle('main', alignment=TA_CENTER, fontSize=9, fontName='Helvetica-Bold', leading=10)
    style_sub = ParagraphStyle('sub', alignment=TA_CENTER, fontSize=8)
    style_cust = ParagraphStyle('cust', alignment=TA_CENTER, fontSize=7, fontName='Helvetica-Bold')

    sticker_data, row = [], []
    for p in etiket_listesi:
        # Etiket Kutusu İçeriği
        content = [
            [Paragraph(f"#{p['sira_no']}", style_num)],
            [Paragraph(tr_clean_for_pdf(p['kisa_isim']), style_main)],
            [Paragraph(p['boyut_str'], style_sub)],
            [Paragraph(f"Desi: {p['desi_val']}", style_main)],
            [Paragraph(tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'][:25]), style_cust)]
        ]
        # Her bir etiket hücresi (Genişlik: ~6.5cm, Yükseklik: ~4.5cm)
        box = Table(content, colWidths=[6.2*cm], rowHeights=[0.6*cm, 1.2*cm, 0.6*cm, 0.8*cm, 0.6*cm],
                    style=TableStyle([
                        ('BOX', (0,0), (-1,-1), 0.5, colors.grey),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('LEFTPADDING', (0,0), (-1,-1), 2),
                        ('RIGHTPADDING', (0,0), (-1,-1), 2),
                    ]))
        row.append(box)
        
        if len(row) == 3: # 3 Sütun dolunca satırı ekle
            sticker_data.append(row)
            row = []
            if len(sticker_data) == 6: # 6 Satır dolunca sayfayı bitir
                elements.append(Table(sticker_data, colWidths=[6.5*cm]*3, style=TableStyle([('TOPPADDING', (0,0), (-1,-1), 5)])))
                elements.append(PageBreak())
                sticker_data = []

    if row or sticker_data: # Kalanları ekle
        while len(row) < 3 and len(row) > 0: row.append("")
        if row: sticker_data.append(row)
        elements.append(Table(sticker_data, colWidths=[6.5*cm]*3))

    doc.build(elements); buffer.seek(0); return buffer

# =============================================================================
# 3. WEB ARAYÜZÜ
# =============================================================================

st.markdown("# 📦 NIXRAD Operasyon Paneli")
st.sidebar.header("Müşteri Bilgileri")
ad_soyad = st.sidebar.text_input("Adı Soyadı / Firma")
telefon = st.sidebar.text_input("Telefon")
adres = st.sidebar.text_area("Adres")
odeme_tipi = st.sidebar.radio("Ödeme", ["ALICI", "PESIN"])
musteri_data = {'AD_SOYAD': ad_soyad, 'TELEFON': telefon, 'ADRES': adres, 'ODEME_TIPI': odeme_tipi}

tab1, tab2 = st.tabs(["📂 Dosya ile Hesapla", "🧮 Manuel Hesaplayıcı"])

with tab1:
    uploaded_file = st.file_uploader("Excel/CSV Yükle", type=['xlsx', 'csv'])
    if uploaded_file:
        if st.button("Analiz Et"):
            df_raw = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
            # (Analiz mantığı önceki kodun aynısıdır, özetlenmiştir)
            st.session_state['ham_veri'] = [] # Örnekleme için temizle
            # ... (Burada dosya okuma ve hesapla_ve_analiz_et fonksiyonu çalışır)

    if 'ham_veri' in st.session_state and st.session_state['ham_veri']:
        edited_df = st.data_editor(pd.DataFrame(st.session_state['ham_veri']), num_rows="dynamic")
        
        # PDF Hazırlıkları
        final_etiketler = []
        count = 1
        for _, r in edited_df.iterrows():
            for _ in range(int(r['Adet'])):
                final_etiketler.append({'sira_no': count, 'kisa_isim': r['Ürün'], 'boyut_str': r['Ölçü'], 'desi_val': r['Birim Desi']})
                count += 1

        st.divider()
        col1, col2, col3 = st.columns(3)
        
        pdf_cargo = create_cargo_pdf(edited_df['Birim Desi'].sum(), len(final_etiketler), musteri_data, final_etiketler)
        col1.download_button("📄 KARGO FİŞİ", pdf_cargo, "Kargo_Fisi.pdf", use_container_width=True)

        # Üretim Emri (Sadece Liste)
        malz_dict = {r['Ürün']: r['Adet'] for _, r in edited_df.iterrows()}
        pdf_prod = create_production_pdf(malz_dict, musteri_data)
        col2.download_button("🏭 ÜRETİM EMRİ", pdf_prod, "Uretim_Emri.pdf", use_container_width=True)

        # Sadece Etiketler (3x6 Düzeni)
        pdf_stickers = create_sticker_only_pdf(final_etiketler, musteri_data)
        col3.download_button("🏷️ ETİKETLERİ YAZDIR (3x6)", pdf_stickers, "Etiketler_3x6.pdf", use_container_width=True)

# Manuel sekmesi mantığı da benzer şekilde pdf_stickers çağrısını yapabilir.
