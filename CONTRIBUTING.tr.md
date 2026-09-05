# Katkı

<sub><a href="CONTRIBUTING.md">English</a></sub>

Katkıda bulunmayı düşündüğünüz için teşekkürler. Bu proje küçüktür ve gözden
geçirme disiplini bilinçlidir; çekme isteği açmadan önce bunu okuyun.

## Commit'lerinizi imzalayın

Katkılar Developer Certificate of Origin, sürüm 1.1 kapsamında kabul edilir.
Katkıcı lisans sözleşmesi yoktur. Her commit, commit yazarıyla eşleşen bir imza
satırı taşır:

    git commit -s -m "mesajınız"

İmzasız commit taşıyan bir çekme isteği, imzalanana kadar birleştirilmez.

## Çekme isteği açmadan önce

Zorunlu CI'ın çalıştırdığı kontrollerin aynısını çalıştırın. Bağımlılıklar
kurulduktan sonra hepsi çevrimdışı çalışır. `pyproject.toml` 0.12 serisindeki
her uv'yi kabul eder; zorunlu CI 0.12.3 çalıştırır.

    uv sync
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy --strict src/
    uv run lint-imports
    uv run pytest
    uv run python tools/mdlint.py .

## Metin için dil kuralları

Bunlar zorunlu CI'da `tools/mdlint.py` tarafından, her dilde uygulanır:

1. Başlıklar cümle düzenindedir.
2. Bir tanıtım terimleri listesi, İngilizce ve Türkçe olarak yasaktır. Liste
   `tools/mdlint.py` içindedir ve esas kaynak odur.
3. Uzun tire ve orta tire, depo metinlerinde hiçbir zaman geçmez. Kısa çizgi
   serbesttir.

Alıntılanan üçüncü taraf metni, gerekçe taşıyan bir muafiyet işaretiyle muaf
tutulur. Gerekçesiz bir muafiyet lint hatasıdır.

## Türkçe ayna

`README.md` esas metindir ve `README.tr.md` özet değil tam bir aynasıdır. Birini
diğeri olmadan değiştirmek gözden geçirmede reddedilir. Türkçesini yazmakta
rahat değilseniz çekme isteğinde bunu belirtin, halledilir; aynayı bayat
bırakmayın. Aynı kural bu deponun diğer `.tr.md` aynaları için de geçerlidir.

## Bir değişikliği kabul etmeyi kolaylaştıran şey

Değişen gözlemlenebilir davranışı ve bunu kanıtlayan komutu belirtin. Üretim
yoluna dokunan bir değişiklik ayrıca sabit bir tohum için bayt düzeyindeki
çıktıya etkisini belirtir, çünkü değişikliğin majör bir sürüm olayı olup
olmadığını bu belirler.

## Reddedilecek olanlar

Kayıt altına alınmış bir karar olmadan çalışma zamanı bağımlılığı ekleyen
değişiklikler. Üretim yolunun herhangi bir yerine model koyan değişiklikler.
Herhangi bir biçimde gerçek veri alan değişiklikler. Bir değişmezi daha sıkı
biriyle değiştirmek yerine zayıflatan değişiklikler.
