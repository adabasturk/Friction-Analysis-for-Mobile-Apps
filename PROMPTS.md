# Friction Atlas — Claude Code Prompt'ları (PART 5-8)

Her PART için **yeni bir sohbet** aç. Blokları olduğu gibi yapıştır, birleştirme.
PART 4'ün prompt'u `PLAN.md` içinde duruyor, buraya tekrarlanmadı.

Hepsinde geçerli olan iki kural:
- Claude Code uzun script çalıştırmaz. Yazar, sen kendi terminalinde başlatırsın.
- Her PART bitince: çalıştır, doğrula, `git commit`, sonraki sohbete geç.

---

## PART 5 — Hibrit sorgu katmanı

> Ne zaman yapıştır: `extract.py --frame all` bitmiş, `extractions` tablosu dolu olduğunda.

```
PART 5: Hibrit sorgu katmanı. @PLAN.md ve @CLAUDE.md'yi oku.

src/ask.py yaz. CLI, web arayüzü yok. İki farklı soru tipi var ve tek
mekanizmayla çözülmezler.

YÖNLENDİRİCİ
Gelen soruyu önce küçük bir LLM çağrısıyla sınıflandır: AGGREGATE mi
QUALITATIVE mi. Sadece tek kelime döndürsün, format="json" kullan.
Belirsizse AGGREGATE varsay — sayı sorusuna metin cevabı vermek, metin
sorusuna sayı vermekten daha kötü.

A) AGGREGATE ("kaç tane", "yüzde kaç", "hangi ülkede en çok")
- LLM'e yorum metni VERME. Sadece SQL yazdır.
- Şemayı prompt'a koy, model SELECT üretsin, sen çalıştır, sonucu
  doğal dile çevir.
- Güvenlik: sadece SELECT. INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH
  içeren her şey reddedilir, çalıştırılmadan önce kontrol edilir.
- Üretilen SQL cevabın altında gösterilsin. Bu sızıntı değil, özellik.

  KRİTİK — oran soran her sorgu iki şeyi yapmak zorunda:
  (1) WHERE in_estimation_frame = 1
  (2) selection_weight ile ağırlıklandırma

  Kanonik biçim, prompt'a örnek olarak aynen koy:

    SELECT app,
           SUM(CASE WHEN friction_type != 'none'
                    THEN selection_weight ELSE 0 END)
             / SUM(selection_weight) AS rate,
           COUNT(*) AS n
    FROM extractions
    WHERE in_estimation_frame = 1
    GROUP BY app;

  Üretilen SQL bir oran hesaplıyor ama bu iki şartı taşımıyorsa
  ÇALIŞTIRMA. Modele nedenini söyleyip bir kez tekrar iste. İkinci
  denemede de olmazsa hata ver, sessizce düzeltme.

  Ham sayım sorgularında (kaç yorum toplandı, küme dağılımı) çerçeve
  filtresi gerekmez — onlar 6961 kaydın tamamı üzerinde çalışır.
  Bu ayrımı prompt'ta açıkça yaz.

B) QUALITATIVE ("Brezilyalı kullanıcılar fiyat hakkında ne diyor")
- Embedding aramasıyla en yakın 15 yorumu getir, gemma3:4b
  sentezlesin.
- Arama 6961 embed edilmiş yorumun TAMAMI üzerinde çalışır, sadece
  çıkarılanlar üzerinde değil.
- Her iddianın yanında gerçek review_id dönsün.
- Cevabın altına getirilen 15 kaydın DİL DAĞILIMINI bas. Kümeler dile
  göre oluştuğu için anlamsal arama dil içinde kalma eğiliminde —
  Türkçe sorgu ağırlıklı Türkçe yorum getirir. Bu bilinen bir sınır,
  gizlemek yerine görünür kıl.

C) DÜRÜSTLÜK MEKANİZMASI — bunu atlama, PART 8'de gösterilecek
- Sonuç 5'ten az kayda dayanıyorsa uyar.
- En yakın komşunun benzerlik skoru eşiğin altındaysa tahmin etme,
  "bunu cevaplayacak veri yok" de. Eşiği sabit olarak tanımla ve
  değerini ekrana bas.
- Her cevabın altına "N kayda dayanıyor" satırı.
- Oran cevaplarının altına ayrıca "kestirim çerçevesi, ağırlıklı"
  notu.

Script'i çalıştırma. Yazdıktan sonra bana test komutlarını ver.
```

