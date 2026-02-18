import streamlit as st
import pandas as pd
import re
import io
import requests # Logoyu linkten çekmek için eklendi
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
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
LOGO_URL = "https://static.ticimax.cloud/74661/Uploads/HeaderTasarim/Header1/b2d2993a-93a3-4b7f-86be-cd5911e270b6.jpg"

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
# PDF FONKSİYONLARI (SIĞDIRILMIŞ VE LOGOLU)
# =============================================================================

def create_thermal_labels_3x6(etiket_listesi, musteri_bilgileri, toplam_etiket_sayisi):
    buffer = io.BytesIO()
    width, height = 60*mm, 30*mm
    c = canvas.Canvas(buffer, pagesize=(width, height))
    try:
        resp = requests.get(LOGO_URL); logo_img = ImageReader(io.BytesIO(resp.content))
    except: logo_img = None

    for p in etiket_listesi:
        if logo_img: c.drawImage(logo_img, 1*mm, height - 7.5*mm, width=12*mm, height=6*mm, mask='auto')
        no_str = f"{p['sira_no']}/{toplam_etiket_sayisi}"
        alici_ad = tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'] or "MUSTERI ADI")
        alici_adres = tr_clean_for_pdf(musteri_bilgileri['ADRES'] or "ADRES GIRILMEDI")
        alici_tel = musteri_bilgileri['TELEFON'] or "TELEFON YOK"
        urun_adi = tr_clean_for_pdf(p['kisa_isim'])
        desi_text = f"DESI : {p['desi_val']}"

        c.setFont("Helvetica-Bold", 4.5)
        c.drawString(14*mm, height - 3*mm, "GONDEREN FIRMA: NIXRAD / KARPAN DIZAYN A.S.")
        c.setFont("Helvetica", 3.5)
        c.drawString(14*mm, height - 5*mm, "Yeni Cami OSB Mah. 3.Cad. No:1 Kavak/SAMSUN Tel: 0262 658 11 58")
        
        c.setLineWidth(0.15); c.line(1*mm, height - 8*mm, width - 1*mm, height - 8*mm)
        c.setFont("Helvetica-Bold", 6); c.drawString(2*mm, height - 10.5*mm, f"ALICI MUSTERI: {alici_ad}")
        c.line(1*mm, height - 11.5*mm, width - 1*mm, height - 11.5*mm)
        
        c.setFont("Helvetica-Bold", 5); addr_y = height - 14*mm
        if len(alici_adres) > 60:
            c.drawString(2*mm, addr_y, f"ADRES :{alici_adres[:60]}"); c.drawString(2*mm, addr_y - 2.5*mm, alici_adres[60:120])
        else: c.drawString(2*mm, addr_y, f"ADRES :{alici_adres}")
        
        c.line(1*mm, height - 18.5*mm, width - 1*mm, height - 18.5*mm)
        c.setFont("Helvetica-Bold", 6); c.drawString(2*mm, height - 21*mm, f"TEL : {alici_tel}")
        c.line(1*mm, height - 22*mm, width - 1*mm, height - 22*mm)
        
        c.setFont("Helvetica-Bold", 7); c.drawString(2*mm, height - 25.5*mm, urun_adi)
        c.setFont("Helvetica-Bold", 6.5); c.drawString(2*mm, height - 28.5*mm, desi_text)
        c.setFont("Helvetica-Bold", 9); c.drawRightString(width - 2*mm, height - 28.5*mm, no_str)
        c.showPage()
    c.save(); buffer.seek(0); return buffer

