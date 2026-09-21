# Friction Atlas — A/B Test Hipotezleri (Claude tarafından üretildi)

Claude Sonnet 5 tarafından, `output/hypotheses_prompt.md`'deki talimata göre ve `output/observations.csv`'deki 68 gerçek gözlemden üretildi. Ollama çağrısı yapılmadı. Her "Gözlem" satırındaki sayı `output/observations.csv`'de birebir doğrulandı; hiçbir sayı üretilmedi.

18 hipotez, 2 tanesi istatistiksel olarak anlamlı bir farka dayanıyor (aşağıda işaretli).

---

## 1 — anlamlı fark

**Gözlem:** Retake AI Face & Selfie Editor'ın paywall_timing oranı %14.1 (n=150), ReShoot: AI Face Photo Editor'ınki %6.3 (n=149) - fark anlamlı.

**Hipotez:** Retake AI'da paywall'ın gösterildiği an, ilk yüz düzenleme sonucu kullanıcıya gösterildikten SONRAYA ertelenmeli (şu an muhtemelen kullanım öncesinde/sırasında gösteriliyor); ReShoot'un düşük oranı böyle bir geç-gösterim modeliyle tutarlı olabilir.

**Test:** Retake AI'da paywall'ı "ilk sonuç görüntülendikten sonra" gösteren bir varyant, mevcut akışa karşı 4 hafta A/B test edilir; yeni yorumlardaki paywall_timing şikayet oranı ve ücretsizden-ücretliye dönüşüm oranı birlikte ölçülür.

**Risk:** Paywall'ı geciktirmek kısa vadede dönüşümü düşürebilir, çünkü kullanıcı sonucu zaten ücretsiz almış olur.

---

## 2 — anlamlı fark

**Gözlem:** Retake AI Face & Selfie Editor'ın price_level oranı %9.0 (n=150), ReShoot: AI Face Photo Editor'ınki %1.6 (n=149) - fark anlamlı.

**Hipotez:** Retake AI'nın mevcut abonelik fiyatını ReShoot'un fiyat basamağına yaklaştırmak (veya aynı fiyata daha fazla haftalık kredi eklemek) fiyat şikayetlerini azaltabilir.

**Test:** Retake AI'da mevcut fiyatın ~%20 altında bir tanıtım fiyatı yeni kullanıcıların yarısına 4 hafta gösterilir; price_level içerikli yeni yorum oranı ve ARPU birlikte izlenir.

**Risk:** Fiyat düşürmek gelir kaybına yol açabilir; ARPU'nun oran düşüşünü telafi edip etmediği görülmeden kalıcı hale getirilmemeli.

---

## 3

**Gözlem:** Retake AI Face & Selfie Editor'da trigger_moment=before_first_use oranı %29.1 (n=150), ReShoot: AI Face Photo Editor'da %19.2 (n=149) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** İki uygulamada da en yüksek sürtünme anı kullanıcı ürünü hiç denemeden önce yaşanıyor; Retake AI'da ilk açılışta ödeme duvarı yerine filigranlı, sınırlı bir ücretsiz önizleme düzenlemesi sunmak bu anı erteleyebilir.

**Test:** Yeni kullanıcılara ilk oturumda 1 ücretsiz filigranlı düzenleme hakkı tanınan bir varyant, mevcut anında-paywall akışına karşı 4 hafta test edilir; before_first_use trigger_moment oranı ve gün-1 elde tutma ölçülür.

**Risk:** Fark istatistiksel olarak anlamlı değil; gözlem yön gösterici olarak alınmalı, doğrudan yatırım kararına dayanak yapılmamalı.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 4

**Gözlem:** AI Chatbot - Nova'da friction_type=performance oranı %4.2 (n=148), Chat AI: Ask Agent Anything'de %0.7 (n=149) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** Nova'da yanıt üretim süresini kısaltacak bir sunucu/model optimizasyonuna (daha hızlı bir yanıt modeline geçiş) öncelik verilmeli.

