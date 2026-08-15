# Scrapy — دليل المستودع بالعربية

> **حالة هذا الدليل:** كُتب اعتمادًا على المستودع `ysrg2003/scrapy` عند الإصدار `2.17.0` والالتزام `06af687662112027b4482d31e2714a3cf280a91f`، وعلى التوثيق الرسمي لـ Scrapy. قد تتغير التفاصيل عند الانتقال إلى التزام أحدث.

## 1. ما هو Scrapy؟

Scrapy إطار عمل مرتفع المستوى مكتوب بلغة Python لبناء الزواحف التي تزور صفحات الويب وتستخرج منها بيانات منظَّمة. صُمم أساسًا للاستخلاص من الويب، لكنه يصلح أيضًا لاستهلاك بعض واجهات البرمجة وبناء زواحف عامة لأغراض مثل جمع البيانات والمراقبة والأرشفة والاختبارات الآلية [1]. لا يُعد Scrapy قاعدة بيانات أو خدمة استضافة بحد ذاته؛ فهو ينفذ دورة الزحف والاستخراج، بينما تحدد أنت طريقة التخزين أو التصدير أو التكامل مع خدمة خارجية.

يعمل Scrapy بأسلوب غير حاجب يعتمد على Twisted. يرسل عدة طلبات وفق إعدادات التزامن والتهذيب، ويمرر الاستجابات إلى العنكبوت لاستخراج العناصر والطلبات الجديدة، ثم يرسل العناصر إلى خطوط المعالجة أو مصدّرات الملفات [2].

### النتيجة الأولى التي سيحققها القارئ

بعد اتباع هذا الدليل ستتمكن من إنشاء بيئة افتراضية، تثبيت نسخة المستودع محليًا، إنشاء مشروع Scrapy، كتابة عنكبوت صغير، تشغيله، وتجهيز الناتج في ملف JSON Lines. لا يحتاج هذا المسار الأول إلى مفتاح API أو كلمة مرور أو حساب خدمة؛ الاعتماديات الخارجية لا تصبح مطلوبة إلا عند اختيار تكامل اختياري مثل S3 أو Google Cloud Storage أو FTP أو وكيل محمي.

## 2. المتطلبات

| المتطلب | الحالة | التفاصيل |
| --- | --- | --- |
| Python | مطلوب | الإصدار 3.10 أو أحدث. يدعم المشروع CPython وPyPy وفق دليل التثبيت الرسمي [3]. |
| Git | مطلوب للمساهمين | مطلوب لاستنساخ المستودع والعمل على فروعه. |
| بيئة افتراضية | موصى بها بشدة | تمنع تعارض Scrapy واعتمادياته مع حزم Python النظامية [3]. |
| اتصال بالإنترنت | مطلوب للتثبيت والتشغيل الشبكي | يحتاج `pip` إلى الوصول إلى فهرس الحزم، ويحتاج العنكبوت إلى الوصول إلى الموقع المستهدف. |
| أدوات بناء النظام | حسب المنصة | قد تحتاج Linux إلى حزم تطوير، وقد تحتاج Windows إلى Microsoft C++ Build Tools، وقد تحتاج macOS إلى Xcode Command Line Tools [3]. |
| أسرار أو مفاتيح API | غير مطلوبة للمسار الأول | لا تُنشئ ملفًا سريًا لمجرد تشغيل المثال. أضف بيانات الاعتماد فقط عندما تفعل تكاملًا يحتاجها. |

## 3. خريطة المستودع

المستودع هو مصدر Scrapy نفسه، وليس مشروع زحف جاهزًا لموقع واحد. لذلك ستجد فيه نواة الإطار، التوثيق، الاختبارات، وقوالب المشاريع التي ينشئها أمر `startproject`.