def create_cargo_pdf(proje_toplam_desi, toplam_parca, musteri_bilgileri, ham_tablo_verisi):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1*cm, leftMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm)
    elements = []
    styles = getSampleStyleSheet()
    
    try:
        resp = requests.get(LOGO_URL); img_data = io.BytesIO(resp.content)
        logo = Image(img_data, width=4*cm, height=2*cm); elements.append(logo); elements.append(Spacer(1, 0.2*cm))
    except: pass

    gonderen_info = [Paragraph("<b>GONDEREN FIRMA:</b>", styles['Normal']), Paragraph("NIXRAD / KARPAN DIZAYN A.S.", ParagraphStyle('h', fontSize=14, fontName='Helvetica-Bold', textColor=colors.darkred)), Paragraph("Yeni Cami OSB Mah. 3.Cad. No:1 Kavak/SAMSUN Tel: 0262 658 11 58", styles['Normal'])]
    odeme_info = [Paragraph("<b>ODEME TIPI:</b>", styles['Normal']), Spacer(1, 0.5*cm), Paragraph(f"<b>{tr_clean_for_pdf(musteri_bilgileri.get('ODEME_TIPI', 'ALICI'))} ODEMELI</b>", ParagraphStyle('big', fontSize=14, alignment=TA_CENTER, fontName='Helvetica-Bold'))]
    t_header = Table([[gonderen_info, odeme_info]], colWidths=[13*cm, 6*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 1, colors.black), ('GRID', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'TOP'), ('BACKGROUND', (0,0), (-1,-1), colors.whitesmoke)]))
    elements.append(t_header); elements.append(Spacer(1, 0.5*cm))

    alici_content = [Paragraph(f"<b>ALICI MUSTERI: {tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'] or '.....')}</b>", ParagraphStyle('huge', fontSize=20, fontName='Helvetica-Bold')), Paragraph(f"<b>Tel:</b> {musteri_bilgileri['TELEFON'] or '.....'}", styles['Normal']), Spacer(1, 0.5*cm), Paragraph(f"<b>ADRES:</b><br/>{tr_clean_for_pdf(musteri_bilgileri['ADRES'] or 'Adres Girilmedi')}", ParagraphStyle('adr', fontSize=14, leading=18))]
    elements.append(Table([[alici_content]], colWidths=[19*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 2, colors.black), ('PADDING', (0,0), (-1,-1), 10)]))); elements.append(Spacer(1, 0.5*cm))

    pkt_data = [['Urun Adi', 'Adet', 'Olcu', 'Desi']] + [[tr_clean_for_pdf(r['Ürün']), str(r['Adet']), r['Ölçü'], str(r['Birim_Desi'])] for r in ham_tablo_verisi]
    t_pkt = Table(pkt_data, colWidths=[10*cm, 2*cm, 5*cm, 2*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('ALIGN', (1,0), (1,0), 'CENTER')]))
    elements.append(t_pkt); elements.append(Spacer(1, 0.5*cm))

    summary_data = [[f"TOPLAM KOLI: {int(toplam_parca)}", f"TOPLAM DESI: {proje_toplam_desi:.2f}"]]
    elements.append(Table(summary_data, colWidths=[9.5*cm, 9.5*cm], style=TableStyle([('ALIGN', (1,0), (1,0), 'RIGHT'), ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 14), ('TEXTCOLOR', (1,0), (1,0), colors.black), ('LINEBELOW', (0,0), (-1,-1), 2, colors.black)]))); elements.append(Spacer(1, 1*cm))
    
    warning = Table([[Paragraph("<b>DIKKAT KIRILIR !</b>", ParagraphStyle('WT', fontSize=24, alignment=TA_CENTER, textColor=colors.white, fontName='Helvetica-Bold'))], [Paragraph("SAYIN MUSTERIMIZ, PAKETLERI KONTROL EDEREK ALINIZ. HASAR VARSA KARGOYA TUTANAK TUTTURUNUZ.", ParagraphStyle('warn', alignment=TA_CENTER, textColor=colors.white, fontSize=10, fontName='Helvetica-Bold'))]], colWidths=[19*cm], style=TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.black), ('PADDING', (0,0), (-1,-1), 10)]))
    elements.append(warning); doc.build(elements); buffer.seek(0); return buffer