**Test:** Optimize edilmiş yanıt hattı kullanıcıların yarısına 3 hafta sunulur; yeni yorumlardaki performance içerikli şikayet oranı karşılaştırılır.

**Risk:** Fark istatistiksel olarak anlamlı değil; gözlemlenen fark örnekleme hatasından kaynaklanıyor olabilir, yatırımdan önce daha büyük örneklemle doğrulanmalı.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 5

**Gözlem:** AI Chatbot - Nova'da friction_type=subscription_trap oranı %7.4 (n=148), Chat AI: Ask Agent Anything'de %3.3 (n=149) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** Nova'nın abonelik yönetimine, mağaza dışına çıkmadan uygulama içinden erişilebilen tek adımlı bir "aboneliği yönet" bağlantısı eklemek abonelik tuzağı şikayetlerini azaltabilir.

**Test:** Yeni "aboneliği yönet" bağlantısı ayarlar menüsüne eklenir; 4 hafta sonra subscription_trap içerikli yeni yorum oranı önceki döneme karşı karşılaştırılır.

**Risk:** Fark istatistiksel olarak anlamlı değil; ayrıca iptal akışını kolaylaştırmak kısa vadeli churn'ü artırabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 6

**Gözlem:** Chat AI: Ask Agent Anything'de would_pay_signal='conditional' oranı %9.2 (n=149), AI Chatbot - Nova'da %6.0 (n=148) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** Chat AI'da "conditional" sinyali taşıyan yorumlarda sık geçen engeli hedefleyen, ödeme ekranında gösterilecek süreli bir indirim kodu denenmeli.

**Test:** conditional segmentiyle örtüşen düşük kullanım yoğunluklu kullanıcılara özel %20 indirimli bir teklif ekranı 6 hafta A/B test edilir; dönüşüm oranı ölçülür.

**Risk:** Fark istatistiksel olarak anlamlı değil; segment yorum metninden çıkarıldığı için gerçek ödeme niyetiyle tam örtüşmeyebilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 7

**Gözlem:** Retake AI Face & Selfie Editor'da would_pay_signal='conditional' oranı %12.3 (n=150), ReShoot: AI Face Photo Editor'da %11.9 (n=149) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** Face çiftinde conditional oranı diğer sinyallerden belirgin şekilde yüksek; her iki uygulamada da ödeme ekranına, kullanıcıların en sık talep ettiği eksik özelliği öne çıkaran bir teklif ekranı eklenmeli.

**Test:** Yeni teklif ekranı Retake AI'da kullanıcıların yarısına 6 hafta gösterilir; dönüşüm oranı ve conditional oranındaki değişim izlenir.

**Risk:** Fark istatistiksel olarak anlamlı değil; iki uygulama zaten birbirine yakın, bulgu bir çift-karşılaştırması değil segment büyüklüğü gözlemidir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 8

**Gözlem:** Retake AI Face & Selfie Editor'da paid_but_still_limited oranı %13.2 (n=150), ReShoot: AI Face Photo Editor'da %10.7 (n=149) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** Retake AI'da satın alma sonrası ekranda kullanıcının tam olarak hangi hakları aldığını gösteren bir "aboneliğin özeti" ekranı eklemek, ödeme yapıp yine de limitli kaldığını bildiren kullanıcı oranını azaltabilir.

**Test:** Satın alma sonrası özet ekranı yeni abonelerin yarısına 4 hafta gösterilir; paid_but_still_limited içerikli yeni yorum oranı karşılaştırılır.

**Risk:** Fark istatistiksel olarak anlamlı değil; sorunun kaynağı iletişim eksikliği değil gerçek bir ürün kısıtlaması olabilir, bu durumda ekran değişikliği etkisiz kalır.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 9