| المسار | دوره |
| --- | --- |
| `scrapy/` | الحزمة البرمجية الأساسية، وتشمل المحرك، المجدول، المنزّل، العناكب، الطلبات والاستجابات، المحددات، خطوط المعالجة، الوسطاء، الإضافات، وإدارة الإعدادات. |
| `scrapy/cmdline.py` | نقطة التنفيذ الفعلية لأداة سطر الأوامر `scrapy`. |
| `scrapy/__main__.py` | يتيح تشغيل الأداة بصيغة `python -m scrapy`. |
| `scrapy/VERSION` | مصدر رقم الإصدار الذي يقرأه نظام البناء. |
| `scrapy/templates/` | قوالب المشاريع والعناكب التي تستخدمها أوامر الإنشاء. |
| `tests/` | اختبارات الوحدة والتكامل والسلوك، ومنها اختبارات أوامر CLI ومحرك الزحف. |
| `docs/` | التوثيق المحلي بصيغة reStructuredText، ويحتوي النسخة المحلية من دليل التثبيت والبرنامج التعليمي ومرجع الأوامر. |
| `pyproject.toml` | تعريف الحزمة، إصدار Python المطلوب، الاعتماديات، extras، نقطة الدخول، وإعدادات أدوات الاختبار والتحقق. |
| `tox.ini` | بيئات الاختبار والتحقق الآلي للمساهمين. |
| `.github/workflows/` | سير عمل GitHub Actions للاختبارات والنشر والتحقق على المنصات المختلفة. |
| `README.rst` و`INSTALL.md` | المدخل المختصر الرسمي وروابط التثبيت والتوثيق. |
| `SECURITY.md` | الإصدارات المدعومة وطريقة الإبلاغ عن الثغرات. |
| `CONTRIBUTING.md` | قواعد المساهمة في المشروع. |

## 4. التثبيت من نسخة المستودع

### 4.1 Linux وmacOS

نفِّذ الأوامر التالية في الطرفية. يبدأ المسار بالانتقال إلى مجلد العمل حتى لا تُنشأ البيئة الافتراضية في مكان غير مقصود.

```bash
git clone https://github.com/ysrg2003/scrapy.git
cd scrapy
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

أمر `-e .` يثبت نسخة تحريرية من المستودع؛ أي إن تعديلاتك على ملفات المصدر تنعكس في البيئة دون إعادة تثبيت الحزمة في كل مرة. أما إن أردت استخدام Scrapy كمستخدم عادي خارج هذا المستودع فاستخدم `python -m pip install Scrapy` داخل بيئة افتراضية، وهو المسار الذي يوصي به الدليل الرسمي [3].

**النتيجة المتوقعة:** بعد التثبيت يجب أن يعمل الأمر التالي ويعرض الإصدار ومعلومات الاعتماديات.

```bash
scrapy version -v
```

سيظهر سطر يبدأ بـ `Scrapy`، ويعرض في هذه النسخة `2.17.0`. إذا ظهر `command not found` فتحقق أولًا من تفعيل البيئة عبر `which python` و`which scrapy`. إذا كان `python` من خارج مجلد `.venv`، نفّذ `. .venv/bin/activate` من جذر المستودع ثم أعد المحاولة.

### 4.2 Ubuntu أو Debian عند فشل بناء الاعتماديات

تحتوي النسخ الحديثة من Python غالبًا على عجلات ثنائية جاهزة، لكن دليل Scrapy يذكر أن بعض الأنظمة قد تحتاج إلى أدوات التطوير الخاصة بـ `lxml` و`cryptography` [3]. عند ظهور أخطاء ترجمة أو غياب ملفات مثل `libxml/xmlversion.h` أو `openssl/ssl.h`، نفّذ ما يلي خارج البيئة الافتراضية:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-dev python3-pip libxml2-dev libxslt1-dev zlib1g-dev libffi-dev libssl-dev
```

ثم من جذر المستودع فعّل البيئة وأعد التثبيت:

```bash
. .venv/bin/activate
python -m pip install -e .
```

إذا استمر الفشل، احتفظ برسالة الخطأ كاملة؛ لا تستبدل هذه الحزم بحزمة Ubuntu القديمة `python-scrapy` لأن التوثيق الرسمي يحذر من أنها قد تكون أقدم من الإصدار الحالي [3].

### 4.3 Windows PowerShell

