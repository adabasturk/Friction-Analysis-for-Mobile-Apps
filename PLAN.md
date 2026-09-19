# Friction Atlas — Proje Planı

**Ne bu:** İki Türk AI uygulama stüdyosunu (Codeway, HubX) aynı dikeyler içinde **eşleşmiş çiftler** olarak karşılaştıran, App Store yorumlarından dönüşüm sürtünmesini (paywall, fiyat, onboarding) ölçen ve test edilebilir hipotezler üreten bir sistem. Yapılandırılmış çıkarım yerel LLM'de çalışır.

**Neden eşleşmiş çift:** Rastgele popüler uygulamaları kıyaslarsan farkın stüdyodan mı kategoriden mi geldiğini ayıramazsın. Dikeyi sabit tutunca geriye kalan fark stüdyonun para kazanma kararıdır. Betimleme yerine çıkarım üretmenin tek yolu bu.

**Neden bu proje:** Growth Product Specialist başvuruları için portföy parçası. Çıktı bir dashboard değil, hipotez listesi.

**Donanım:** MacBook Pro 13" 2020, Intel i5 1.4 GHz, 8 GB RAM, GPU yok, macOS Sonoma 14.6. Bunu kısıt değil tasarım parametresi say.

**Araç:** Claude Code. Kurallar `CLAUDE.md`'de. Bu dosya (`PLAN.md`) adım adım ne yapılacağını tutar.

---

## Kapsam — kesinleşmiş hali

Eski planda üç çift artı iki kontrol uygulaması vardı. Fiilen kurulan set iki çift:

| Dikey | Codeway | HubX |
|---|---|---|
| AI chatbot | Chat AI (1668787639) | Nova (1669007652) |
| Yüz / portre düzenleme | Retake AI (6466298983) | ReShoot (6751296351) |

**Ülkeler:** us, gb, de, tr, br, in, fr, jp

Kontrol uygulaması (CleanUp, PlantApp) **yok**. Bunun yazıya doğrudan sonucu var: "bu oyun kitabı AI dalgasından eski mi" sorusunu bu veriyle cevaplayamazsın. PART 8'de o iddiayı kurma. Sınırlılıklar bölümüne bir cümleyle yaz, kapat.

`config/apps.json` bir config dosyası. Başka bir şirkete yönelmek için uygulamalarını ekleyip pipeline'ı tekrar çalıştırmak yeter. Wowoo için ChatPrime, FaceForm, Render AI, Plant AI eklenir — dördü de yukarıdaki dikeylere oturuyor.

---

## Durum — nerede kaldık

| Aşama | Durum | Sonuç |
|---|---|---|
| PART 0 — İskelet | Bitti | — |
| PART 1 — Toplama | Bitti | 9.432 yorum |
| PART 2 — DB | Bitti | `data/friction.db`, 6.961 substantive |
| PART 3 — Embedding + kümeleme | Bitti | 6.961 embed (9 dk), KMeans k=12 |
| PART 4 — LLM çıkarımı | **Sıradaki** | ~1.000 kayıt, ~5 saat |
| PART 5 — Sorgu katmanı | Yapılmadı | |
| PART 6 — Analiz + hipotez | Yapılmadı | |
| PART 7 — Değerlendirme | Kısmen (bake-off yapıldı) | |
| PART 8 — Yayın | Yapılmadı | |

### Model seçimi (ölçüldü, varsayılmadı)

Üç dilde 8 elle etiketlenmiş yorum üzerinde dört aday:

| Model | friction_type | would_pay_signal | sn/kayıt |
|---|---|---|---|
| **gemma3:4b** | **7/8** | **8/8** | 15.7 |
| qwen2.5:3b | 6/8 | 6/8 | 6.9 |
| granite3.3:2b | 4/8 | 7/8 | 7.1 |
| llama3.2:3b | 3/8 | 6/8 | 7.4 |

İki hata biçimi yazıya açıkça girecek, çünkü asıl bulgu onlar:

- **llama3.2:3b sekiz vakanın altısına `price_level` dedi.** Toplam skoru orta sıralarda görünürken aslında hiçbir ayrım yapmıyordu — çoğunluk sınıfına çökme. Toplam doğruluk bunu gizler, sınıf bazında bakmak ortaya çıkarır.
- **granite3.3:2b `payment_confusion` uydurdu** — şemada olmayan bir enum değeri. Her çıktının neden doğrulandığının canlı kanıtı.

gemma3:4b bu makinede diğerlerinin iki katı yavaş. Tek seferlik bir toplu iş için bu takas değer.

### Kümeleme bulguları — PART 4'ü bunlar şekillendiriyor

k=12 ile:

- **Kümeler konuya göre değil DİLE göre oluştu.** Küme 0 TR, 2 DE, 3 JA, 4 PT, 8 FR. Çok dilli embedding'de beklenen davranış ve bu bir bulgu: `nomic-embed-text` çok dilli bir korpusta önce dili kodluyor, konuyu sonra. PART 5'teki anlamsal aramanın neden dil içinde kaldığını da bu açıklıyor. Yazıda yer alacak.
- **Küme 5 (n=630, ort. puan 1.60)** — altın madeni. Ücretsiz deneme tuzağı, iptal edememe, haftalık 9.99£ şikâyetleri.
- **Küme 10 (n=367, %88 yüz editörü)** — Retake + ReShoot'un kendi kümesi, sonuç kalitesi üzerine.
- **Kümeler 1, 7, 9, 11 (~2.000)** — kısa İngilizce övgü, "very helpful" tarzı.
- **Küme 6 (n=669)** — kısa ve çok dilli yorumlar. Konu benzerliğinden değil biçim benzerliğinden bir araya gelmiş. İçinde gerçek free_quota_limit ve quality_gap şikâyetleri var ("3 messages? Are you kidding!"). Klavye ezmesi 6961 kaydın sadece 9'u; küme topluca elenmeyecek.

---

## Nasıl çalışıyoruz

- Her PART'ı **ayrı** yapıştır. Hepsini birden verme.
- Her PART için yeni sohbet aç. `@dosya` ile referans vermek yeter.
- Uzun script'leri Claude Code çalıştırmasın. Yazsın, sen kendi terminalinde başlat.
- Her PART'tan sonra: çalıştır, doğrula, `git commit`, sonrakine geç.
- Bir PART çalışmıyorsa ilerleme. Sırayla gitmek, sonda hepsini birden debug etmekten çok daha hızlı.

---

## PART 4 — LLM çıkarımı (çekirdek)

### Neden örnekleme tasarımı bu projenin en kritik kararı

6.961 substantive yorumun tamamını çalıştırmak 31 saat sürer. Örnekleme zorunlu. Ama örneklemeyi yanlış kurmak projeyi savunulamaz hale getirir:

**Amaçlı seçim keşif için doğru, oran için yanlış.** Küme 5'i tamamen alıp övgü kümelerini tamamen dışarıda bırakırsan `friction_type = "none"` sistematik olarak eksik sayılır ve "Nova yorumlarının %X'i paywall sürtünmesi içeriyor" cümlesinin paydası kalmaz. Kayıtların seçilme olasılığı uygulamaya ve dile göre değişiyorsa, çıkan yüzdeler popülasyonun değil örneklemin yüzdesi olur — Codeway vs HubX kıyası yorumlanamaz.

Çözüm iki ayrı çerçeve:

| Çerçeve | n | Nasıl seçilir | Ne için kullanılır |
|---|---|---|---|
| **A — kestirim** | 600 | Uygulama başına 150, uygulama içinde puan bandına (1-2 / 3 / 4-5) göre tabakalı **rastgele**. Övgüler dahil. | Bütün yüzdeler, çift kıyasları, ülke kırılımları |
| **B — keşif** | ~400 | Amaçlı: küme 5'ten 250, küme 10'dan 100, dil kümelerinden anahtar kelime eşleşmesi ~150 | Alıntılar, hipotez üretimi, nadir kategorileri yakalamak |

Çakışan kayıtlarda iki bayrak da 1, kayıt bir kez çıkarılır. Benzersiz toplam ~1.000.