**Senin işin:** Kırmaya çalış. Şunları sor ve ne olduğunu not et:

```
"Codeway'in CEO'su kim?"                    → veri yok demeli
"Nova'nın paywall şikâyeti oranı nedir?"    → ağırlıklı SQL, çerçeve notu
"kaç yorum topladın?"                        → 9432, çerçeve filtresi olmamalı
"Japon kullanıcılar iptal hakkında ne diyor?" → dil dağılımı JA ağırlıklı çıkmalı
```

Uyduruyorsa C çalışmıyor demektir. Bu oturumun ekran kaydını al — PART 8'e girecek.

---

## PART 6 — Analiz ve hipotez üretimi

> Ne zaman yapıştır: PART 5 çalışıyor, sorgu katmanı doğrulanmış olduğunda.

```
PART 6: Analiz ve hipotez üretimi. @PLAN.md ve @CLAUDE.md'yi oku.

İki script: src/analyze.py ve src/hypotheses.py.

--- src/analyze.py ---

TEMEL KURAL: uydurma metrik yok. Her sayı doğrudan sayılabilir bir
şeyden gelecek. "olgunluk skoru" tipi türetilmiş skor üretme.

1. AĞIRLIKLANDIRMA — tek fonksiyona hapset
   weighted_rate(df, condition) diye TEK bir fonksiyon yaz, her yerde
   onu çağır. Bütün oranlar in_estimation_frame = 1 alt kümesinde ve
   selection_weight ile hesaplanır. Keşif çerçevesi oran ÜRETMEZ,
   sadece alıntı verir. Bu ayrımı kod seviyesinde zorla: keşif
   kayıtları oran fonksiyonuna hiç girmesin.

2. GÜVEN ARALIĞI — tabakalı örneklem formülü, basit binom değil
   Tabakalar uygulama içinde puan bandı (1-2 / 3 / 4-5).

     p_st = Σ W_h · p_h            W_h = N_h / N
     Var  = Σ W_h² · p_h(1-p_h)/n_h · (1 - n_h/N_h)
     %95 GA = p_st ± 1.96 · sqrt(Var)

   Sonlu popülasyon düzeltmesi (1 - n_h/N_h) dahil, atlamayın.
   Her oranın yanında GA döndürülecek.

3. EŞLEŞMİŞ ÇİFT TABLOLARI — uygulamalar tek listede yan yana değil,
   çift içinde karşı karşıya. Çiftler:
     chatbot: Chat AI (Codeway) vs Nova (HubX)
     face:    Retake AI (Codeway) vs ReShoot (HubX)

   Üret:
   - Çift başına friction_type dağılımı (ağırlıklı % + %95 GA + n)
   - Çift başına trigger_moment dağılımı: aynı dikeyde iki stüdyo
     paywall'u farklı anlarda mı gösteriyor?
   - would_pay_signal = "conditional" grubu — en değerli segment
   - price_level vs free_quota_limit ayrı ayrı, ASLA birleştirme.
     Farklı deneylere işaret ederler.
   - paid_but_still_limited = true oranı, çift başına
   - friction_type × yıldız puanı çapraz tablosu. Puan Apple'dan
     gelen gerçek değer, LLM çıktısı değil. Hangi sürtünme 1 yıldız
     üretiyor, hangisi 4 yıldızlık homurdanma?

4. LLM GEREKTİRMEYEN BULGULAR — ayrı bölüm, ayrı başlık
   Bunlar 6961 kaydın TAMAMI üzerinde hesaplanır, örnekleme hatası
   yok. En sağlam sayılar bunlar, raporda önce gelsinler:
   - Küme kompozisyonu: küme 5'in (n=630) uygulama ve ülke dağılımı
   - Puan dağılımları, uygulama başına
   - Yorum hacmi dengesizliği
   - Klavye ezmesi filtresinin düşürdüğü kayıt sayısı

5. ÜLKE KIRILIMI — dikkat
   Kestirim çerçevesi uygulama × puana göre tabakalı, ülkeye göre
   DEĞİL. 600 / 4 uygulama / 8 ülke ≈ hücre başına 19 kayıt.
   Ülke iddialarını sadece en büyük 3-4 pazarda ve çift içinde
   havuzlanmış kur. n < 30 olan her hücreyi çıktıda görünür şekilde
   işaretle (örn. yanına "⚠ n=19" yaz).

6. GRAFİKLER — matplotlib, 4-5 tane, output/charts/
   Sade: ızgara yok, dekoratif renk yok, 3D yok. Her grafik tek bir
   şey söylesin. Her grafikte n değeri ve hata çubuğu (GA) görünsün.
   Tek vurgu rengi + nötr gri, PART 8'deki paletle aynı olacak.

7. Bütün tabloları output/ altına CSV olarak da yaz.

--- src/hypotheses.py ---

analyze.py'ın ürettiği sayıları okuyup gemma3:4b'ye A/B test hipotezi
ürettir. Format:

  Gözlem: [veriden gelen sayı + hangi tablodan geldiği]
  Hipotez: [ne değişirse ne olur]
  Test: [nasıl ölçülür, hangi metrik, hangi süre]
  Risk: [ne ters gidebilir]

KRİTİK: prompt'a SADECE analyze.py'ın hesapladığı gerçek sayıları
geçir. Modelin sayı üretmesine izin verme. Çıktıda prompt'ta geçmeyen
bir sayı varsa o hipotezi "unverified" olarak işaretle.

output/hypotheses.md'ye yaz. 15-20 tane üretsin, eleme bana ait.

Script'leri çalıştırma. Yazdıktan sonra bana komutları ver.
```