يوصي دليل Scrapy باستخدام Anaconda أو Miniconda على Windows لتقليل مشكلات بناء الاعتماديات [3]:

```powershell
conda create -n scrapy-env python=3.12
conda activate scrapy-env
conda install -c conda-forge scrapy
```

إذا كنت تعمل على نسخة المصدر نفسها وتريد تثبيتها تحريريا، استخدم PowerShell من جذر المستودع:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

قد يتطلب مسار `pip` على Windows تثبيت **Microsoft C++ Build Tools** مع مكونات MSVC وWindows SDK [3]. إذا رفض PowerShell تشغيل `Activate.ps1` بسبب سياسة التنفيذ، استخدم جلسة PowerShell مناسبة أو نفّذ التفعيل من `cmd.exe` عبر `.venv\Scripts\activate.bat`؛ لا تغيّر سياسة النظام تغييرا دائمًا لمجرد تشغيل المشروع.

### 4.4 PyPy وConda

يمكن تثبيت الحزمة من قناة `conda-forge` بالأمر التالي:

```bash
conda install -c conda-forge scrapy
```

أما PyPy فقد يبني بعض الاعتماديات من المصدر بدل استخدام عجلات CPython، ولذلك قد يحتاج إلى أدوات بناء إضافية. بعد التثبيت يمكن استخدام `scrapy bench` كفحص سريع لسلامة التشغيل [3].

## 5. أول تشغيل: إنشاء مشروع وعنكبوت

> نفِّذ هذا القسم داخل مجلد عمل منفصل عن جذر مستودع Scrapy، حتى لا تخلط بين مصدر الإطار ومشروع الزحف الذي ستنشئه.

### الخطوة 1: إنشاء مشروع جديد

```bash
mkdir -p ~/scrapy-work
cd ~/scrapy-work
scrapy startproject quotes_project
cd quotes_project
```

ينشئ الأمر مجلد `quotes_project` وملف `scrapy.cfg` وحزمة Python تحتوي على `items.py` و`middlewares.py` و`pipelines.py` و`settings.py` ومجلد `spiders/` [4].

تحقق من البنية:

```bash
find . -maxdepth 3 -type f | sort
```

ينبغي أن ترى على الأقل:

```text
scrapy.cfg
quotes_project/__init__.py
quotes_project/items.py
quotes_project/middlewares.py
quotes_project/pipelines.py
quotes_project/settings.py
quotes_project/spiders/__init__.py
```

إذا قال Scrapy إن المجلد موجود أو إن المشروع غير صالح، انتقل إلى `~/scrapy-work` وتأكد من اسم مجلد جديد، ولا تنفذ الأمر من داخل مجلد مشروع آخر إلا إذا كنت تعرف أثر ذلك.

### الخطوة 2: كتابة العنكبوت

أنشئ الملف `quotes_project/spiders/quotes.py` بالمحتوى التالي:

```python
import scrapy


class QuotesSpider(scrapy.Spider):
    name = "quotes"
    start_urls = ["https://quotes.toscrape.com/tag/humor/"]

    def parse(self, response):
        for quote in response.css("div.quote"):
            yield {
                "author": quote.css("small.author::text").get(),
                "text": quote.css("span.text::text").get(),
            }

        next_page = response.css('li.next a::attr("href")').get()
        if next_page is not None:
            yield response.follow(next_page, callback=self.parse)
```

في هذا المثال يعرّف `name` الاسم الذي سيستعمله أمر `crawl`، وتحدد `start_urls` الطلبات الأولى، ويستخرج `parse` البيانات بمحددات CSS، ثم يتبع رابط الصفحة التالية باستخدام `response.follow`. عند عدم العثور على عنصر، يعيد `.get()` القيمة `None` بدل كسر العنكبوت بفهرس غير موجود؛ وهذا يجعل المثال أكثر تحمّلًا لتغيرات الصفحة [1] [4].

### الخطوة 3: فحص العنكبوت قبل التشغيل

```bash
scrapy list
scrapy check quotes
```

