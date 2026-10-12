# Yapay Zeka Kullanım Notu

Bu projede yapay zeka aracı olarak Claude'u kullandım. Aşağıda neyi ona yaptırdığımı,
neyi kendim yaptığımı ve nasıl doğruladığımı yazdım.

## 1\. Başlangıç

Hocanın paylaştığı şemayı Claude'a gösterip sistemden tam olarak ne beklendiğini
sordum. Bana gereksinimleri ve dört parçalı bir mimari özet çıkardı: monitor, protokole
özel checker'lar, SQLite depolama ve dashboard.

## 2\. Kararlar (kim önerdi?)

* **Python:** Claude önerdi. Hocanın dil kısıtı olmadığını ben söyledim, öneriyi kabul ettim.
* **Üst üste 3 hata eşiği:** Claude önerdi (tek bir hatalı kontrolde dashboard yanıp
sönmesin diye), ben kabul ettim.
* **SQLite:** Hocanın notlarında zaten vardı.
* **Mock servisler + chaos runner birlikte:** Hocanın notlarındaki iki seçeneği
birleştirmeyi Claude önerdi, ben kabul ettim.

## 3\. Kim ne yaptı?

* **Claude yazdı:** monitor, checker'lar (HTTP ve gRPC), SQLite katmanı, mock servisler,
chaos runner, dashboard, README ve testler.
* **Ben yaptım:** dosyaları klasöre yerleştirdim, sanal ortamı ve kütüphaneleri kurdum,
bileşenlerin hepsini kendi bilgisayarımda (Windows, Python 3.11) çalıştırdım ve
sonuçları ekran görüntüleriyle Claude'a gösterdim.

## 4\. Doğrulama

* Mock servisleri, monitor'ü ve dashboard'u birlikte çalıştırdım.
* Chaos'u hem `chaos\_runner.py` ile hem de elle (ProductService'i `error` moduna
alarak) tetikledim. Dashboard'da kartın kırmızı DOWN olduğunu, kesinti geçmişine
"devam ediyor" satırı eklendiğini, servis düzelince kartın yeşile dönüp satırın
süresinin (56 sn) kapandığını gördüm. Ekran görüntüleri screenshots/ klasöründe.
* Testleri çalıştırdım: `python -m pytest -v` sonucu `11 passed`.

## 5\. Karşılaştığımız sorunlar

* Dashboard'daki ilk ekran görüntüsünde yanıt süreleri çok yüksekti (300-1000 ms).
Bunu paylaştığım görüntüden Claude fark etti. Sebebi, her kontrolde HTTP istemcisinin
yeniden oluşturulmasıydı; düzeltince süreler birkaç milisaniyeye indi.
* Sonraki bir ekran görüntüsünde chaos çalışmazken bir servis "HATALI" görünüyordu
(`Server disconnected without sending a response`). Claude bunu, yeniden kullanılan
bağlantıların sunucu tarafından kapatılmasına bağladı ve keep-alive'ı kapatan bir
düzeltme ekledi. Sorunu kendi ortamında yeniden üretemediği için sebep kesin
doğrulanmış değil.

## 6\. Bilinen sınırlar

* Chaos, servisi gerçekten kapatmıyor; yalnızca HTTP 500, yavaş yanıt ve aralıklı hata
simüle ediyor.
* SOAP servisleri için şu an SOAP isteği yerine yalnızca `/health` üzerinden HTTP
kontrolü yapılıyor.
* Servis listesi `config.yaml`'dan okunuyor, çalışırken değiştirilemiyor.