**Senin işin:** Hipotezleri kendi filtrenden geçir. Yarısından fazlası genel olacak ("kullanıcı deneyimini iyileştir"). At. **Neyi neden attığını not et** — "AI çıktısının %60'ını eledim, kriterim şuydu" cümlesi, ilandaki "AI çıktısını atmaktan korkmamak" maddesinin doğrudan cevabı.

---

## PART 7 — Değerlendirme katmanı

> Ne zaman yapıştır: PART 6 bitince. Bu adım projeyi "bir sistem kurdum"dan "bir yöntem ölçtüm"e çeviriyor, opsiyonel değil.

```
PART 7: Değerlendirme katmanı. @PLAN.md ve @CLAUDE.md'yi oku.

Bake-off zaten yapıldı (PLAN.md'deki dört model tablosu). Şimdi
ölçeklendiriyoruz.

--- src/sample_for_labeling.py ---

Kestirim çerçevesinden 100 rastgele yorum seç, output/to_label.csv
yaz. Sütunlar: review_id, app, country, rating, body, ve BOŞ bir
true_friction_type sütunu.

KRİTİK: keşif çerçevesinden seçme. O örneklem şikâyete doğru eğimli,
üzerinde ölçülen doğruluk olduğundan yüksek çıkar ve ölçüm
anlamsızlaşır. Sabit seed kullan.

--- src/evaluate.py ---

Ben to_label.csv'yi doldurduktan sonra çalışacak. Aynı test setinde
üç yöntemi kıyasla:
  1. Anahtar kelime eşleşmesi (baseline)
  2. Embedding benzerliğiyle en yakın kategori
  3. LLM çıkarımı (gemma3:4b, extractions tablosundan oku, yeniden
     çalıştırma)

Çıktı:
- Her yöntem için sınıf bazında precision, recall, F1 + destek (n)
- Karışıklık matrisi, her yöntem için
- Genel doğruluk EN SONDA ve tek başına asla raporlanmasın

ÇOĞUNLUK SINIFI KONTROLÜ — bunu açıkça kodla:
Bir yöntem tahminlerinin %60'ından fazlasını tek bir sınıfa veriyorsa
çıktıda uyarı bas. llama3.2:3b bake-off'ta sekiz vakanın altısına
price_level demişti; toplam skoru ortaydı ama hiçbir ayrım
yapmıyordu. Aynı hatayı kendi değerlendirmemde yapmak istemiyorum.

HATA ÖRNEKLERİ:
LLM'in yanıldığı 10 kaydı tam metniyle, gerçek etiket ve tahminle
birlikte output/errors.md'ye yaz. Bu bölüm, LLM'i kazanan ilan
etmekten daha değerli.

Sonuçları output/evaluation.md'ye yaz.

Script'leri çalıştırma. Yazdıktan sonra bana komutları ver.
```