ينبغي أن يعرض `scrapy list` الاسم `quotes`. أما `scrapy check quotes` فيشغّل اختبارات العقود إن كانت معرفة. إذا لم يظهر العنكبوت، تحقق من أن الملف داخل `quotes_project/spiders/` وأنه يحتوي على فئة ترث من `scrapy.Spider`، وأنك تنفذ الأمر من المجلد الذي يحتوي `scrapy.cfg`.

### الخطوة 4: تشغيل الزحف وحفظ الناتج

لإنشاء ملف جديد أو استبدال ملف موجود، استخدم `-O`:

```bash
scrapy crawl quotes -O quotes.jsonl
```

ولإضافة العناصر إلى ملف موجود، استخدم `-o`:

```bash
scrapy crawl quotes -o quotes.jsonl
```

يعني `-O` الاستبدال، بينما يعني `-o` الإضافة. وعند التشغيل المتكرر يفضل استخدام JSON Lines بامتداد `.jsonl`؛ فإضافة سجلات إلى ملف JSON تقليدي قد تجعله غير صالح نحويًا [4].

**النتيجة المتوقعة:** يجب أن ينتهي التشغيل برسالة إغلاق للعنكبوت وأن ينشأ `quotes.jsonl`، بحيث يكون كل سطر كائن JSON مستقلًا، مثل:

```json
{"author": "...", "text": "..."}
```

قد تظهر طلبات إلى `robots.txt` أو استجابات غير ناجحة بحسب الموقع والاتصال. لا تعتبر رمز HTTP واحدًا دليلًا كافيًا على نجاح الاستخراج؛ افحص كذلك عدد العناصر في السجل وحجم ملف الناتج.

## 6. استخدام Scrapy Shell لتجربة المحددات

قبل تعديل العنكبوت، جرّب المحددات في الصدفة التفاعلية:

```bash
scrapy shell "https://quotes.toscrape.com/page/1/"
```

داخل الصدفة:

```python
response.css("title::text").get()
response.css("div.quote span.text::text").getall()
response.xpath("//small[@class='author']/text()").getall()
```

يستخدم Scrapy محددات CSS وXPath، ويُرجع `.getall()` قائمة النتائج، بينما يعيد `.get()` أول نتيجة أو `None` عند عدم وجودها [4]. في Windows استخدم علامات اقتباس مزدوجة حول الرابط، خصوصًا إذا احتوى الرابط على `&`.

إذا أعاد المحدد قائمة فارغة، فالمشكلة غالبًا في تغير HTML أو في أن البيانات تُحمّل بواسطة JavaScript بعد وصول HTML الأول. افحص الاستجابة الخام، وجرب XPath، ثم راجع دليل التعامل مع المحتوى الديناميكي بدل افتراض أن المتصفح المرئي يساوي الاستجابة التي يراها Scrapy.

## 7. خريطة دورة التنفيذ

تتحكم **الآلة التنفيذية** في تدفق الزحف. تحصل على الطلبات الابتدائية من العنكبوت، وتضعها في **المجدول**، ثم تمررها إلى **المنزّل** عبر Downloader Middleware. يعيد المنزّل استجابة تمر مرة أخرى عبر الوسيط إلى الآلة، التي تسلمها إلى العنكبوت عبر Spider Middleware. ينتج العنكبوت عناصر وطلبات جديدة؛ تذهب العناصر إلى Item Pipeline وتعود الطلبات إلى المجدول حتى تنتهي قائمة العمل [2].

| المكوّن | المسؤولية |
| --- | --- |
| Engine | تنسيق تدفق البيانات وتشغيل المكونات وإطلاق الأحداث. |
| Scheduler | ترتيب الطلبات التي ستنفذ وتغذية الآلة بالطلب التالي. |
| Downloader | جلب الصفحات وإنشاء كائنات `Response`. |
| Spider | تفسير الاستجابات وإنتاج العناصر والطلبات الجديدة. |
| Downloader Middleware | تعديل الطلب قبل الإرسال أو الاستجابة بعد التنزيل، أو إسقاط الطلب، أو إرجاع استجابة بديلة. |
| Spider Middleware | معالجة مدخلات ومخرجات العنكبوت ومعالجة بعض الاستثناءات. |
| Item Pipeline | تنظيف العناصر والتحقق منها وتخزينها أو تمريرها إلى مكونات لاحقة. |
| Feed Export | تصدير العناصر إلى JSON أو JSON Lines أو CSV أو XML أو مخازن مدعومة. |