**Sıra önemli: önce filtre, sonra örnekleme, sonra ağırlık.** Klavye ezmesi filtresi
örneklemeden önce çalışmalı. Ters sırada yaparsan `selection_weight`, içinde çöp olan bir
popülasyona göre hesaplanır ve bütün oranlar hafifçe kayar.

**Hangi küme nereden hariç:** Hiçbir küme kestirim çerçevesinden hariç tutulmaz — övgü
kümeleri (1, 7, 9, 11) dahil her şey rastgele seçime girer, çünkü "none" oranının paydası
onlar. Hariç tutma sadece keşif çerçevesi için geçerli: orada 5 ve 10 dışındaki kümelerden
yalnızca anahtar kelime eşleşmeleri alınır. Küme 6 ise filtre adımında `is_substantive = 0`
olduğu için popülasyondan tamamen düşer, örneklemeye hiç girmez.

`extractions` tablosuna üç sütun: `in_estimation_frame`, `in_discovery_frame`, `selection_weight` (= tabaka popülasyonu / tabaka örneklemi). Yüzde hesaplayan her sorgu sadece A'dan ve ağırlıklı çalışır. Bu üç sütun, "yöntemini nasıl savunuyorsun" sorusunun cevabı.

**Hassasiyet, önceden bilinsin:** uygulama başına n=150'de %30 civarı bir oranın standart hatası ~3.7 puan, %95 güven aralığı ±7.3 puan. Yani **çiftler arasında 12 puandan küçük farklar anlamlı değil** ve öyle raporlanmayacak. Bunu kabul edip güven aralıklarını grafiklere koymak, sahte kesinlikten çok daha iyi görünür.

**Küme 5'in tamamını çıkarmaya gerek yok.** "630 subscription_trap yorumunun %71'i Nova'dan" cümlesi için LLM gerekmiyor — küme üyeliği ve app zaten DB'de. Kendi kuralın: veride olanı modele sorma. 250 kayıt doygunluk için fazlasıyla yeter.

### Şema (v2)

```json
{
  "friction_type": "paywall_timing | price_level | subscription_trap | free_quota_limit | referral_gate | quality_gap | onboarding_confusion | performance | none",
  "trigger_moment": "before_first_use | after_first_result | after_free_quota | at_export | unclear | none",
  "mentions_price": true,
  "price_mentioned": "9.99/week | null",
  "paid_but_still_limited": false,
  "would_pay_signal": "yes | no | conditional | unclear",
  "feature_praised": "...",
  "gist": "en fazla 12 kelime, yorumun dili ne olursa olsun HER ZAMAN İngilizce"
}
```

Şema kararları, hepsi gerekçeli:

- **`sentiment` yok.** Her yorumda zaten Apple'ın 1-5 yıldızı var. Bake-off'ta dört modelin dördü de insan etiketlerinden aynı yönde saptı — bu alanın zor değil *muğlak* olduğunu gösterir. Modele sorulacak kötü bir soru.
- **`free_quota_limit` ile `price_level` ayrı.** "Pahalı" ile "ücretsiz kota cimri" tamamen farklı deneyler gerektirir. Asla birleştirme.
- **`referral_gate` enum'a eklendi** (kümelerden çıktı: "sınırsız erişim için 3 arkadaş davet et"). Mevcutken birincil sürtünme o oluyor, dolayısıyla bir tür.
- **`paid_but_still_limited` boolean, enum değil** (lifetime alıp yine limitli kalmak). Bu bir sürtünme türü değil, türlerden bağımsız bir durum: kullanıcı hem "pahalı" deyip hem bu durumda olabilir. Ayrıca friction_type'ı 10 değere çıkarmak 4B bir modelde dağılmaya yol açar; boolean çok daha kolay.

**Şema değişti, bake-off skorları eski şemaya ait.** Tam koşudan önce elindeki 8 etiketli vakayı v2 ile tekrar geçir — 8 × ~18 sn = 2.5 dakika. Gerileme yoksa yazıda "şemayı genişlettim, doğruluğun düşmediğini doğruladım" cümlesi bedavaya geliyor. Gerileme varsa `paid_but_still_limited`'ı düşür.

