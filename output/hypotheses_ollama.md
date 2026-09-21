# Friction Atlas — A/B Test Hipotezleri

gemma3:4b tarafından, `output/observations.csv`'deki 69 gerçek gözlemden üretildi. Modelin kendi ürettiği hiçbir sayı yok - her "Gözlem" satırı aşağıda otomatik doğrulandı.

## 1

**Gözlem:** chatbot çifti, Chat AI: Ask Agent Anything friction_type=paywall_timing oranı: %4.3 [%1.4-%7.2] (n=149) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** Chat AI'nın paywall zamanlamasıyla ilgili friction'ı azaltmak, kullanıcıların ücretli aboneliğe geçiş oranını artırabilir.

**Test:** Chat AI'nın paywall zamanlamasıyla ilgili friction'ı azaltan bir tasarım değişikliği kullanıcıların %30'una gösterilir, 3 hafta boyunca ücretli aboneliğe geçiş oranı ölçülür.

**Risk:** Tasarım değişikliği kullanıcı deneyimini olumsuz etkileyebilir ve kullanıcıların uygulamayı terk etmesine neden olabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 2

**Gözlem:** chatbot çifti, AI Chatbot - Nova friction_type=paywall_timing oranı: %2.5 [%0.2-%4.7] (n=148) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** AI Chatbot - Nova'nın paywall zamanlamasıyla ilgili friction'ı azaltmak, kullanıcıların ücretli aboneliğe geçiş oranını artırabilir.

**Test:** AI Chatbot - Nova'nın paywall zamanlamasıyla ilgili friction'ı azaltan bir tasarım değişikliği kullanıcıların %30'una gösterilir, 3 hafta boyunca ücretli aboneliğe geçiş oranı ölçülür.

**Risk:** Tasarım değişikliği kullanıcı deneyimini olumsuz etkileyebilir ve kullanıcıların uygulamayı terk etmesine neden olabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 3

**Gözlem:** chatbot çifti, Chat AI: Ask Agent Anything friction_type=subscription_trap oranı: %3.3 [%0.7-%5.8] (n=149) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** Chat AI'nın abonelik tuzağı friction'ı azaltmak, kullanıcıların aboneliklerinin süresini uzatabilir.

**Test:** Chat AI'nın abonelik tuzağı friction'ı azaltan bir tasarım değişikliği kullanıcıların %30'una gösterilir, kullanıcıların aboneliklerinin ortalama süresi 6 hafta boyunca ölçülür.

**Risk:** Abonelik tuzağı friction'ı azaltma çabası, kullanıcıların aboneliklerini iptal etmesine neden olabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 4

**Gözlem:** face çifti, Retake AI Face & Selfie Editor friction_type=paywall_timing oranı: %14.1 [%9.3-%18.9] (n=150) - fark anlamlı

**Hipotez:** Retake AI Face & Selfie Editor'daki ödeme zamanlamasıyla ilgili sürtüşme oranını azaltmak, kullanıcıların ücretli özelliklere erişimini artırabilir.

**Test:** Bu sürtüşme oranının üst sınırını temsil eden %18.9'daki kullanıcı segmentine, ödeme sürecini hızlandıran bir "Hemen Başla" düğmesi ekleyin, 3 hafta boyunca dönüşüm oranını ölçün.

**Risk:** "Hemen Başla" düğmesi, kullanıcıları ödeme sürecinden caydırabilir ve genel dönüşüm oranını düşürebilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 5

**Gözlem:** face çifti, ReShoot: AI Face Photo Editor friction_type=paywall_timing oranı: %6.3 [%3.4-%9.2] (n=149) - fark anlamlı

**Hipotez:** ReShoot: AI Face Photo Editor'daki ödeme zamanlamasıyla ilgili sürtüşme oranını azaltmak, kullanıcıların ücretli özelliklere erişimini artırabilir.

**Test:** Bu sürtüşme oranının üst sınırını temsil eden %9.2'deki kullanıcı segmentine, ödeme sürecini daha cazip hale getiren bir "Ücretsiz Deneme" seçeneği sunun, 4 hafta boyunca dönüşüm oranını ölçün.

**Risk:** "Ücretsiz Deneme" seçeneği, kullanıcıları ücretli aboneliğe geçişten caydırabilir ve uzun vadede gelir elde etmeyi zorlaştırabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 6

**Gözlem:** face çifti, Retake AI Face & Selfie Editor friction_type=subscription_trap oranı: %6.1 [%2.5-%9.7] (n=150) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** Retake AI Face & Selfie Editor'daki abonelik tuzağı sürtüşme oranında herhangi bir fark bulunmadığı için, bu sürtüşme oranını azaltmak için mevcut stratejilerin etkili olduğu varsayılabilir.