**Gözlem:** Chat AI: Ask Agent Anything'de paid_but_still_limited oranı %6.7 (n=149), AI Chatbot - Nova'da %6.0 (n=148) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** Chat AI'da satın alma sonrası, kullanıcının hangi hakları aldığını özetleyen bir onboarding kartı göstermek, ödeme yapıp yine limitli kalan kullanıcı oranını azaltabilir.

**Test:** Onboarding kartı yeni abonelerin yarısına 4 hafta gösterilir; paid_but_still_limited içerikli yeni yorum oranı karşılaştırılır.

**Risk:** Fark istatistiksel olarak anlamlı değil; oranlar zaten birbirine çok yakın, öncelik düşük tutulmalı.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 10

**Gözlem:** face çifti, fr pazarında herhangi-sürtünme ham oranı %66.7 (n=18) ⚠ düşük n (örneklem ülkeye göre tabakalanmadı, popülasyona genellenemez).

**Hipotez:** Fransa pazarı için Fransızca yerelleştirilmiş bir destek/SSS ekranı denenmeli; ancak n=18 çok düşük olduğundan önce bu pazardan daha fazla veri toplanmalı.

**Test:** Yerelleştirilmiş SSS ekranı Fransa trafiğinin yarısına 4 hafta sunulur; ham şikayet oranındaki değişim izlenir (küçük örneklem nedeniyle sonuç yönlendirici kabul edilmeli).

**Risk:** n=18 çok düşük; gözlemlenen oran gürültü olabilir, doğrudan ürün yatırımına dayanak yapılmamalı.

> ⚠ düşük n

---

## 11

**Gözlem:** face çifti, de pazarında herhangi-sürtünme ham oranı %45.5 (n=22) ⚠ düşük n (örneklem ülkeye göre tabakalanmadı, popülasyona genellenemez).

**Hipotez:** Almanya pazarı için yerel para birimi gösterimi olan bir fiyat ekranı denenmeli; n=22 ile bu öncelik sırası düşük tutulmalı.

**Test:** Yerel para birimi gösteren fiyat ekranı Almanya trafiğinin yarısına 4 hafta sunulur; ham şikayet oranındaki değişim izlenir.

**Risk:** n=22 düşük n; gözlemlenen oran tesadüfi olabilir, örneklem büyümeden karar verilmemeli.

> ⚠ düşük n

---

## 12

**Gözlem:** chatbot çifti, br pazarında herhangi-sürtünme ham oranı %45.2 (n=42), us pazarında %20.6 (n=34) (örneklem ülkeye göre tabakalanmadı, popülasyona genellenemez).

**Hipotez:** Brezilya trafiğinde ödeme ekranına yerel bir ödeme yöntemi (Pix) eklemek, ABD'ye kıyasla belirgin şekilde yüksek görünen ham şikayet oranını azaltabilir.

**Test:** Pix ödeme seçeneği Brezilya kullanıcılarının yarısına 4 hafta sunulur; ham şikayet oranı ve ödeme tamamlama oranı ölçülür.

**Risk:** Bu iki oran arasında formal bir anlamlılık testi yapılmadı (örneklem ülkeye göre tabakalanmadı); fark örnekleme dengesizliğinden kaynaklanıyor olabilir.

---

## 13

**Gözlem:** Retake AI Face & Selfie Editor'da friction_type=free_quota_limit oranı %9.0 (n=150), ReShoot: AI Face Photo Editor'da %5.3 (n=149) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** Retake AI'da günlük ücretsiz düzenleme hakkını 1'den 2'ye çıkarmak kota şikayetlerini azaltabilir.

**Test:** Günlük ücretsiz hak sayısı 2 olan bir varyant kullanıcıların yarısına 3 hafta sunulur; free_quota_limit içerikli yeni yorum oranı ve ücretliye dönüşüm oranı birlikte izlenir.

**Risk:** Fark istatistiksel olarak anlamlı değil; ayrıca ücretsiz hakkı artırmak ücretliye dönüşüm oranını düşürebilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 14