**Süre tahmini:** 16 sn/kayıt ölçümü 6 alanlı şemaya aitti. v2'de çıktı token'ı arttı, gerçekçi tahmin 18-19 sn. ~1.000 kayıt → **yaklaşık 5 saat**. Tek gece sığar ama teğet geçer.

### Claude Code'a yapıştır

```
PART 4: LLM extraction. @PLAN.md ve @CLAUDE.md'yi oku.

ÖNCE: src/db.py'a migration ekle. extractions tablosuna sütunlar:
friction_type, trigger_moment, mentions_price, price_mentioned,
paid_but_still_limited, would_pay_signal, feature_praised, gist,
cluster_id, in_estimation_frame, in_discovery_frame, selection_weight,
model_name, prompt_version, extracted_at, elapsed_sec,
validation_status.
Migration idempotent olsun (sütun varsa atla).

SONRA src/sample.py. LLM ÇAĞRISI YOK, sadece temizlik + seçim.
SIRA ÖNEMLİ: önce filtre, sonra örnekleme, sonra ağırlık.

ADIM 1 — klavye ezmesi filtresi. Küme 6'da (n=669) "Ggshsjsjsjjdjddndjjd"
tipi kayıtlar 10 karakter filtresini geçmiş. Latin alfabesi için: boşluk
yoksa VE benzersiz karakter oranı < 0.35 VE sesli harf oranı < 0.2 ise
is_substantive = 0. Bu kuralı SADECE latin alfabesine uygula — Japonca
yorumlarda boşluk yok, onları kesme. Kaç kaydın düştüğünü raporla, silme,
sadece bayrağı güncelle. Örnekleme bu adımdan SONRA çalışacak.

ADIM 2 — Çerçeve A (kestirim):
- 4 uygulamanın her birinden 150 kayıt, toplam 600
- Uygulama içinde puan bandına göre tabakalı: (1-2), (3), (4-5).
  Tabaka payı o bandın uygulama içindeki oranıyla orantılı, her
  tabakadan en az 15 kayıt garanti.
- Tabaka içinde RASTGELE, sabit seed (42). Övgü kümeleri dahil —
  "none" oranının paydası bunlar, hariç tutmak yanlış olur.
- selection_weight = tabaka_popülasyonu / tabaka_örneklemi
- in_estimation_frame = 1

ADIM 3 — Çerçeve B (keşif). Kestirim çerçevesinden hiçbir küme hariç
değil; hariç tutma sadece burada geçerli:
- küme 5'ten 250 rastgele
- küme 10'dan 100 rastgele
- dil kümelerinden (0, 2, 3, 4, 8) anahtar kelime eşleşmesi,
  küme başına en fazla 30, toplam ~150
- in_discovery_frame = 1

Çakışan kayıtlarda iki bayrak da 1, kayıt bir kez extract edilir.
Seçim mantığı tek fonksiyonda. Çıktıda her çerçeve ve tabaka için kaç
kayıt seçildiğini tablo bas. Seçimi output/sample.csv'ye de yaz.

Anahtar kelimeler çok dilli. Japonca için 解約 / 課金 / 高い / サブスク
mutlaka olsun ve Japonca'da kelime sınırı olmadığı için regex \b
KULLANMA, düz substring eşleşmesi yap.
TR: abonelik, ücret, pahalı, iptal, deneme, para
DE: teuer, Abo, kündigen, kostenlos
PT: caro, assinatura, cancelar, grátis
FR: cher, abonnement, résilier, gratuit
EN: subscription, paywall, price, expensive, trial, refund, cancel

SONRA src/extract.py:
- Şema PLAN.md'deki v2 hali, prompt'a aynen koy
- ollama format="json", keep_alive="30m",
  options: num_ctx=2048, num_predict=256, temperature=0
- Her çıktı doğrulanacak: enum dışı değer varsa bir kez retry, yine
  olmazsa validation_status="invalid" ve logla. Başarısız sayısı
  sonda raporlanacak — bu saklanacak bir şey değil, bulgu.
- 25 kayıtta bir DB'ye checkpoint, kesilirse kaldığı yerden devam
- tqdm, kalan süre tahmini
- Kayıt başına süre ölçülüp sonda ortalama sn/kayıt basılacak
- prompt_version = "v2" sabiti, model_name ollama'dan gelsin
- --limit N ve --frame {estimation,discovery,all} bayrakları

Script'leri çalıştırma. Yazdıktan sonra bana --limit 20 komutunu ver.
```

