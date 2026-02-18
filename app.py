import io
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

# Türkçe karakter düzeltme fonksiyonu (Eğer kodunda zaten varsa bunu kopyalama)
def tr_clean_for_pdf(text):
    if not isinstance(text, str): return str(text)
    mapping = {'ğ': 'g', 'Ğ': 'G', 'ş': 's', 'Ş': 'S', 'ı': 'i', 'İ': 'I', 'ç': 'c', 'Ç': 'C', 'ö': 'o', 'Ö': 'O', 'ü': 'u', 'Ü': 'U'}
    for k, v in mapping.items(): text = text.replace(k, v)
    return text

# --- İSTEDİĞİN 3x6 TERMAL ETİKET FONKSİYONU ---
def create_thermal_labels_3x6(etiket_listesi, musteri_bilgileri, toplam_etiket_sayisi):
    buffer = io.BytesIO()
    # 60mm Genişlik x 30mm Yükseklik
    width, height = 60*mm, 30*mm
    c = canvas.Canvas(buffer, pagesize=(width, height))
    
    # Logo URL
    logo_url = "https://static.ticimax.cloud/74661/Uploads/HeaderTasarim/Header1/b2d2993a-93a3-4b7f-86be-cd5911e270b6.jpg"

    for p in etiket_listesi:
        # 1. Logo Çizimi (Sol Üst)
        try:
            # Her etikette tekrar indirmemek için cache mantığı eklenebilir ama basitlik için böyle bıraktım
            response = requests.get(logo_url)
            logo_img = ImageReader(io.BytesIO(response.content))
            # Logoyu biraz daha sola ve yukarı hizaladık
            c.drawImage(logo_img, 1*mm, height - 7.5*mm, width=12*mm, height=6*mm, mask='auto')
        except:
            pass

        # Veri Hazırlığı
        no_str = f"{p['sira_no']}/{toplam_etiket_sayisi}"
        alici_ad = tr_clean_for_pdf(musteri_bilgileri.get('AD_SOYAD', 'MUSTERI ADI'))
        alici_adres = tr_clean_for_pdf(musteri_bilgileri.get('ADRES', 'ADRES GIRILMEDI'))
        alici_tel = musteri_bilgileri.get('TELEFON', 'TELEFON YOK')
        urun_adi = tr_clean_for_pdf(p['kisa_isim'])
        desi_text = f"DESI : {p['desi_val']}"

        # 2. Gönderen Bilgileri (Sağ Üst)
        c.setFont("Helvetica-Bold", 4.5)
        c.drawString(14*mm, height - 3*mm, "GONDEREN FIRMA: NIXRAD / KARPAN DIZAYN A.S.")
        c.setFont("Helvetica", 3.5)
        c.drawString(14*mm, height - 5*mm, "Yeni Cami OSB Mah. 3.Cad. No:1 Kavak/SAMSUN Tel: 0262 658 11 58")
        
        # Çizgi 1
        c.setLineWidth(0.15)
        c.line(1*mm, height - 8*mm, width - 1*mm, height - 8*mm)
        
        # 3. Alıcı Adı
        c.setFont("Helvetica-Bold", 6)
        c.drawString(2*mm, height - 10.5*mm, f"ALICI MUSTERI: {alici_ad}")
        c.line(1*mm, height - 11.5*mm, width - 1*mm, height - 11.5*mm)
        
        # 4. Adres (Uzunsa iki satır)
        c.setFont("Helvetica-Bold", 5)
        addr_y = height - 14*mm
        if len(alici_adres) > 60:
            c.drawString(2*mm, addr_y, f"ADRES :{alici_adres[:60]}")
            c.drawString(2*mm, addr_y - 2.5*mm, alici_adres[60:120])
        else:
            c.drawString(2*mm, addr_y, f"ADRES :{alici_adres}")
        
        c.line(1*mm, height - 18.5*mm, width - 1*mm, height - 18.5*mm)
        
        # 5. Telefon
        c.setFont("Helvetica-Bold", 6)
        c.drawString(2*mm, height - 21*mm, f"TEL : {alici_tel}")
        c.line(1*mm, height - 22*mm, width - 1*mm, height - 22*mm)
        
        # 6. Ürün Adı ve Desi
        c.setFont("Helvetica-Bold", 7)
        c.drawString(2*mm, height - 25.5*mm, urun_adi)
        
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(2*mm, height - 28.5*mm, desi_text)
        
        # 7. Etiket Sıra No (SAĞ EN ALT KÖŞE)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(width - 2*mm, height - 28.5*mm, no_str)
        
        c.showPage() # Sayfayı bitir (Etiketi kes)
    
    c.save()
    buffer.seek(0)
    return buffer