**Gözlem:** AI Chatbot - Nova'da trigger_moment=before_first_use oranı %11.6 (n=148), Chat AI: Ask Agent Anything'de %9.6 (n=149) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** Nova'da ilk açılıştaki zorunlu kayıt/ödeme ekranını, kullanıcı en az bir mesaj gönderene kadar ertelemek ilk-kullanım-öncesi sürtünmeyi azaltabilir.

**Test:** Kayıt ekranının ilk mesajdan sonra gösterildiği bir varyant 4 hafta A/B test edilir; before_first_use trigger_moment oranı ve gün-1 elde tutma ölçülür.

**Risk:** Fark istatistiksel olarak anlamlı değil; ayrıca ödemeyi ertelemek gelir elde etme hızını düşürebilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 15

**Gözlem:** Chat AI: Ask Agent Anything'de trigger_moment=after_first_result oranı %9.9 (n=149), AI Chatbot - Nova'da %6.4 (n=148) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** Chat AI'da ilk yanıt üretildikten hemen sonra gösterilen paywall'ın yerine, kullanıcı 3 mesaj gönderene kadar bir bekleme süresi eklenmesi bu andaki sürtünmeyi azaltabilir.

**Test:** Paywall'ın 3. mesajdan sonra gösterildiği bir varyant 4 hafta test edilir; after_first_result trigger_moment oranı izlenir.

**Risk:** Fark istatistiksel olarak anlamlı değil; paywall'ı geciktirmek erken dönüşümü azaltabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 16

**Gözlem:** ReShoot: AI Face Photo Editor'da friction_type=quality_gap oranı %5.1 (n=149), Retake AI Face & Selfie Editor'da %4.0 (n=150) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** ReShoot'ta düzenleme öncesi bir "önce/sonra örnek" önizlemesi eklemek, çıktı kalitesi beklentisini netleştirerek kalite-beklenti uyuşmazlığı şikayetlerini azaltabilir.

**Test:** Önizleme özelliği kullanıcıların yarısına 3 hafta sunulur; quality_gap içerikli yeni yorum oranı karşılaştırılır.

**Risk:** Fark istatistiksel olarak anlamlı değil; ayrıca gerçek çıktı kalitesi değişmediği için önizleme beklenti farkını tam kapatmayabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 17

**Gözlem:** Chat AI: Ask Agent Anything'de friction_type=free_quota_limit oranı %4.3 (n=149), AI Chatbot - Nova'da %3.9 (n=148) - fark anlamlı değil (GA'lar çakışıyor).

**Hipotez:** Chat AI'da ücretsiz mesaj hakkı tükenmeden önce kalan hakkı gösteren bir sayaç eklemek, kota sınırına ani çarpma hissini azaltabilir.

**Test:** Sayaç özelliği kullanıcıların yarısına 3 hafta sunulur; free_quota_limit içerikli yeni yorum oranı karşılaştırılır.

**Risk:** Fark istatistiksel olarak anlamlı değil; oranlar zaten birbirine yakın, düşük öncelikli bir test.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 18

**Gözlem:** face çifti, us pazarında herhangi-sürtünme ham oranı %38.5 (n=135), br pazarında %41.1 (n=56) (örneklem ülkeye göre tabakalanmadı, popülasyona genellenemez).

**Hipotez:** ABD, en büyük ve en güvenilir örneklem hücresi olduğu için (n=135), paywall zamanlamasını değiştiren varyant (bkz. hipotez 1) önce ABD trafiğinde test edilmeli.

**Test:** ABD trafiğinde paywall'ın ilk sonuçtan sonra gösterildiği varyant 4 hafta test edilir; ham şikayet oranı ve dönüşüm oranı birlikte izlenir.

**Risk:** n=135 diğer ülke hücrelerinden büyük olsa da örneklem ülkeye göre tabakalanmadığı için sonuç yine de popülasyona genellenemez.