### Senin işin

1. `python src/sample.py` — `output/sample.csv`'yi aç, tabaka tablosuna bak. Bir tabaka beklenmedik şekilde boşsa örnekleme değil veri sorunu vardır.
2. `python src/extract.py --limit 20` — çıktıyı satır satır oku. `trigger_moment` sürekli `unclear` dönüyorsa şema fazla ince, sadeleştir. `friction_type` tek kategoriye yığılıyorsa kategoriler kötü tanımlı.
3. 8 etiketli vakayı v2 şemasıyla tekrar geçir, gerileme var mı bak.
4. Gece tam koşu:

```bash
caffeinate -i python src/extract.py --frame all 2>&1 | tee logs/extract.log
```

`caffeinate` olmadan Sonoma uykuya geçip Ollama'yı düşürür. `keep_alive` olmadan model her çağrıda yeniden yüklenir; 8 GB'ta bu kayıt başına 5-10 saniye, 1.000 kayıtta 2 saat eder. `--limit 20` çıktısında sn/kayıt 19'un belirgin üstündeyse önce `num_ctx` ile oyna, sonra tam koşuyu başlat. Koşu sırasında tarayıcıyı kapat, embedding çalıştırma.

---

## PART 5 — Hibrit sorgu katmanı

> İki soru tipi var ve farklı mekanizma istiyorlar. İkisini tek RAG'le çözmeye çalışma.
>
> **A) Toplama soruları** ("kaç tane", "hangi ülkede en çok", "yüzde kaç"):
> - LLM'e metin verme. Sadece **SQL yazdır**.
> - Şemayı prompt'a koy, model SELECT üretsin, sen çalıştır, sonucu doğal dile çevir
> - Güvenlik: sadece SELECT'e izin, INSERT/UPDATE/DELETE/DROP içeren her şey reddedilir
> - **Üretilen SQL cevabın altında gösterilsin** — bu sızıntı değil, özellik
> - **Kritik:** oran soran her sorgu `WHERE in_estimation_frame = 1` içermeli ve
>   `selection_weight` ile ağırlıklandırmalı. Bunu prompt'a kural olarak yaz, model
>   unutursa üretilen SQL'i reddet ve tekrar iste.
>
> **B) Niteliksel sorular** ("Brezilyalı kullanıcılar fiyat hakkında ne diyor"):
> - Embedding aramasıyla en yakın 15 yorumu getir, model sentezlesin
> - Her iddianın yanında gerçek review_id dönsün
> - Arama 6.961 embed edilmiş yorumun tamamı üzerinde çalışır, sadece çıkarılanlar
>   üzerinde değil — burası çerçeve ayrımından etkilenmez
> - **Bilinen sınır:** kümeler dile göre oluştuğu için anlamsal arama dil içinde kalma
>   eğiliminde. Türkçe bir sorgu ağırlıklı Türkçe yorum getirir. Bunu cevabın altında
>   getirilen kayıtların dil dağılımını basarak görünür kıl.
>
> **C) Yönlendirme:** gelen soruyu önce küçük bir LLM çağrısıyla A mı B mi diye sınıflandır
>
> **D) Dürüstlük mekanizması — bunu atlama:**
> - Sonuç 5'ten az kayda dayanıyorsa uyar
> - Benzerlik skoru eşiğin altındaysa tahmin etmek yerine "bunu cevaplayacak veri yok" de
> - Her cevabın altına "N kayda dayanıyor" bas
>
> CLI olarak kur (`src/ask.py`). Web arayüzü yok.

**Senin işin:** Kırmaya çalış. Veri dışında bir şey sor — "Codeway'in CEO'su kim?" gibi. Uyduruyorsa D çalışmıyor. Bu testleri ekran kaydına al, yazıya girecek.

---

## PART 6 — Analiz ve hipotez üretimi