## 8. أوامر CLI المهمة

تبحث أداة `scrapy` عن `scrapy.cfg` في مسارات النظام والمستخدم وجذر المشروع، وتمنح إعدادات المشروع أولوية أعلى من الإعدادات العامة. وتدعم كذلك متغيرات بيئية لتحديد وحدة الإعدادات أو المشروع أو غلاف Python [5].

| الأمر | يحتاج مشروعًا؟ | الاستخدام |
| --- | ---: | --- |
| `scrapy startproject NAME` | لا | إنشاء هيكل مشروع جديد. |
| `scrapy genspider NAME DOMAIN` | لا | توليد عنكبوت من قالب. |
| `scrapy crawl SPIDER` | نعم | تشغيل عنكبوت مسجل في المشروع. |
| `scrapy runspider FILE.py` | لا | تشغيل ملف عنكبوت مستقل دون مشروع. |
| `scrapy list` | نعم | عرض أسماء العناكب المكتشفة. |
| `scrapy check SPIDER` | نعم | تنفيذ اختبارات العقود. |
| `scrapy shell URL` | لا | تجربة الطلبات والمحددات تفاعليًا. |
| `scrapy fetch URL` | لا | جلب رابط بالطريقة التي يستخدمها Scrapy. |
| `scrapy settings --get NAME` | حسب الإعداد | قراءة قيمة إعداد. |
| `scrapy bench` | لا | قياس أداء سريع محلي. |
| `scrapy version -v` | لا | عرض إصدار Scrapy والاعتماديات والمنصة. |

يمكن تشغيل الأداة أيضًا بصيغة:

```bash
python -m scrapy version -v
```

### إعدادات المشروع والبيئة

يحتوي `scrapy.cfg` الذي ينشئه `startproject` عادةً على اسم وحدة الإعدادات:

```ini
[settings]
default = quotes_project.settings
```

ولا ينبغي وضع كلمات المرور أو مفاتيح API داخل هذا الملف. هذه هي المتغيرات العامة الأكثر ارتباطًا باكتشاف المشروع:

| المتغير | النوع | أثره | مثال آمن |
| --- | --- | --- | --- |
| `SCRAPY_SETTINGS_MODULE` | اسم وحدة Python | يحدد وحدة الإعدادات التي سيقرأها الأمر. | `quotes_project.settings` |
| `SCRAPY_PROJECT` | اسم مستعار | يختار مشروعًا غير `default` عندما يحتوي `scrapy.cfg` على أكثر من وحدة إعدادات. | `project2` |
| `SCRAPY_PYTHON_SHELL` | اسم غلاف | يحدد الغلاف التفاعلي المفضل عند توفره. | `python` |

هذه ليست أسرارًا بحد ذاتها، لكنها قد تشير إلى ملفات إعدادات تحتوي بيانات حساسة؛ احتفظ بالأسرار في مدير أسرار أو ملف محلي مستبعد من Git، ولا تطبع قيمها في السجلات.

## 9. الاعتماديات وextras الاختيارية

يعرّف `pyproject.toml` الاعتماديات الأساسية مثل Twisted وlxml وparsel وw3lib وcryptography وpyOpenSSL، كما يعرّف extras تُثبت مكونات إضافية عند الحاجة [6]. لا تثبت كل extras دون سبب؛ اختر فقط ما يطابق ميزة ستستخدمها.