**Senin işin:** 100 yorumu elle etiketle. Yaklaşık bir saat, sıkıcı. Ama o saat projenin en savunulabilir parçasını üretiyor — RAG demosu herkeste var, ölçüm kimsede yok.

---

## PART 8 — Yayın

> Ne zaman yapıştır: PART 6 ve 7 çıktıları hazır olduğunda.

```
PART 8: Statik site. @PLAN.md'yi oku.

site/index.html — tek sayfa, vanilla HTML/CSS. React, Next.js,
Tailwind, Bootstrap YOK. Framework kurma.

YAPI — dört bölüm, bu sırayla:
1. Yöntem — eşleşmiş çift tasarımı neden, iki çerçeveli örnekleme
   neden, model bake-off tablosu (dört model, iki hata biçimi dahil)
2. Bulgular — output/charts/ görselleri gömülü, her birinin altında
   tek cümlelik okuma
3. Hipotezler — kart halinde: Gözlem → Hipotez → Test → Risk
4. Sınırlılıklar — GÖMÜLMEYECEK, görünür yerde duracak

SINIRLILIKLAR bölümü şunları içerecek, yumuşatmadan:
- Kontrol uygulaması yok; "bu oyun kitabı AI dalgasından eski mi"
  sorusu bu veriyle cevaplanamaz
- Kestirim çerçevesi uygulama başına 150 kayıt; 12 puandan küçük
  farklar istatistiksel olarak anlamlı değil
- Kümeler konuya değil dile göre oluştu; anlamsal arama dil içinde
  kalma eğiliminde
- App Store RSS uygulama-ülke başına ~500 yorumla sınırlı, örneklem
  güncel yorumlara eğimli
- LLM çıkarımının ölçülen doğruluğu: [PART 7 sayısı buraya]

SOHBET KATMANI canlı değil. Terminal oturumunun GIF'i + 4 örnek
soru-cevap statik olarak gömülü. "Codeway'in CEO'su kim?" sorusuna
verilen "veri yok" cevabı mutlaka olsun — dürüstlük mekanizmasının
kanıtı o.

TASARIM — başvurulan rol görsel yargı istiyor, şablon gibi durmasın:
- Tek güçlü tipografik karar, en fazla iki font
- Dar palet: bir nötr zemin, bir vurgu rengi. Grafiklerdeki paletle
  AYNI olacak.
- Cömert boşluk, geniş satır yüksekliği, uzun okuma için ölçülmüş
  satır uzunluğu (65-75 karakter)
- Mobilde bozulmasın ama mobile-first tasarlama — bu bir okuma
  sayfası, uygulama değil
- Animasyon, gradyan, glassmorphism, emoji, ikon seti YOK

Vercel'e deploy edilecek, build adımı olmayacak. Tek HTML + tek CSS
+ görseller.
```

**Senin işin:** En güçlü üç hipotezin için Figma'da paywall varyantı mockup'la ve sayfaya koy. Bir saatlik iş ama "analiz etti" ile "ne yapılacağını gösterdi" arasındaki farkı tam olarak bu yaratıyor.

---

## Sıra ve süre

| Part | Yapıştırma sırası | Kod süresi | Senin süren |
|---|---|---|---|
| 5 | PART 4 koşusu bitince | 3-4 saat | kırma testleri, ~30 dk |
| 6 | PART 5 doğrulanınca | 2 saat | hipotez eleme, ~1 saat |
| 7 | PART 6 bitince | 1 saat | 100 etiket, ~1 saat |
| 8 | 6 ve 7 hazır olunca | 4-5 saat | Figma mockup, ~1 saat |

PART 7'yi atlama isteği gelirse: atlarsan elinde çalışan bir demo olur, ölçülmüş bir yöntem olmaz. İkisi arasındaki fark, mülakatta sorulacak ilk soru.