> Şimdi bulgular. **Uydurma metrik yok** — her sayı doğrudan sayılabilir bir şeyden gelecek.
>
> 1. `src/analyze.py`, **eşleşmiş çift mantığıyla** tablolar kursun — uygulamalar tek listede
>    yan yana değil, çift içinde karşı karşıya:
>    - Çift başına friction_type karşılaştırması (ağırlıklı yüzde + %95 GA)
>    - Çift başına trigger_moment dağılımı: aynı dikeyde iki stüdyo paywall'u farklı anlarda
>      mı gösteriyor?
>    - `would_pay_signal = conditional` grubu — en değerli segment: ödemeye yakın ama bir şey
>      engelliyor
>    - Çift başına `price_level` vs `free_quota_limit` ayrımı — farklı deneylere işaret
>      ederler, asla birleştirme
>    - `paid_but_still_limited = true` oranı, çift başına
>    - friction_type × yıldız puanı çapraz tablosu (LLM'in çıkardığı sentiment değil, gerçek
>      puan): hangi sürtünme 1 yıldız üretiyor, hangisi 4 yıldızlık homurdanma
> 2. **Ağırlıklandırma zorunlu.** Bütün oranlar `in_estimation_frame = 1` alt kümesinde ve
>    `selection_weight` ile hesaplanacak. Keşif çerçevesi oran üretmez, sadece alıntı verir.
>    Kodda bunu tek bir `weighted_rate()` fonksiyonuna hapset ki her yerde tekrar etmeyesin.
> 3. **LLM gerektirmeyen bulgular ayrı bölüm.** Küme kompozisyonu (küme 5'in uygulama ve ülke
>    dağılımı), puan dağılımları, yorum hacmi dengesizliği — bunlar 6.961 kaydın tamamı
>    üzerinde, örnekleme hatası olmadan hesaplanır. En sağlam sayıların bunlar, öne çıkar.
> 4. **Ülke kırılımında dikkat.** Kestirim çerçevesi uygulama × puana göre tabakalı, ülkeye
>    göre değil. 600 kayıt / 4 uygulama / 8 ülke ≈ hücre başına 19. Ülke iddialarını sadece
>    en büyük 3-4 pazarda ve çift içinde havuzlanmış olarak kur; n < 30 olan her hücreyi
>    görünür şekilde işaretle.
> 5. Grafikler: matplotlib, 4-5 tane. Sade — ızgara yok, dekoratif renk yok, her grafik tek
>    bir şey söylesin. Her grafikte n ve güven aralığı görünsün.
> 6. `src/hypotheses.py` — bulguları LLM'e verip A/B test hipotezleri ürettir. Format:
>    ```
>    Gözlem: [veriden gelen sayı + kaynağı]
>    Hipotez: [ne değişirse ne olur]
>    Test: [nasıl ölçülür, hangi metrik]
>    Risk: [ne ters gidebilir]
>    ```
> 7. `output/hypotheses.md`'ye yaz.
>
> **Kritik:** Hipotez üretirken prompt'a sadece `analyze.py`'ın hesapladığı gerçek sayıları
> geçir. Modelin sayı üretmesine asla izin verme.

**Senin işin:** Hipotezleri kendi filtrenden geçir. Model 20 tane üretecek, yarısından fazlası genel olacak ("kullanıcı deneyimini iyileştir"). At. Kalan senin projen. **Neyi attığını not et** — "AI çıktısının %60'ını attım, kriterim şuydu" cümlesi, ilanın "AI çıktısını atmaktan korkmamak" maddesinin cevabı.

---

## PART 7 — Değerlendirme katmanı

