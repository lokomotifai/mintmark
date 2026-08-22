# Mintmark

**Deterministik, tamamen sentetik, Türkçe öncelikli veri kümeleri basar: span
düzeyinde kişisel veri etiketleri ve bir köken manifestosu ile birlikte.**

> **Önemli: bu araç ne değildir.**
>
> Mintmark, gerçek verinin anonimleştirilmesi veya maskelenmesi değildir. Gerçek
> veri okumaz ve gerçek veriyi güvenli hale getiremez.
>
> Hukuki tavsiye değildir, uyumluluk garantisi değildir. Yazılımın ne yaptığını
> anlatır; bunu kendi yükümlülüklerinize eşlemek bu aracın değil sizin işinizdir.
>
> Sentetik gerçekçiliğin sınırları vardır. Veri, beyan edilen dağılımlar ve
> derlenmiş sözlüklerle şekillenir; gerçek bir popülasyona uydurulmaz. Buradan
> çıkarılan istatistiksel sonuçları, beyanlar hakkında sonuçlar olarak okuyun.
>
> Üretilen telefon numaraları atanmış numaralarla çakışabilir. Türkiye numara
> planı kurgusal bir mobil aralık ayırmadığı için bu mühendislikle çözülemez. Bu
> veri sistemleri test etmek içindir. Hiçbir zaman kimseye ulaşmak için değildir.

## Hızlı başlangıç

Bağımlılık kurulumundan sonra çevrimdışı. Anahtar yok, hesap yok, ağ yok.

    uv tool install mintmark        # veya: pip install mintmark
    mintmark mint --pack packs/example --recipe demo --seed 42 --out ./demo-run
    mintmark verify ./demo-run

`demo-run/` şunları içerir:

    customer.jsonl                 100 kayıt, satır başına bir JSON nesnesi
    transaction.jsonl              100 kayıt, her biri işlenmiş bir açıklama ile
    transaction.labels.jsonl       her açıklamaya span uzaklıkları
    MINTMARK.json                  köken manifestosu
    SHA256SUMS                     üretilen her dosya için bir sağlama toplamı

ve `mintmark verify` şunu bildirir:

    manifest schema: valid
    checksums: 3/3 match
    identifier policy: safe (confirmed)
    checksum-valid identifiers found: 0
    taxonomy: hushmark-tr v0.1, pin af11b31e4916
    label alignment: 100 documents, 81 spans

Aynı komutu iki kez çalıştırın, veri dosyaları bayt bayt aynıdır.
`mintmark reproduce ./demo-run` manifestodan yeniden basar ve karşılaştırır.

## Ne elde edersiniz

Basılmış bir veri kümesi şunlardan oluşur: veri dosyaları, her belge tipi için
bir etiket dosyası, bir manifesto ve sağlama toplamları. Manifesto motor
sürümünü, paket kimliğini ve özetini, tarifi, tohumu, tanımlayıcı politikasını,
taksonomi pinini, her çıktının sağlama toplamını ve basımın fiilen ulaştığı
dağılımları birbirine bağlar. Manifestosu olmayan bir veri kümesi Mintmark
teslimi sayılmaz, çünkü dosyaları onları üretenle bağlayan hiçbir şey kalmaz.

Etiketler on sekizlik kapalı bir kümeden gelir: hushmark-tr v0.1 taksonomisinin
on iki adlandırılmış varlık tipi, artı TCKN, VKN, IBAN, PAN, PHONE ve EMAIL.
Bilinmeyen bir etiket her yerde kapalı biçimde reddedilir.

## Tanımlayıcılar varsayılan olarak checksum geçersizdir

Her tanımlayıcı motorunun iki modu vardır.

`safe` varsayılandır. Biçim olarak makul ama kanıtlanabilir şekilde checksum
geçersiz değerler üretir; dolayısıyla üretilen bir tanımlayıcı gerçek olamaz.
IBAN'lar atanmamış olduğu doğrulanmış bir banka kodu taşır; kart numaraları
hiçbir ticari ağın kullanmadığı bir sektör tanımlayıcısıyla başlar; e-posta
adresleri yalnızca kimsenin kaydettiremeyeceği rezerve alan adları altındadır.