| الإضافة | الميزة |
| --- | --- |
| `bpython` | غلاف Bpython. |
| `gcs` | Google Cloud Storage لتصدير الملفات وخطوط الوسائط. |
| `httpx` | معالج HTTPX مع HTTP/2 ودعم SOCKS. |
| `images` | خط معالجة الصور. |
| `ipython` | غلاف IPython. |
| `ptpython` | غلاف ptpython. |
| `robotparser` | محلل robots.txt بديل. |
| `s3` | تخزين Amazon S3 للتصدير والوسائط والتنزيلات. |
| `twisted-http2` | دعم HTTP/2 عبر Twisted. |
| `uvloop` | حلقة أحداث uvloop في الأنظمة المدعومة. |
| `zstd` | فك ضغط استجابات Zstandard. |

مثال تثبيت ميزتين فقط:

```bash
python -m pip install -e '.[s3,images]'
```

تثبيت `s3` لا يمنحك حساب AWS ولا ينشئ صلاحياته؛ ستظل بحاجة إلى إعداد اعتماديات AWS وفق بيئتك، ويجب عدم وضع المفاتيح في المستودع. وبالمثل، اختيار `gcs` أو `httpx` لا يعني أن التكامل سيعمل دون إعداد الخدمة أو الشبكة المطلوبة.

## 10. التطوير والاختبار

للتطوير من المصدر استخدم التثبيت التحريري داخل `.venv` كما في القسم الرابع. يعرّف المستودع اعتماديات الاختبار وبيئاتها في `tox.ini`، ويُستخدم `tox` لتشغيل مصفوفة التحقق التي تشمل Python وmypy وpylint والتوثيق واختبارات الوحدات [7].

للفحص السريع بعد تثبيت اعتماديات الاختبار الأساسية:

```bash
python -m pip install pytest pytest-cov pytest-twisted
python -m pytest -q tests/test_command_version.py tests/test_command_startproject.py
```

ولتشغيل بيئة Python 3.12 المعرفة في إعدادات `tox.ini`:

```bash
python -m pip install tox
tox -e py312
```

يتطلب المسار الكامل أن تكون نسخة Python المطلوبة والأدوات التي يثبتها `tox` متاحة. إذا أردت اختبار التغيير في أمر واحد، ابدأ بالاختبار المقابل له بدل تشغيل كامل المصفوفة. بعد النجاح راجع أيضًا التنسيق والتحقق الساكن وفق أوامر المشروع المعرفة في `tox.ini`.

**نتيجة تحقق أُجريت على هذه النسخة:** استُخدمت Python 3.12.3، وثُبت المستودع بـ`pip install -e .`، ونجح `scrapy version -v`، ونجح `scrapy --help` خارج المشروع، ونجح اختبارا `test_command_version.py` و`test_command_startproject.py` بعد تثبيت اعتماديات الاختبار الدنيا بنتيجة `10 passed`. ظهرت تحذيرات إعداد مرتبطة بغياب `pytest-cov` في بيئة التحقق الدنيا، ولم تُعد هذه النتيجة تشغيلًا كاملًا لكل الاختبارات.

## 11. الأمان والامتثال التشغيلي

Scrapy يستطيع إرسال رؤوس HTTP وبيانات اعتماد وطلبات عبر بروكسيات أو خدمات تخزين؛ لذلك يجب اعتبار أي قيمة مثل كلمة مرور HTTP أو بيانات FTP أو مفاتيح S3 أو رموز الجلسة سرية. ضعها في متغيرات البيئة أو مدير أسرار أو إعدادات محلية مستبعدة من Git، وتحقق من أن السجل لا يطبع رؤوس `Authorization` أو عناوين تحتوي اسم مستخدم وكلمة مرور. لا تضع مفاتيح حقيقية في الأمثلة أو الاختبارات أو Issues.

احترم شروط استخدام الموقع وسياسة `robots.txt` ومعدلات الطلب المناسبة، ولا تجمع بيانات شخصية أو محمية إلا إذا كان لديك أساس مشروع وصلاحية واضحة. استخدم `DOWNLOAD_DELAY` أو حدود التزامن وAutoThrottle عند ملاءمة ذلك، واختبر أولًا على موقع تملكه أو على موقع التدريب المستخدم في الأمثلة. هذا الدليل يشرح تشغيل الإطار ولا يمنح إذنًا للوصول إلى أي موقع.