> Bu adım projeyi "bir sistem kurdum"dan "bir yöntem ölçtüm"e çevirir. Opsiyonel değil.
>
> Bake-off zaten yapıldı (yukarıdaki tablo ve iki hata biçimi). Onlar kurulum adımı değil,
> bulgu — yazıda öyle yer alacak. Şimdi ölçeklendir:
>
> 1. `src/sample_for_labeling.py` — **kestirim çerçevesinden** 100 rastgele yorum seç,
>    `output/to_label.csv` yaz. Sütunlar: review_id, app, body, boş `true_friction_type`.
>    Keşif çerçevesinden seçme; o örneklem şikâyete doğru eğimli, üzerinde ölçülen doğruluk
>    olduğundan yüksek çıkar.
> 2. Ben etiketledikten sonra `src/evaluate.py` — aynı test setinde üç yöntemi kıyasla:
>    - Anahtar kelime eşleşmesi (baseline)
>    - Embedding benzerliğiyle en yakın kategori
>    - LLM çıkarımı
> 3. Her biri için precision, recall, F1. Karışıklık matrisi.
> 4. **Sınıf bazında bak, sadece toplam doğruluğa değil.** llama3.2:3b'nin çoğunluk sınıfına
>    çökmesi toplam skorda görünmüyordu. Aynı hatayı kendi değerlendirmende yapma.
> 5. **LLM'in nerede yanıldığını örnekle göster.** O bölüm, LLM'i kazanan ilan etmekten daha
>    değerli.

**Senin işin:** 100 yorumu elle etiketle. Sıkıcı, yaklaşık bir saat. Ama o saat projenin en savunulabilir parçasını üretiyor — RAG demosu herkeste var, ölçüm kimsede yok.

---

## PART 8 — Yayın

> Sonucu yayımlanabilir hale getir. **Statik site**, canlı model gerekmiyor. Vercel'e deploy.
>
> 1. `site/index.html` — tek sayfa, üç bölüm: **Yöntem**, **Bulgular**, **Hipotezler**
> 2. Grafikler statik görsel olarak gömülü
> 3. Hipotezler kart halinde: gözlem → hipotez → test → risk
> 4. Sohbet canlı değil: terminal oturumunun GIF'i artı örnek soru-cevap
> 5. **Sınırlılıklar bölümü olacak** ve gömülmeyecek, görünür yerde duracak:
>    kontrol uygulaması yok; kestirim çerçevesi uygulama başına 150 kayıt, 12 puandan küçük
>    farklar anlamlı değil; kümeler dile göre oluştuğu için anlamsal arama dil içinde kalıyor;
>    App Store RSS uygulama-ülke başına ~500 yorumla sınırlı, örneklem güncel yorumlara eğimli.
>    Bu bölüm zayıflık değil, sinyal.
>
> **Tasarım yönü — bu önemli, başvurulan rol görsel yargı istiyor:**
> - Varsayılan Bootstrap/Tailwind görüntüsü yok. Şablon gibi durmasın.
> - Tek güçlü tipografik karar, en fazla iki font
> - Dar palet: bir nötr zemin, bir vurgu. Grafikler aynı paleti kullansın.
> - Cömert boşluk, geniş satır yüksekliği
> - Mobilde bozulmasın ama mobile-first tasarlama — bu bir okuma sayfası
> - Animasyon, gradyan, glassmorphism, emoji yok
>
> Vanilla HTML/CSS. Framework kurma.

**Senin işin:** En güçlü üç hipotezin için Figma'da paywall varyantı mockup'la ve sayfaya koy. Bir saatlik iş ama "analiz etti" ile "ne yapılacağını gösterdi" arasındaki farkı tam olarak bu yaratıyor.

---

## Başvuru e-postası

Proje bitince tek paragraf:

> Merhaba — Growth Product Specialist ilanı için yazıyorum. İlanı okuduktan sonra Codeway ve HubX uygulamalarını aynı dikeyler içinde eşleştirip 8 ülkedeki App Store yorumlarını analiz eden bir sistem kurdum. Bulgular ve 8 test hipotezi burada: [link]. Tamamı yerel bir LLM'de çalışıyor, kod açık: [github].

CV'yi ekle ama e-postayı onun etrafına kurma. Link yeterince şey söylüyor.

---

## Süre tahminleri — kalan iş

| Part | Süre | Not |
|---|---|---|
| 4 | 2 saat kurulum + ~5 saat koşu | Toplu işi gece başlat |
| 5 | 3-4 saat | Debug'ın çoğu burada |
| 6 | 2 saat + senin filtren | |
| 7 | 1 saat kod + 1 saat etiketleme | |
| 8 | 4-5 saat | Zamanı tasarıma harca |

Sıkıştırırsan 2-3 gün, normal tempoda 4-5 gün.