**Test:** Mevcut stratejileri koruyarak, 2 hafta boyunca bu sürtüşme oranını izleyin ve herhangi bir değişiklik yapmayın.

**Risk:** Verilerde bir yanlışlık olabilir veya farklı kullanıcı segmentleri farklı tepkiler verebilir; bu nedenle, gelecekteki analizler için bu durumu göz önünde bulundurun.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 7

**Gözlem:** chatbot çifti, Chat AI: Ask Agent Anything trigger_moment=before_first_use oranı: %9.6 [%5.1-%14.0] (n=149) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** İlk kullanımda "Ask Agent Anything" tetikleme oranını artırmak için, kullanıcıya daha fazla yardım ipucu sunmak etkili olmayabilir.

**Test:** "Ask Agent Anything" tetikleme oranını etkileyecek potansiyel ipuçlarını chatbot'a ekleyin, 2 hafta boyunca tetikleme oranını ölçün.

**Risk:** Kullanıcılar zaten mevcut ipuçlarını kullanıyor olabilir veya "Ask Agent Anything" özelliği hakkında yeterince bilgi sahibi olmayabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 8

**Gözlem:** chatbot çifti, AI Chatbot - Nova trigger_moment=before_first_use oranı: %11.6 [%7.0-%16.2] (n=148) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** İlk kullanımda "AI Chatbot - Nova" tetikleme oranını artırmak için, Nova'nın sunduğu temel özelliklere vurgu yapmak daha etkili olabilir.

**Test:** "AI Chatbot - Nova" tetikleme oranını etkileyecek temel özelliklerin listesini chatbot'a ekleyin, 3 hafta boyunca tetikleme oranını ölçün.

**Risk:** Kullanıcılar Nova'nın sunduğu özelliklerden haberdar olmayabilir veya bu özelliklere ilgi duymayabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 9

**Gözlem:** chatbot çifti, Chat AI: Ask Agent Anything trigger_moment=after_first_result oranı: %9.9 [%5.4-%14.5] (n=149) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** İlk sonuçtan sonra "Ask Agent Anything" tetikleme oranını artırmak için, kullanıcıya daha fazla ilgili sonuç sunmak etkili olmayabilir.

**Test:** İlk sonuçtan sonra, kullanıcının sorgusuyla ilgili daha fazla sonuç sunan bir filtreleme mekanizması ekleyin, 4 hafta boyunca tetikleme oranını ölçün.

**Risk:** Kullanıcılar zaten ilk sonuçtan memnun kalmış olabilir veya daha fazla bilgiye ihtiyaç duymayabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 10

**Gözlem:** face çifti, Retake AI Face & Selfie Editor trigger_moment=before_first_use oranı: %29.1 [%22.6-%35.7] (n=150) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** Retake AI Face & Selfie Editor'nın ilk kullanım öncesi tetiklenme oranını artırmak, uygulamanın genel kullanımını artırabilir.

**Test:** Uygulamanın ilk açılışında kullanıcıları Retake AI Face & Selfie Editor'a yönlendiren bir bildirim gönderin, 3 hafta boyunca tetiklenme oranını ölçün.

**Risk:** Kullanıcılar bildirimleri görmezden gelebilir veya uygulamanın temel özelliklerine odaklanabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 11

**Gözlem:** face çifti, ReShoot: AI Face Photo Editor trigger_moment=before_first_use oranı: %19.2 [%14.3-%24.1] (n=149) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** ReShoot: AI Face Photo Editor'ın ilk kullanım öncesi tetiklenme oranını artırmak, uygulamanın genel kullanımını artırabilir.

**Test:** Uygulamanın ilk açılışında kullanıcıları ReShoot: AI Face Photo Editor'a yönlendiren bir bildirim gönderin, 4 hafta boyunca tetiklenme oranını ölçün.

**Risk:** Kullanıcılar bildirimleri görmezden gelebilir veya uygulamanın temel özelliklerine odaklanabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 12

**Gözlem:** face çifti, Retake AI Face & Selfie Editor trigger_moment=after_first_result oranı: %8.4 [%4.3-%12.5] (n=150) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** Retake AI Face & Selfie Editor'ın ilk sonuçtan sonra tetiklenme oranını artırmak, kullanıcıların daha fazla içerik oluşturmasını teşvik edebilir.

**Test:** Kullanıcıların ilk sonuçlarını aldıktan sonra, benzer efektler yaratmak için Retake AI Face & Selfie Editor'ı öneren bir bildirim gönderin, 2 hafta boyunca tetiklenme oranını ölçün.

