# Yönetişim

<sub><a href="GOVERNANCE.md">English</a></sub>

Bu dosya, bu depoda kararların bugün nasıl alındığını anlatır; eninde sonunda
nasıl alınmasını istediğimizi değil.

## Mevcut durum, açıkça

Mintmark kurucu yönetimindedir ve tek bakımcısı vardır. Bağımsız bakımcı gözden
geçirmesi şu anda mümkün değildir. Bu gerçek bir sınırlılıktır ve yalnızca tek
katılımcısı olan bir gözden geçirme süreciyle gizlenmek yerine burada kayda
geçirilmiştir.

## Yönetim ilkeleri

1. Yetki modelin dışında kalır. Bu projede hiçbir şey bir kararı üretilmiş bir
   çıktıya devretmez.
2. Davranışa dair her iddia, kayda geçirilmiş bir gözleme dayanır.
3. Yerleşik kararlar yalnızca uygulama kanıtı onlarla çeliştiğinde yeniden
   açılır ve değişiklik, eskisinin düzeltilmesi olarak değil yeni bir karar
   olarak kayda geçirilir.
4. Varsayılan anlatım tonu ölçülülüktür, özellikle bir düzenlemenin yakınında.

## Roller

**Katkıcı.** Bir konu veya çekme isteği açan herkes. Önceden bir ilişki
gerekmez.

**Gözden geçiren.** Sürdürülmüş ve isabetli gözden geçirme çalışmasının ardından
adlandırılmış bir kapsamda gözden geçirmeye davet edilen katkıcı. Gözden
geçirenler birleştirme yapmaz.

**Bakımcı.** Adlandırılmış bir kapsamda birleştirme ve sürüm yetkisini elinde
tutar. `MAINTAINERS.md` içinde o kapsamla birlikte listelenir.

## Karar sınıfları

| Sınıf | Örnekler | Kim karar verir |
| --- | --- | --- |
| Rutin | Hata düzeltmesi, test, belge düzeltmesi, bağımlılık yükseltmesi | Bakımcı birleştirmesi |
| Esaslı | Yeni bir komut satırı yüzeyi, şema değişikliği, yeni çalışma zamanı bağımlılığı, değişmez değişikliği | Değişiklik günlüğüne ve mimari ise numaralı bir karar olarak geçirilen bakımcı kararı |
| Yerleşik aile kararı | Topoloji, kimlik politikası varsayılanları, taksonomi sabitlemesi, lisanslama, model kullanmama kuralı | Burada karara bağlanmaz. Bunlar aile bildirgesinden gelir ve yalnızca açık bir aile düzeyi kararla değişir |
| Dış yetki | Depo oluşturma, yayımlama, sürümler, ad dondurma, bir düzenlemeye atıf yapan her cümle | Bakımcı kararı değildir. Sahibin kayıt altına alınmış onayını gerektirir |

## Kurucu yönetiminde birleştirme kuralı ve onun yerini alan denetim

Tek bir bakımcı bulunduğu sürece, o bakımcı kendi değişikliklerini
birleştirebilir. Bunu telafi eden denetim şudur: zorunlu CI yeşil olmadan hiçbir
birleştirme geçmez ve değişmez paketi, bir kusurla ana dal arasında duran şeyin
gözden geçiren değil kontroller olacağı biçimde yazılmıştır.

İkinci bir bakımcı katıldığında bu kural kaldırılır ve esaslı değişiklikler için
iki taraflı gözden geçirme uygulanır. Tetikleyici budur, bir tarih değil.

## Sürümler

Sürümler bir bakımcı tarafından çıkarılır, yayımlandıktan sonra değiştirilemez ve
sahibin kayıt altına alınmış onayının arkasındadır. Yayımlama kimlik bilgileri bu
depoda hiçbir zaman uzun ömürlü belirteçler değildir; yayımlama OIDC üzerinden
güvenilir yayımlama ile yapılır.

## Süreklilik

Tek bakımcı erişilemez hâle gelirse, depo sessizce devredilmek yerine arşive
kaldırılır. Dürüst bir bildirim taşıyan arşivlenmiş bir depo, kullanıcıları için
canlı görünen bakımsız bir depodan iyidir.
