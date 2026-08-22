# Güvenlik politikası

<sub><a href="SECURITY.md">English</a></sub>

## Özel olarak bildirin

Bu deponun güvenlik sekmesindeki GitHub özel güvenlik açığı bildirimini
kullanın. Bu yol, bildirimi açık bir konuda ifşa etmeden açıklamayı eşgüdümlü
yürütmemizi sağlar.

Bu yol kullanılamıyorsa
[fatih@komunite.com.tr](mailto:fatih@komunite.com.tr?subject=Mintmark%20security%20contact)
adresine yazın ve güvenli bir kanal isteyin. Şifresiz epostaya istismar ayrıntısı
veya sır koymayın. Bir bildirimin kapsamda olup olmadığını sormak için açık bir
konu açmayın; özel olarak sorun.

## Yanıt hedefleri

Bunlar hedeftir, sözleşmeye bağlı hizmet düzeyi değildir:

- üç iş günü içinde alındı bildirimi;
- yedi iş günü içinde ilk değerlendirme; ve
- doğrulanmış yüksek etkili bir bildirim için on dört iş günü içinde önerilen bir
  giderme ya da eşgüdüm planı.

Bildirimler yalnızca sentetik veriye karşı doğrulanır, ki bu projenin konusunun
tamamı da odur. Her düzeltmeye bir gerileme testi eşlik eder.

## Güvenlik sınırları

Mintmark yerel bir üreteçtir. Bir paket okur, dosya yazar ve hiçbir ağ girdisi
veya çıktısı gerçekleştirmez. Tehdit modeli de bundan çıkar.

**Kapsam içi.** Kod çalıştırmaya, çıktı dizininin dışına yol geçişine ya da sıkı
bir yükleyicinin reddetmesi gereken kaynak tüketimine yol açan bir paket. Sağlaması
geçerli bir kimlik içeren güvenli mod çıktısı. Kurcalanmış veriye karşı doğrulanan
bir künye. Baytlar farklıyken başarı bildiren bir `verify` veya `reproduce`
sonucu. Üretim sırasında yapılan her ağ çağrısı. Özel materyalin derlenmiş bir
çıktıya ulaşabileceği her yol.

**Kapsam dışı.** Üretilen verinin gerçekçiliği, ki bu güvenlik değil kalite
sorusudur. Üretilen bir telefon numarasının tahsis edilmiş bir numaraya rastlantı
eseri benzemesi, ki Türkiye numaralandırma planının bilinen bir sınırlılığı olarak
README'de belgelenmiştir. Bir tüketicinin üretilmiş bir veri kümesiyle, o bu
araçtan çıktıktan sonra yaptığı her şey.

**Açıkça güvenlik açığı olmayan.** Doğrulayıcı modun sağlaması geçerli kimlikler
üretmesi. Bu onun belirtilmiş amacıdır, her üretimde tercihe bağlıdır ve böyle
her veri kümesi künyesinde bir uyarı bloğu taşır. Doğrulayıcı modun belgelendiği
gibi çalıştığını bildiren bir rapor, bu paragrafa yönlendirilerek kapatılır.

## Bu projenin iddia etmedikleri

Mintmark hiçbir düzenleme kapsamında uyum garantisi vermez. Gerçek verinin
anonimleştirmesi değildir. Kullanmak, tek başına hiçbir alt sistemi hukuka uygun
kılmaz.