`validator` checksum geçerli değerler üretir. Kendi doğrulama mantığınızı
geçerli bir şeye karşı test edebilesiniz diye vardır. Basım başına opsiyoneldir
ve bu modda basılan her veri kümesi manifestosunda bir uyarı bloğu taşır;
`verify` bu bloğun eksikliğini kabul etmez.

## Determinizm ve tam olarak neyin iddia edildiği

Aynı motor sürümü, paket özeti, tarif, tohum, tanımlayıcı politikası ve çıktı
biçimi; CPython 3.12 üzerinde Linux x86_64, Linux arm64 ve macOS arm64'te bayt
bayt aynı veri dosyalarını ve etiket dosyalarını üretir.

Manifestonun `provenance` bloğu, yani oluşturma zaman damgası ve çağrı satırı,
hariçtir. Manifestodaki diğer her şey dahildir.

Windows iddia edilmez ve test edilmez.

Bu iddia, üretilen veride kayan noktalı sayı kullanılmamasının, basım yolunda
hiçbir transandantal fonksiyon çağrılmamasının ve hiçbir yerde model
kullanılmamasının nedenidir.

## Proje durumu

Sürüm 0.1, ön yayın. Semantik sürümleme altındaki kamusal yüzey şunlardır:
komut satırı grameri, çıkış kodları, `--json` yükleri, kütüphanenin iki
fonksiyonu, paket şeması, manifesto şeması ve sabit bir tohumun ürettiği
baytlar. Sonuncusu vurgulanmayı hak eder: sabit bir tohum için üretilen
baytları değiştiren bir değişiklik, hiçbir imza değişmese bile ana sürüm
olayıdır, çünkü yayımlanmış her manifestonun yeniden üretilebilirliğini bozar.

Mintmark adı marka taraması tamamlanana kadar geçicidir. Henüz hiçbir paket
deposuna yayın yapılmamıştır ve bu belge yapıldığına dair bir iddia taşımaz.

## Sektör paketleri

Motor, hızlı başlangıç ve testler tarafından kullanılan tek bir örnek paket ile
gelir. Bu paket açıkça bir sektör paketi değildir.

Sektör paketleri, motor kodu içermeyen, bildirim ve veri taşıyan ayrı
depolardır: `mintmark-banking`, ardından `mintmark-insurance`, ardından
`mintmark-hr`. Her biri bu motoru kapalı üst sınırlı bir sürüm aralığıyla
sabitler ve sürüm eki olarak sürümlenmiş bir referans veri kümesi yayımlar.

## Bu neden var

hushmark-tr model kartı, benimseyenlerden dedektörü üretimde kullanmadan önce
temsili veriyle değerlendirmelerini ister. Türk kurumları bunu KVKK riski
almadan üretim verisiyle yapamaz ve yerine koyacak gerçekçi bir şeyleri
olmamıştır. Mintmark tam olarak o değerlendirme verisini üretir: aynı kapalı
taksonomiye göre etiketlenmiş, hiçbir aşamasında gerçek kişisel veri
kullanılmadan.

## Belgeler

- [docs/determinism.md](docs/determinism.md), iddia ve bir veri kümesinin nasıl yeniden üretileceği
- [docs/taxonomy.md](docs/taxonomy.md), etiket kümesi, pin ve sapma prosedürü
- [docs/normative-verification.md](docs/normative-verification.md), neyin hangi kaynağa karşı ne zaman doğrulandığı
- [docs/engineering-notes.md](docs/engineering-notes.md), katkıda bulunanlar için operasyonel bilgi

## Lisans ve marka

Kod Apache-2.0'dır. Bakınız [LICENSE](LICENSE) ve [NOTICE](NOTICE).

Lisans, Mintmark adı veya logosu üzerinde hiçbir hak vermez. Bakınız
[TRADEMARKS.md](TRADEMARKS.md).

For English, see [README.md](README.md).