**Risk:** Kullanıcılar ilk sonuçtan memnun kalmış olabilir ve daha fazla etkileşimde bulunmak istemeyebilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 13

**Gözlem:** chatbot çifti, Chat AI: Ask Agent Anything would_pay_signal='conditional' oranı: %9.2 [%4.6-%13.9] (n=149) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** Chat AI'nın conditional sinyalini taşıyan kullanıcı segmentindeki kullanıcıların ödeme davranışlarını etkileyecek bir mesaj (örneğin, "Daha fazla deneme günü!") göstermek dönüşümü artırabilir.

**Test:** conditional sinyali taşıyan yorumların geldiği kullanıcı segmentine özel bir mesajla gösterim yapın, 3 hafta boyunca dönüşüm oranını ölçün.

**Risk:** Mesajın kullanıcılar tarafından dikkate alınmaması veya mesajın içeriği satın alma kararını etkilemeyen bir konu olması.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 14

**Gözlem:** face çifti, Retake AI Face & Selfie Editor would_pay_signal='conditional' oranı: %12.3 [%7.4-%17.1] (n=150) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** Retake AI'nın conditional sinyalini taşıyan kullanıcı segmentindeki kullanıcıların, yüz düzenleme özelliklerine olan ilgisini artıracak bir özellik tanıtımı (örneğin, yeni filtreler) dönüşümü etkileyebilir.

**Test:** conditional sinyali taşıyan yorumların geldiği kullanıcı segmentine yeni filtreler ekleyin, 4 hafta boyunca dönüşüm oranını ölçün.

**Risk:** Yeni filtrelerin kullanıcılar tarafından ilgi çekici bulunmaması veya mevcut filtrelerin yeterli seçenek sunması.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 15

**Gözlem:** face çifti, ReShoot: AI Face Photo Editor would_pay_signal='conditional' oranı: %11.9 [%7.8-%16.1] (n=149) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** ReShoot uygulamasının conditional sinyalini taşıyan kullanıcı segmentindeki kullanıcıların, video düzenleme özelliklerine olan ilgisini artıracak bir özellik tanıtımı (örneğin, otomatik efektler) dönüşümü etkileyebilir.

**Test:** conditional sinyali taşıyan yorumların geldiği kullanıcı segmentine otomatik efektler ekleyin, 5 hafta boyunca dönüşüm oranını ölçün.

**Risk:** Otomatik efektlerin kullanıcılar tarafından kullanışlı bulunmaması veya mevcut efektlerin yeterli seçenek sunması.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 16

**Gözlem:** Retake AI'nın would_pay_signal='conditional' oranı %12.4 (n=150) - en yüksek segment

**Hipotez:** Bu segmentteki kullanıcılara ödeme ekranında küçük bir teşvik (ek deneme günü veya indirim) göstermek dönüşümü artırabilir.

**Test:** conditional sinyali taşıyan yorumların geldiği kullanıcı segmentine özel bir teklif ekranı 6 hafta A/B test edilir, dönüşüm oranı metriği.

**Risk:** Segment yorum metninden çıkarıldı; gerçek satın alma niyetiyle birebir örtüşmeyebilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 17

**Gözlem:** face çifti, Retake AI Face & Selfie Editor friction_type=price_level oranı: %9.0 [%4.7-%13.3] (n=150) - fark anlamlı

**Hipotez:** Retake AI Face & Selfie Editor'ın fiyatlandırma sürecindeki friction'ını azaltmak, kullanıcıların ücretli sürümüne geçiş oranını artırabilir.

**Test:** Retake AI Face & Selfie Editor'ın fiyatlandırma sayfasını, mevcut kullanıcıların %50'sine göster, 4 hafta boyunca ücretli sürüm geçiş oranını ölç.

**Risk:** Kullanıcıların fiyatlandırma konusunda farklı hassasiyetleri olabilir; indirimler kullanıcıları caydırabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 18

**Gözlem:** face çifti, ReShoot: AI Face Photo Editor friction_type=price_level oranı: %1.6 [%0.0-%3.1] (n=149) - fark anlamlı

**Hipotez:** ReShoot: AI Face Photo Editor'ın fiyatlandırma sürecindeki friction'ını azaltmak, kullanıcıların ücretli sürümüne geçiş oranını artırabilir.

**Test:** ReShoot: AI Face Photo Editor'ın fiyatlandırma sayfasını, mevcut kullanıcıların %50'sine göster, 4 hafta boyunca ücretli sürüm geçiş oranını ölç.

