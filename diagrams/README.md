# Diagrammalar

Bu papkadagi fayllar loyihaning arxitekturasini vizual tasvirlash uchun yaratilgan
bir martalik skriptlar va ularning natijalari. **Ishlab chiqarish dasturiga (main.py)
hech qanday aloqasi yo'q** — hech biri import qilinmaydi, faqat qo'lda ishga tushiriladi.

- `generate_flowchart_image.py`, `render_toliq_miya_sxemasi.py`, `render_5_miya_sxemasi.py` —
  PNG sxema rasmini chizib beruvchi skriptlar (Pillow orqali).
- `*.png`, `*.svg`, `*.mmd` — shu skriptlar natijasida hosil bo'lgan tayyor rasmlar/diagrammalar.
- `*.html` — brauzerda ko'rish/yuklab olish uchun sahifalar.

Skriptlarni qayta ishga tushirsangiz, shu papka ichidan (`cd diagrams && python generate_flowchart_image.py`)
bajaring — chiqish fayli manzillari shu katalogga nisbatan yozilgan.
