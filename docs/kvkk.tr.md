# Mintmark ve KVKK

<sub><a href="kvkk.md">English</a></sub>

Bu projenin var olma nedeni Türk veri koruma hukukudur; dolayısıyla konu bir
README'nin içine gömülmüş bir cümleyi değil, açık bir beyanı hak ediyor.

**Bu hukuki tavsiye değildir.** Bu proje ne üretir, ne üretmez, onun bir
tarifidir; kendi hukuk danışmanınızın değerlendirebileceği somut bir şey olsun
diye yazılmıştır.

## Kanun

Kişisel Verilerin Korunması Kanunu, kanun numarası 6698, 2016'dan bu yana
yürürlükte ve Mart 2024'te değiştirildi. Kişisel veriyi, kimliği belirli veya
belirlenebilir gerçek kişiye ilişkin bilgi olarak tanımlar ve bir grup kategoriyi
daha sıkı bir rejime ayırır.

## Sentetik verinin neden ayrı bir soru olduğu

Kişisel verinin bir ilgili kişisi vardır: bilginin ilişkin olduğu gerçek bir
kişi. Bu projenin ürettiği verinin böyle biri yoktur.

Her değer, bir tohumdan belirlenimci bir fonksiyonla hesaplanır. Hiçbir gerçek
kayıt okunmaz, gerçek kayıtlarla eğitilmiş hiçbir model devrede değildir ve
gerçek bir kişinin verisi kurgusal bir veriye dönüştürülmez. Bir değerin
karşılık geldiği bir asıl yoktur, kimseye geri götüren bir yeniden kimliklendirme
yolu yoktur ve hakları buna bağlanan bir kişi yoktur.

Bu, verinin nasıl üretildiğine dair bir beyandır ve iddia edilmekle kalmaz,
doğrulanabilir: künye motor sürümünü, paket digest'ini, tarifi ve tohumu kayda
geçirir; `mintmark reproduce` de bunlardan aynı baytları yeniden türetir.

Bu, anonimleştirmeden farklıdır ve fark önemlidir. Anonimleştirilmiş veri, bir
zamanlar birinin kişisel verisiydi. Bu hiçbir zaman olmadı.

## Özel nitelikli kategoriler ve nasıl etiketlendikleri

Altıncı madde daha sıkı bir rejime tabi kategorileri sayar: ırk ve etnik köken,
siyasi düşünce, felsefi inanç, din, mezhep veya diğer inançlar, kılık ve kıyafet,
dernek, vakıf ya da sendika üyeliği, sağlık, cinsel hayat, ceza mahkûmiyeti ve
güvenlik tedbirleri ile biyometrik ve genetik veriler.

Bu projenin sabitlediği taksonomi bunların çoğu için etiket taşır, çünkü bir
dedektör, veri kümesinin hiç içermediği bir şey üzerinden ölçülemez:

| Altıncı madde kategorisi | Bu taksonomideki etiket |
| --- | --- |
| Irk, etnik köken | `ETHNICITY` |
| Siyasi düşünce | `POLITICAL` |
| Felsefi inanç, din, mezhep, diğer inançlar | `RELIGION` |
| Sendika üyeliği | `UNION` |
| Sağlık | `HEALTH` |
| Cinsel hayat | `SEXUAL_LIFE` |
| Ceza mahkûmiyeti ve güvenlik tedbirleri | `CRIMINAL` |
| Biyometrik veri | `BIOMETRIC_REF` |
| Kılık ve kıyafet | etiket yok |
| Dernek veya vakıf üyeliği | etiket yok; `UNION` yalnızca sendikaları kapsar |
| Genetik veri | etiket yok |

Üç boşluk, keşfedilmeye bırakılmak yerine belirtiliyor. Bu veri kümelerine karşı
değerlendirilen bir dedektör o üçü üzerinden değerlendirilmemiş olur ve bu
projeden çıkan bir kapsam sayısı onları kapsıyormuş gibi okunmamalıdır.

**Bu veride `HEALTH` etiketli bir aralık, kimse hakkında sağlık verisi
değildir.** Kurgusal bir belgedeki kurgusal bir ifadedir ve bir dedektörün onu
bulup bulmadığı puanlanabilsin diye etiketlenmiştir. Etiket, bir dedektörün
tanıması gereken kategoriyi tarif eder; bir kişi hakkındaki bir olguyu değil.

## Bu projenin iddia etmedikleri

Uyum garantisi değildir. Hiçbir veri kümesi bir sistemi hukuka uygun kılmaz ve
buradaki hiçbir şey hiçbir şeye karşı savunma değildir.

Sizin verinizin anonimleştirmesi değildir. Bu proje hiçbir veri almaz. Gerçek
kayıtları güvenli hâle getirmeniz gerekiyorsa bu başka bir sorundur ve bu araç o
araç değildir.

Sizin işleme faaliyetiniz hakkında hiçbir şey söylemez. Sisteminizin gerçek
kişisel veriyi ele alışının kanunu karşılayıp karşılamadığı; sisteminize,
amacınıza, hukuki sebebinize ve güvenlik tedbirlerinize bağlıdır. Bunların hiçbiri
buradan görünmez.

## Size verdiği şey

Gerçek kayıtları taşımadan doldurabileceğiniz bir test ortamı ve bir dedektörü
ölçebileceğiniz bir değerlendirme kümesi. Ekiplerin üretim verisini kopyalamaya
en sık başvurduğu iki yer bunlardır ve ikisi de kaçınılabilirdir.

## Veri almadan önce bilinmesi gereken iki sınır

**Kimlik politikası.** Varsayılan `safe`, yani üretilen değerler kendi
sağlamalarını kasten geçemez; böylece üretilen hiçbir şey tahsis edilmiş bir
kimlikle karıştırılamaz. Kendi doğrulama mantığını test eden ekipler için tercihe
bağlı bir `validator` politikası sağlaması geçerli değerler üretir; böyle her
veri kümesi künyesinde bir uyarı taşır ve bu projenin yayımladığı her referans
veri kümesi `safe` ile üretilir.

**Telefon numaraları.** Türkiye numaralandırma planı kurgusal bir aralık
ayırmaz; dolayısıyla üretilen bir numara tahsis edilmiş bir numarayla
çakışabilir. Bu verideki bir numarayı asla aramayın. Bu, README'de bilinen bir
sınırlılık olarak kayıtlıdır ve projenin içinden düzeltilebilir değildir.

## Bir sorunu bildirmek

Buradaki bir veri kümesinin gerçek bir kişiye ilişkin bir şey içerdiğini
düşünüyorsanız, bu bir hata bildirimi değil güvenlik sorunudur.
[SECURITY.md](../SECURITY.md) içindeki özel yolu kullanın.