وفق `SECURITY.md`، الإصدار المدعوم في هذا المستودع هو فرع `2.17.x`، ويجب إرسال بلاغات الثغرات عبر [نموذج GitHub Security Advisory](https://github.com/scrapy/scrapy/security/advisories/new) بدل نشر تفاصيل الثغرة علنًا [8].

## 12. استكشاف الأخطاء

| العرض | السبب المرجح | الإجراء |
| --- | --- | --- |
| `scrapy: command not found` | البيئة الافتراضية غير مفعلة أو لم يثبت المشروع. | نفّذ `. .venv/bin/activate` ثم `python -m pip install -e .`، وتحقق من `which scrapy`. |
| فشل بناء `lxml` أو `cryptography` | غياب حزم التطوير أو المترجم. | طبّق حزم Ubuntu في القسم 4.2، أو استخدم Conda، أو ثبّت أدوات البناء المناسبة لمنصتك [3]. |
| `No active project` عند `crawl` | التنفيذ خارج مجلد يحتوي `scrapy.cfg`. | انتقل إلى جذر مشروع الزحف، أو استخدم `scrapy runspider path/to/spider.py` للملف المستقل. |
| لا يظهر العنكبوت في `scrapy list` | مسار الملف أو اسم الفئة أو الوراثة غير صحيح. | ضع الملف تحت `PROJECT/spiders/`، واجعل الفئة ترث من `scrapy.Spider` وتملك `name` فريدًا. |
| الناتج فارغ | المحدد لا يطابق HTML، أو المحتوى ديناميكي، أو الاستجابة غير ناجحة. | افحص `scrapy shell` و`response.status` و`response.text` ثم عدّل CSS/XPath. |
| إضافة `-o` إلى JSON أفسدت الملف | الإضافة إلى JSON تقليدي قد تنتج أكثر من قيمة JSON متجاورة. | استخدم `-O` للاستبدال، أو استخدم JSON Lines بامتداد `.jsonl` مع `-o` [4]. |
| خطأ `OP_NO_TLSv1_1` | عدم توافق إصدار Twisted مع pyOpenSSL. | أعد تثبيت Twisted مع إضافة TLS: `python -m pip install 'Twisted[tls]'` وفق دليل التثبيت [3]. |
| يفشل الطلب رغم نجاح المتصفح | الموقع يتطلب JavaScript أو جلسة أو رؤوسًا أو يحظر المعدل. | افحص الاستجابة الخام، خفّض معدل الطلب، وأضف المعالجة اللازمة دون تجاوز ضوابط الموقع أو شروطه. |

## 13. تنظيف البيئة وإعادة الضبط

لإيقاف البيئة الافتراضية، نفّذ:

```bash
deactivate
```

لحذف البيئة والملفات الناتجة محليًا من مشروع الزحف، تحقّق من المسار أولًا ثم نفّذ:

```bash
rm -rf .venv
rm -f quotes.json quotes.jsonl
```

لا تنفذ أمر الحذف إذا لم تكن داخل المجلد الصحيح. أما في مستودع Scrapy نفسه، فاحذف فقط ملفات البناء أو البيئات التي أنشأتها أنت، ولا تحذف `scrapy/` أو `tests/` أو `docs/`.

## المراجع

[1]: https://docs.scrapy.org/en/latest/intro/overview.html "Scrapy at a glance"
[2]: https://docs.scrapy.org/en/latest/topics/architecture.html "Scrapy architecture overview"
[3]: https://docs.scrapy.org/en/latest/intro/install.html "Scrapy installation guide"
[4]: https://docs.scrapy.org/en/latest/intro/tutorial.html "Scrapy tutorial"
[5]: https://docs.scrapy.org/en/latest/topics/commands.html "Scrapy command line tool"
[6]: https://github.com/ysrg2003/scrapy/blob/master/pyproject.toml "Repository pyproject.toml"
[7]: https://github.com/ysrg2003/scrapy/blob/master/tox.ini "Repository tox.ini"
[8]: https://github.com/ysrg2003/scrapy/blob/master/SECURITY.md "Repository security policy"