**Risk:** Kullanıcıların fiyatlandırma konusunda farklı hassasiyetleri olabilir; indirimler kullanıcıları caydırabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 19

**Gözlem:** chatbot çifti, Chat AI: Ask Agent Anything paid_but_still_limited oranı: %6.7 [%3.4-%9.9] (n=149) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** Chat AI'nın 'Ask Agent Anything' özelliğinin, kullanıcıların ödeme yapma eğilimini artırmadığı görülüyor.

**Test:** Chat AI'ya ek olarak, Nova'nın 'Ask Agent Anything' özelliğini farklı bir şekilde pazarlayın, 3 hafta boyunca 'Ask Agent Anything' özelliğini kullanan kullanıcıların ödeme oranını ölçün.

**Risk:** Kullanıcılar, 'Ask Agent Anything' özelliğinin değerini tam olarak anlamayabilir ve bu nedenle ödeme yapmaktan kaçınabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 20

**Gözlem:** face çifti, Retake AI Face & Selfie Editor paid_but_still_limited oranı: %13.2 [%8.4-%18.0] (n=150) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** Retake AI'nın 'Face & Selfie Editor' özelliği, kullanıcıların ödeme yapma eğilimini artırmıyor.

**Test:** Retake AI'nın 'Face & Selfie Editor' özelliğini, ReShoot'un 'AI Face Photo Editor' özelliğine kıyasla farklı bir şekilde tanıtın, 4 hafta boyunca her bir editörün ödeme oranını karşılaştırın.

**Risk:** İki editör arasındaki özellik farkı kullanıcılar tarafından yeterince fark edilmeyebilir ve bu da ödeme oranlarındaki farkı etkileyebilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 21

**Gözlem:** face çifti, ReShoot: AI Face Photo Editor paid_but_still_limited oranı: %10.7 [%6.9-%14.4] (n=149) - fark anlamlı değil (GA'lar çakışıyor)

**Hipotez:** ReShoot'un 'AI Face Photo Editor' özelliği, kullanıcıların ödeme yapma eğilimini artırmıyor.

**Test:** ReShoot'un 'AI Face Photo Editor' özelliğini, farklı bir kullanıcı segmentine tanıtın ve 2 hafta boyunca bu segmentin ödeme oranını izleyin.

**Risk:** Hedeflenen kullanıcı segmenti, bu tür bir fotoğraf düzenleme özelliğini kullanmaya uygun olmayabilir.

> ⚠ fark istatistiksel olarak anlamlı değil

---

## 22

**Gözlem:** Klavye ezmesi filtresinin düşürdüğü kayıt sayısı: 9 (n=9) ⚠ düşük n

**Hipotez:** Klavye ezmesi filtrelerinin etkinliğini artırmak, daha fazla kullanıcıyı uygulamaya kaydettirebilir.

**Test:** Klavye ezmesi filtrelerini etkinleştiren kullanıcıların kayıt oranını, filtreleri devre dışı bırakan kullanıcılarla karşılaştırın, 2 hafta boyunca kayıt sayısını ölçün.

**Risk:** Düşük örneklem boyutu nedeniyle sonuçlar istatistiksel olarak anlamlı olmayabilir.

> ⚠ düşük n; fark istatistiksel olarak anlamlı değil

---

## 23

**Gözlem:** chatbot çifti, br pazarı herhangi-sürtünme ham oranı: %45.2 (n=42)

**Hipotez:** Br pazarı kullanıcılarına yönelik chatbot deneyimini optimize etmek, herhangi-sürtünme oranını azaltabilir.

**Test:** Br pazarı kullanıcılarına özel olarak chatbot yanıtlarını ve akışlarını yeniden düzenleyin, 3 hafta boyunca herhangi-sürtünme oranını ölçün.

**Risk:** Yeniden düzenleme, kullanıcı deneyimini olumsuz etkileyebilir ve dönüşümleri azaltabilir.

---

## 24

**Gözlem:** face çifti, fr pazarı herhangi-sürtünme ham oranı: %66.7 (n=18) ⚠ düşük n

**Hipotez:** Fransa pazarı kullanıcılarına yönelik yüz tanıma deneyimini iyileştirmek, herhangi-sürtünme oranını azaltabilir.

**Test:** Fransa pazarı kullanıcılarına yüz tanıma doğruluğunu ve hızını artırmaya yönelik iyileştirmeler uygulayın, 4 hafta boyunca herhangi-sürtünme oranını ölçün.

**Risk:** Düşük örneklem boyutu nedeniyle sonuçlar istatistiksel olarak anlamlı olmayabilir ve iyileştirmeler etkili olmayabilir.

> ⚠ düşük n

---