def create_production_pdf(tum_malzemeler, etiket_listesi, musteri_bilgileri):
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=0.5*cm, leftMargin=0.5*cm, topMargin=1*cm, bottomMargin=1*cm); elements = []
    elements.append(Paragraph(f"URETIM & PAKETLEME EMRI - {tr_clean_for_pdf(musteri_bilgileri['AD_SOYAD'] or 'Isim Girilmedi')}", ParagraphStyle('T', fontSize=16, alignment=TA_CENTER, fontName='Helvetica-Bold')))
    data = [['MALZEME ADI', 'ADET', 'KONTROL']] + [[Paragraph(tr_clean_for_pdf(m), ParagraphStyle('m', fontSize=10)), f"{int(v)}" if v%1==0 else f"{v:.1f}", "___"] for m, v in tum_malzemeler.items()]
    elements.append(Table(data, colWidths=[14*cm, 2*cm, 3*cm], style=TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))); elements.append(Spacer(1, 1*cm))
    sticker_data, row = [], []
    for p in etiket_listesi:
        box = Table([[Paragraph(f"<b>#{p['sira_no']}</b>", ParagraphStyle('n', alignment=TA_RIGHT, fontSize=12, fontName='Helvetica-Bold'))], [Paragraph(f"<b>{tr_clean_for_pdf(p['kisa_isim'])}</b>", ParagraphStyle('C', alignment=TA_CENTER, fontSize=9))], [Paragraph(f"{p['boyut_str']}", ParagraphStyle('C', alignment=TA_CENTER, fontSize=8))], [Spacer(1, 0.2*cm)], [Paragraph(f"<b>Desi: {p['desi_val']}</b>", ParagraphStyle('L', alignment=TA_LEFT, fontSize=10))], [Paragraph(f"<b>{tr_clean_for_pdf((musteri_bilgileri['AD_SOYAD'] or '')[:20])}</b>", ParagraphStyle('cb', alignment=TA_CENTER, fontSize=9, fontName='Helvetica-Bold'))]], colWidths=[5.8*cm], rowHeights=[0.8*cm, 1*cm, 0.5*cm, 0.4*cm, 0.8*cm, 0.5*cm], style=TableStyle([('BOX', (0,0), (-1,-1), 1, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        row.append(box)
        if len(row)==3: sticker_data.append(row); row = []
    if row: row.extend([""] * (3 - len(row))); sticker_data.append(row)
    elements.append(Table(sticker_data, colWidths=[6.5*cm]*3, style=TableStyle([('BOTTOMPADDING', (0,0), (-1,-1), 15)]))); doc.build(elements); buffer.seek(0); return buffer

# =============================================================================
# 3. WEB ARAYÜZÜ (ORİJİNAL AKIŞ)
# =============================================================================

st.markdown("""# 📦 NIXRAD Operasyon Paneli \n ### by [NETMAKER](https://netmaker.com.tr/)""", unsafe_allow_html=True)
st.sidebar.header("Musteri Bilgileri")
ad_soyad = st.sidebar.text_input("Adi Soyadi / Firma Adi")
telefon = st.sidebar.text_input("Telefon Numarasi")
adres = st.sidebar.text_area("Adres (Enter ile alt satira gecebilirsiniz)")
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
                df = df_raw[h_idx + 1:].copy(); df.columns = [str(col).strip() for col in new_h]
                try: df = df[['Stok Adı', 'Miktar']]
                except: df = df.iloc[:, [0, 2]]; df.columns = ['Stok Adı', 'Miktar']
                st.session_state['ham_veri'], st.session_state['malzeme_listesi'] = [], {}
                for _, row in df.dropna(subset=['Stok Adı']).iterrows():
                    adet = float(row['Miktar'])
                    if adet > 0:
                        stok_l = tr_lower(str(row['Stok Adı']))
                        if ('vana' in stok_l and 'nirvana' not in stok_l) or any(x in stok_l for x in ['volan', 'tapa', 'aksesuar', 'set']):
                            st.session_state['malzeme_listesi'][f"{row['Stok Adı']} (Adet)"] = st.session_state['malzeme_listesi'].get(f"{row['Stok Adı']} (Adet)", 0) + adet
                        elif any(x in stok_l for x in ['radyatör', 'havlupan', 'radyator']):
                            analiz = hesapla_ve_analiz_et(str(row['Stok Adı']), adet)
                            if analiz:
                                for m, b, a in analiz['Reçete']: st.session_state['malzeme_listesi'][f"{a} ({b})"] = st.session_state['malzeme_listesi'].get(f"{a} ({b})", 0) + (m * adet)
                                st.session_state['ham_veri'].append(analiz)
        except Exception as e: st.error(f"Hata: {e}")

    if st.session_state['ham_veri']:
        st.divider(); ozet_alani = st.container()
        edited_df = st.data_editor(pd.DataFrame(st.session_state['ham_veri'])[["Ürün", "Adet", "Ölçü", "Birim_Desi", "Toplam_Agirlik_Gosterim"]], num_rows="dynamic", use_container_width=True)
        toplam_parca, p_desi = edited_df["Adet"].sum(), (edited_df["Birim_Desi"] * edited_df["Adet"]).sum()
        with ozet_alani:
            st.subheader("📊 Proje Özeti")
            c1, c2, c3 = st.columns(3); c1.metric("📦 Toplam Koli", int(toplam_parca)); c2.metric("📐 Toplam Desi", f"{p_desi:.2f}"); st.code(f"toplam desi {p_desi:.2f}")
        
        final_malz = dict(zip(st.data_editor(pd.DataFrame([{"Malzeme": k, "Adet": v} for k,v in st.session_state['malzeme_listesi'].items()]))['Malzeme'], st.session_state['malzeme_listesi'].values()))
        final_etiket = []
        for _, row in edited_df.iterrows():
            for _ in range(int(row['Adet'])): final_etiket.append({'sira_no': len(final_etiket)+1, 'kisa_isim': row['Ürün'], 'boyut_str': row['Ölçü'], 'desi_val': row['Birim_Desi']})

        st.divider(); col1, col2, col3 = st.columns(3)
        col1.download_button("📄 KARGO FISI", create_cargo_pdf(p_desi, toplam_parca, musteri_data, edited_df.to_dict('records')), "Kargo.pdf", "application/pdf", use_container_width=True)
        col2.download_button("🏭 URETIM FIŞİ", create_production_pdf(final_malz, final_etiket, musteri_data), "Uretim.pdf", "application/pdf", use_container_width=True)
        col3.download_button("🏷️ TERMAL ETİKET (3x6)", create_thermal_labels_3x6(final_etiket, musteri_data, len(final_etiket)), "Termal.pdf", "application/pdf", use_container_width=True)

with tab_manuel:
    st.header("🧮 Hızlı Hesaplayıcı")
    if 'manuel_liste' not in st.session_state: st.session_state['manuel_liste'] = []
    cm1, cm2, cm3, cm4 = st.columns(4)
    with cm1: model = st.selectbox("Model", ["Standart", "Havlupan"] + [m.capitalize() for m in MODEL_DERINLIKLERI.keys() if m != 'livera'])
    with cm2: v1 = st.number_input("Boy1", min_value=10, value=60)
    with cm3: v2 = st.number_input("Boy2", min_value=10, value=100)
    with cm4: m_adet = st.number_input("Adet", min_value=1, value=1)
    if st.button("Ekle", type="primary"):
        is_h = 'havlupan' in model.lower() or any(z in model.lower() for z in ZORUNLU_HAVLUPANLAR)
        g, y = (v1, v2) if is_h else (v2, v1)
        bd, bs, bk = manuel_hesapla(model, g, y, m_adet)
        st.session_state['manuel_liste'].append({"Ürün": model, "Adet": m_adet, "Ölçü": bs, "Birim_Desi": bd, "Toplam Desi": round(bd*m_adet, 2)})
    if st.session_state['manuel_liste']:
        df_m = pd.DataFrame(st.session_state['manuel_liste']); st.dataframe(df_m, use_container_width=True)
        m_etiket = []
        for r in st.session_state['manuel_liste']:
            for _ in range(r['Adet']): m_etiket.append({'sira_no': len(m_etiket)+1, 'kisa_isim': r['Ürün'], 'boyut_str': r['Ölçü'], 'desi_val': r['Birim_Desi']})
        st.download_button("🏷️ TERMAL ETİKET BAS", create_thermal_labels_3x6(m_etiket, musteri_data, len(m_etiket)), "Manuel_Termal.pdf", use_container_width=True)
        if st.button("🗑️ Temizle"): st.session_state['manuel_liste'] = []; st.rerun()
