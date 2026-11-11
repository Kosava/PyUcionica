# PyQt6 Learning Studio

Interaktivna desktop aplikacija za učenje Pythona i PyQt6 — za potpune početnike.
Korisnik čita lekciju u gornjem delu prozora, piše kod dole levo, pokreće ga i
odmah vidi rezultat dole desno.

**Status: svih 6 faza je završeno (verzija 0.7.0).** 41 kompletna lekcija
(Moduli 1–5, prvih 6 lekcija Modula 8 i završni projekat Kalkulator), tamna
tema, pretraga, omiljene lekcije, SQLite baza, paketi za Arch Linux i
PyInstaller, 312 testova.

---

## Instalacija i pokretanje

Postoje tri načina. Svi koriste istu bazu sa napretkom
(`~/.local/share/PyUcionica/pyqt6-learning-studio/pyqt6_learning_studio.db`).

### 1. Arch Linux paket (preporučeno na Arch-u)

```bash
cd pyqt6_learning_studio
packaging/make_dist.sh              # pravi izvorni paket i kopira ga u packaging/arch/
cd packaging/arch
makepkg -si                         # pokreće testove i samoproveru, pa instalira
```

Posle instalacije aplikacija je u meniju (kategorije Obrazovanje / Razvoj) i
pokreće se komandom `pyqt6-learning-studio`. Paket instalira:

| Putanja | Sadržaj |
|---|---|
| `/usr/share/pyqt6-learning-studio/` | aplikacija (prevedena u `.pyc`) |
| `/usr/bin/pyqt6-learning-studio` | pokretač |
| `/usr/share/applications/pyqt6-learning-studio.desktop` | stavka u meniju |
| `/usr/share/icons/hicolor/scalable/apps/pyqt6-learning-studio.svg` | ikona |

Zavisnosti: `python`, `python-pyqt6`, `qt6-svg`; opciono `python-qscintilla-qt6`.
Uklanjanje: `sudo pacman -R pyqt6-learning-studio` (napredak ostaje u `~/.local/share`).

> U PKGBUILD-u je `license=('LicenseRef-custom')` — upiši stvarnu licencu
> projekta pre objavljivanja paketa.

### 2. Iz izvornog koda

```bash
# Arch:
sudo pacman -S python-pyqt6 python-qscintilla-qt6 qt6-svg python-pytest
# ili bilo koji sistem, u virtuelnom okruženju:
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python main.py
```

Opcije: `--debug` (detaljniji zapis u terminalu), `--self-test` (samoprovera, vidi dole).

**Bez QScintille:** ako `PyQt6-QScintilla` nije instaliran, aplikacija sama prelazi
na ugrađeni rezervni editor (QPlainTextEdit) koji ima sintaksno bojenje, brojeve
linija, automatsko uvlačenje, Ctrl+/ i označavanje linije sa greškom.

### 3. Samostalan paket (PyInstaller)

```bash
pip install pyinstaller
packaging/build_pyinstaller.sh      # pravi dist/pyqt6-learning-studio/ i pokreće samoproveru
dist/pyqt6-learning-studio/pyqt6-learning-studio
```

Folder `dist/pyqt6-learning-studio/` (~180 MB, uključuje Python i Qt) može da se
kopira na drugi računar istog operativnog sistema. Korisnikov kod pokreće:

1. Python zadat u Podešavanjima (Pokretanje koda → Python), ako je zadat;
2. inače Python sa sistema (`python3`), ako postoji;
3. inače Python ugrađen u paket — tada programi mogu da koriste PyQt6 i module
   standardne biblioteke koje kurs koristi (math, random, json, sqlite3...).

> Paket je izgrađen i proveren na Linuxu (i sa sistemskim i sa ugrađenim
> Pythonom). Na Windows-u i macOS-u paket se pravi istom komandom na tom
> sistemu, ali tamo nije proveren.

---

## Testiranje

```bash
python -m pytest -q                                   # 248 testova, ~30 s
python -m pytest -q --cov=core --cov=database --cov=models --cov=ui   # pokrivenost (pytest-cov)
QT_QPA_PLATFORM=offscreen python main.py --self-test  # samoprovera instalacije
```

Testovi rade bez prikaza prozora (`QT_QPA_PLATFORM=offscreen`) i obuhvataju:

- **Sadržaj kursa:** rešenje svake lekcije prolazi proveru, a početni kod ne
  prolazi; tačan odgovor svakog kviz pitanja sa kodom je stvarni izlaz programa;
  „varanje“ (ručno upisan rezultat, preskočeni slučajevi) ne prolazi.
- **Tokove rada kroz pravi glavni prozor:** početna strana → lekcija → kod →
  provera → „završi i pređi dalje“ → ponovno pokretanje (napredak i kod su
  sačuvani); pokretanje sa unosom; greška sa objašnjenjem i označenom linijom;
  zaustavljanje programa; pitanja o nesačuvanom kodu (Otkaži / Odbaci / Sačuvaj);
  zatvaranje aplikacije; vraćanje početnog koda; omiljene i pretraga; GUI zadatak;
  promena teme uz čuvanje koda; čuvanje podešavanja između pokretanja.
- **Obradu grešaka:** oštećena baza, baza novije verzije, oštećen plan kursa,
  stari `progress.json`, interpreter koji ne postoji, greška u slotu PyQt6
  programa, vremensko ograničenje, previše izlaza.
- **Pokretanje programa:** isti testovi i za „ugrađeni“ Python spakovane aplikacije.

Svako curenje veze ka bazi u testovima je greška (`error::ResourceWarning` u
`pyproject.toml`), a test koji se zaglavi posle 60 s ispisuje gde stoji.

**Samoprovera** (`--self-test`) ne dira korisnikove podatke: učitava sve lekcije,
proverava bazu (u memoriji), pokreće kod izabranim interpreterom (izlaz, unos,
greška), radi proveru PyQt6 prozora i pravi glavni prozor. Koristi je i
`check()` u PKGBUILD-u i skripta za PyInstaller.

---

## Struktura projekta

```
pyqt6_learning_studio/
├── main.py                     ulazna tačka: baza, prenos starih podataka, tema, kurs
├── requirements.txt
├── pyproject.toml              metapodaci i podešavanja pytest-a
├── README.md
├── config/
│   └── settings.py             putanje, ograničenja izvršavanja, font editora
├── core/                       logika — bez crtanja interfejsa
│   ├── lesson_manager.py       plan kursa, učitavanje lekcija iz JSON-a, navigacija
│   ├── code_runner.py          pokretanje koda u zasebnom procesu (QProcess)
│   ├── error_explainer.py      traceback → objašnjenje na srpskom + broj linije
│   ├── exercise_checker.py     provera zadatka prema kriterijumima
│   ├── check_session.py        provera kroz više pokretanja (test slučajeva)
│   ├── course_progress.py      pregled napretka, stanje lekcija, preporuka sledeće
│   ├── quiz_manager.py         tok kviza: mešanje odgovora, bodovanje, prag prolaza (70%)
│   ├── lesson_search.py        pretraga kroz ceo sadržaj lekcija (bez obzira na kvačice)
│   ├── python_locator.py       izbor Python interpretera (sistemski / zadat / ugrađen u paket)
│   ├── self_test.py            samoprovera instalacije (--self-test)
│   ├── progress_manager.py     napredak u bazi: lekcije, kod, istorija provera i kvizova
│   └── settings_manager.py     korisnička podešavanja u bazi (tipovi, granice, podrazumevano)
├── database/
│   ├── schema.sql              šema SQLite baze (verzija 2: + omiljene lekcije)
│   └── database_manager.py     otvaranje, verzija šeme, transakcije, kopija, oporavak
├── models/                     dataclass modeli
│   ├── lesson.py               Module, LessonInfo, Lesson, Term, CodeStep
│   ├── exercise.py             Exercise, ExerciseType, CheckCriteria, TestCase, CodeRule
│   └── quiz.py                 QuizQuestion (choice / predict / output)
├── data/curriculum/
│   ├── course.json             10 modula, 78 lekcija (plan kursa)
│   ├── modul_01/lekcija_01..05.json   Uvod u programiranje
│   ├── modul_02/lekcija_01..07.json   Promenljive i tipovi podataka
│   ├── modul_03/lekcija_01..06.json   Operatori i uslovi
│   ├── modul_04/lekcija_01..09.json   Petlje i kolekcije
│   ├── modul_05/lekcija_01..07.json   Funkcije i organizacija koda
│   ├── modul_08/lekcija_01..06.json   Početak rada sa PyQt6 (lekcije 48–53)
│   └── modul_10/lekcija_01.json       Završni projekat: Kalkulator (lekcija 71)
├── ui/
│   ├── main_window.py          početna strana / radni prostor, povezivanje signala, podešavanja
│   ├── home_page.py            početna strana: napredak, „nastavi“, pregled modula
│   ├── lesson_browser.py       bočni panel „Sadržaj kursa“ (stablo sa stanjima lekcija)
│   ├── quiz_dialog.py          kviz: pitanje po pitanje, objašnjenja, pokretanje koda, rezime
│   ├── settings_dialog.py      podešavanja: izgled, editor, pokretanje koda, lekcije, podaci
│   ├── search_dialog.py        pretraga lekcija sa isečcima i istaknutim pogocima
│   ├── lesson_panel.py         gornja zona: lekcija, primer, zadatak, navigacija
│   ├── editor_panel.py         donja leva zona: editor + dugmad
│   ├── output_panel.py         donja desna zona: izlaz, status, greške, unos
│   ├── code_editor.py          CodeEditor (QScintilla ili rezervni editor)
│   ├── lesson_formatter.py     jednostavan format teksta lekcija → HTML
│   ├── theme.py                svetla i tamna paleta, „prema sistemu“, QSS šablon, boje sintakse
│   ├── icons.py                SVG ikone obojene prema temi
│   └── widgets/feedback_card.py  kartica za objašnjenje greške / rezultat provere
├── resources/
│   ├── icons/*.svg
│   └── styles/base.qss         QSS šablon sa $promenljivim bojama
├── packaging/
│   ├── make_dist.sh            izvorni paket dist/pyqt6-learning-studio-<verzija>.tar.gz
│   ├── build_pyinstaller.sh    PyInstaller paket + samoprovera
│   ├── pyqt6_learning_studio.spec
│   ├── linux/                  .desktop fajl i pokretač
│   └── arch/PKGBUILD           Arch Linux paket
└── tests/                      pytest (248 testova)
```

Odstupanja od predložene strukture i razlozi:

- `lesson_page.py` je podeljen na `lesson_panel.py` (gornja zona) i
  `editor_panel.py` (donja leva) jer su to dva nezavisna dela ekrana.
- Dodat je `core/error_explainer.py` — objašnjavanje grešaka je zasebna
  odgovornost i lako se testira.
- `core/check_session.py` i `core/course_progress.py` su dodati u Fazi 2:
  provera kroz više pokretanja i računanje napretka/preporuke su zasebne,
  testabilne odgovornosti.
- `models/progress.py` nije poseban fajl: `QuizRecord` i `LessonStatus` su
  mali rezultati upita i nalaze se uz `ProgressManager`, koji ih jedini pravi.

---

## Arhitektura

Tri sloja, strogo razdvojena:

| Sloj | Šta radi | Zavisi od |
|---|---|---|
| `models` | Opisuje podatke (lekcija, zadatak, kviz) | ništa |
| `core` | Učitava kurs, pokreće kod, proverava zadatke, čuva napredak | `models` (`code_runner` koristi QtCore) |
| `ui` | Prikazuje i prosleđuje akcije korisnika | `core`, `models` |

Paneli (`LessonPanel`, `EditorPanel`, `OutputPanel`) ne znaju jedni za druge.
Komuniciraju samo preko Qt signala koje povezuje `MainWindow`.

### Povezivanje lekcije, editora i izlaza

```
LessonPanel ──next/previous──▶ MainWindow ──(nesačuvan kod? Sačuvaj/Odbaci/Otkaži)
                                    │
                                    ├─▶ LessonManager.load(id)
                                    ├─▶ EditorPanel: sačuvan kod ili početni kod zadatka
                                    ├─▶ OutputPanel: očisti
                                    └─▶ LessonPanel: tekst, primer, zadatak, kriterijumi

HomePage / LessonBrowser ──lesson_requested──▶ MainWindow (isto pitanje o nesačuvanom kodu)

EditorPanel ──Pokreni / Ctrl+Enter──▶ MainWindow ──▶ CodeRunner.run(kod)
EditorPanel ──Proveri zadatak──▶ MainWindow ──▶ CheckSession.start(kod, kriterijumi)
        CheckSession pokreće CodeRunner jednom po test slučaju (sa zadatim unosom),
        pa šalje sve rezultate u exercise_checker.evaluate
CodeRunner ──stdout/stderr──▶ OutputPanel (uživo)
CodeRunner ──input_requested──▶ OutputPanel (aktivira polje za unos)
OutputPanel ──input_submitted──▶ CodeRunner.send_input()
CodeRunner ──finished(RunResult)──▶ MainWindow
        ├─▶ greška? error_explainer → objašnjenje + označena linija u editoru
        └─▶ provera zadatka? exercise_checker.evaluate → stavke tačno/netačno
```

Kada lekcija promeni zadatak, sistem zna šta se očekuje jer svaki zadatak u
JSON-u nosi svoje kriterijume (`criteria`). Kod u editoru se nikad ne gubi
neprimetno: pri promeni lekcije, učitavanju primera/rešenja ili zatvaranju
aplikacije, za izmenjen kod se nudi **Sačuvaj / Odbaci izmene / Otkaži**.

---

## Pokretanje korisničkog koda (bezbednost)

`core/code_runner.py`:

1. Kod se upisuje u `main.py` u novom privremenom direktorijumu (`pls_run_*`).
2. Pokreće se **zaseban Python proces** (`QProcess`, `python -B -u -X utf8`;
   koji Python — vidi „Samostalan paket“ iznad) —
   nikad u procesu aplikacije, pa se interfejs ne zamrzava.
3. Mali pomoćni skript zamenjuje `input()`: posle pitanja, u isti izlazni tok,
   šalje signal da program čeka unos (zato je redosled pitanja i odgovora u
   prikazu uvek tačan). Tada se **pauzira merenje vremena** i aktivira polje za
   unos. Pri proveri zadatka unos šalje aplikacija i prikazuje ga u izlazu.
4. Ograničenja (`config/settings.py → RunnerLimits`):
   vreme rada **10 s** (bez vremena čekanja na unos), izlaz **100 000 znakova**.
   Prekoračenje zaustavlja program uz jasnu poruku.
5. Dugme **Zaustavi** (Shift+F5): blago gašenje (terminate), pa prinudno (kill).
6. Traceback se čisti od pomoćnih okvira — korisnik vidi samo svoj `main.py`.
7. Privremeni direktorijum se briše posle svakog izvršavanja.

> **Važno:** zaseban proces NIJE sandbox. Pokrenuti program ima ista prava kao
> korisnik — može da čita i briše fajlove i pristupa mreži. To je prihvatljivo za
> kod koji korisnik sam piše dok uči, ali aplikacija nije namenjena izvršavanju
> nepoverljivog koda. Za to bi bila potrebna izolacija na nivou operativnog
> sistema (npr. bubblewrap/firejail, kontejner, poseban korisnik bez prava ili
> virtuelna mašina). Ista napomena je u aplikaciji: *Pomoć → Kako se pokreće kod*.

---

## Format lekcije

Svaka lekcija je JSON fajl; u `course.json` se dodaje `"file": "putanja.json"`.
Nove lekcije se dodaju **bez izmene koda**.

```json
{
  "id": "m01_l02",
  "goal": "Šta će korisnik znati posle lekcije.",
  "explanation": ["Pasus sa **podebljanim** i `kodom`.", "- stavka liste", "> Istaknuta napomena."],
  "terms": [{"term": "Funkcija", "definition": "..."}],
  "example_code": "print(\"Zdravo\")\n",
  "example_steps": [{"code": "print(\"Zdravo\")", "explanation": "..."}],
  "exercise": {
    "type": "write | complete | fix | predict | choice | app",
    "description": "Tekst zadatka.",
    "starter_code": "# početni kod\n",
    "expected_output_preview": "Zdravo",
    "criteria": {
      "expected_output": "Zdravo",
      "output_contains": [],
      "output_line_count": null,
      "code_contains": [{"pattern": "print(", "min_count": 1, "message": "Koristi print."}],
      "code_not_contains": [],
      "min_comment_lines": 0,
      "stdin": "",
      "must_succeed": true
    },
    "hints": ["blag nagoveštaj", "konkretniji", "skoro rešenje"],
    "solution": "print(\"Zdravo\")\n"
  },
  "quiz": [
    {"question": "...", "options": ["a", "b"], "correct": 0, "explanation": "..."},
    {"type": "predict", "question": "Šta ispisuje ovaj program?", "code": "print(7 / 2)\n",
     "options": ["3", "3.5", "4"], "correct": 1, "explanation": "..."},
    {"type": "output", "question": "Upiši tačno šta ovaj program ispisuje.",
     "code": "print(1)\nprint(2)\n", "answer": "1\n2", "explanation": "..."}
  ]
}
```

Zadaci koji čitaju unos koriste **više test slučajeva** umesto jednog `stdin`-a,
da program koji samo ispiše „tačan“ tekst ne bi prošao proveru:

```json
"criteria": {
  "code_contains": [{"pattern": "//", "message": "Sati se računaju sa //."}],
  "cases": [
    {"stdin": "135", "output_contains": ["2 h i 15 min"]},
    {"stdin": "5\n/\n0", "output_contains": ["Deljenje nulom nije moguće."],
     "output_not_contains": ["Rezultat"], "name": "deljenje nulom"}
  ]
}
```

Svaki slučaj može imati `expected_output`, `output_contains`,
`output_not_contains`, `output_line_count`, `name`, `test_code` i `gui_script`.

**Provera prozora:** `gui_script` se izvršava umesto `app.exec()` (program radi
bez prikaza na ekranu) i ima pristup promenljivama programa i pomoćnim funkcijama:

```json
{"name": "sa imenom",
 "gui_script": "upisi(nadji('QLineEdit'), 'Ana')\nklikni('Pozdravi')\nfor n in sve('QLabel'):\n    print('natpis:', tekst(n))\n",
 "output_contains": ["natpis: Zdravo, Ana!"]}
```

**Testovi funkcija:** `test_code` je kod koji aplikacija pri proveri dodaje
POSLE korisnikovog koda. Tako se proverava šta funkcija vraća, a ne samo šta
program ispisuje (koristiće se od Modula 5):

```json
"cases": [
  {"test_code": "print(saberi(2, 3))", "expected_output": "5"},
  {"test_code": "print(saberi(-1, 1))", "expected_output": "0"}
]
```

Ako greška nastane u test kodu (npr. funkcija ne postoji ili se drugačije
zove), korisnik dobija posebno objašnjenje, a ne oznaku linije koje nema u
njegovom kodu. Pravila nad kodom važe
jednom, za ceo zadatak.

Pravila koda (`code_contains`) podrazumevano zanemaruju komentare; sa
`"regex": true` obrazac je regularni izraz, a sa `"ignore_comments": false`
proveravaju se i komentari (npr. „linija mora biti zakomentarisana“).

---

## Faza 1 — šta je implementirano

- Glavni prozor sa tri zone: lekcija gore, editor dole levo, rezultat dole desno;
  oba razdvajača (QSplitter) su podesiva.
- Lekcija: modul, broj („Lekcija 3 od 78“), naslov, cilj, kartice
  **Objašnjenje** (sa novim pojmovima), **Primer** (kod + „deo po deo“ +
  „Prebaci primer u editor“), **Zadatak** (vrsta, opis, očekivani rezultat,
  kriterijumi, nagoveštaji jedan po jedan, rešenje uz potvrdu).
- Prethodna / Sledeća lekcija, „Označi kao završenu“, indikator napretka.
- Smanjivanje/proširivanje prostora lekcije (samo naslov / uobičajeno / prošireno).
- Editor: sintaksa, brojevi linija (uključi/isključi), automatsko uvlačenje
  (i posle `:`), Ctrl+Enter pokreće, Ctrl+/ komentar, crvena oznaka linije sa greškom.
- Dugmad Pokreni, Proveri zadatak, Vrati početni kod, Sačuvaj kod (Ctrl+S).
- Izlaz: stdout i stderr različitim bojama, status, vreme, Očisti, Zaustavi,
  interaktivni `input()` sa jasno označenim poljem za unos.
- Objašnjenja grešaka na srpskom za ~25 vrsta grešaka, sa savetom i dugmetom
  „Idi na liniju N“.
- Provera zadatka po kriterijumima (ne samo „radi bez greške“), sa stavkama
  tačno/netačno, razlikom u prvom pogrešnom redu, brojem pokušaja.
- Čuvanje napretka (u Fazi 1: JSON, atomski upis) i podešavanja (QSettings: veličina
  prozora, raspored panela, brojevi linija, veličina lekcije).
- Svetla tema; sve boje su u paleti (`ui/theme.py`), QSS je šablon.
- Pet kompletnih lekcija Modula 1 + plan svih 78 lekcija.
- 59 testova (u Fazi 1).

Kviz pitanja već postoje u svakoj lekciji, ali se u interfejsu prikazuju tek u
Fazi 3 — u Fazi 1 nema dugmeta koje ne radi.

## Faza 2 — šta je implementirano

- **Početna strana** (prikazuje se pri pokretanju): kartica „Počni ovde“ /
  „Nastavi gde si stao“ / „Preporučena sledeća lekcija“, procenat celog kursa,
  završene lekcije, rešeni zadaci, kartice svih 10 modula sa napretkom
  („Započni / Nastavi / Ponovi modul“, zaključani moduli „Uskoro“).
- **Sadržaj kursa** — bočni panel (F9) sa stablom modula i lekcija: završena,
  zadatak rešen, trenutna, nije započeta, u pripremi (katanac). Filter po
  naslovu, klik otvara lekciju.
- Navigacija: Početna (Ctrl+H), Nastavi učenje (Ctrl+L), prethodna/sledeća
  (Alt+←/→). Svako otvaranje druge lekcije pita za nesačuvan kod.
- **Provera sa više test slučajeva**: svaki slučaj se pokreće posebno, u izlazu
  se vidi „Test 2/6 · unos: 5 / / / 0“ i unos koji je aplikacija poslala;
  izveštaj ima stavku po testu. Provera se prekida ako neki test prekorači vreme.
- Posle uspešne provere: rešenje se **automatski čuva**, a dugme na kartici
  „Završi lekciju i pređi na sledeću“ obavlja oba koraka.
- **13 novih lekcija** (6–18): promenljive, int/float, str, bool, konverzija,
  input(), f-stringovi, operatori, poređenje, and/or/not, if/elif/else,
  ugnježdeni uslovi, kalkulator. Sve sa zadatkom, nagoveštajima, rešenjem i kvizom.
- Testovi proveravaju i da „varanje“ ne prolazi: ručno upisan odgovor,
  kalkulator bez provere nule, prijava koja uvek traži lozinku, pogrešan
  redosled uslova za ocene.

## Faza 3 — šta je implementirano

- **Kviz** za svaku lekciju (kartica „Kviz“ u lekciji): pitanje po pitanje,
  objašnjenje posle svakog odgovora, rezime sa pregledom tačnih/netačnih,
  „Ponovi kviz“. Ponuđeni odgovori se mešaju pri svakom pokušaju. Za prolaz je
  potrebno 70% tačnih; čuva se najbolji i poslednji rezultat, broj pokušaja i
  da li je kviz položen. Početna strana prikazuje broj položenih kvizova.
- **Tri vrste pitanja:** „Izaberi tačan odgovor“, „Predvidi rezultat“ (kod +
  ponuđeni izlazi) i „Upiši šta program ispisuje“ (kod + upisani odgovor).
  Kod pitanja sa programom, posle odgovora može da se klikne **„Pokreni program
  i proveri“** — program se izvršava (u zasebnom procesu) i vidi se stvarni izlaz.
- **37 novih pitanja sa kodom** u svih 18 lekcija. Test pokreće svaki od tih
  programa i proverava da je označeni tačan odgovor zaista ono što program ispiše
  (a da nijedan pogrešan odgovor nije), pa greška u pitanju ne može da prođe neprimećeno.
- **Testovi funkcija** (`test_code`) u proveri zadataka, sa posebnim
  objašnjenjem greške nastale u testu.
- **Preciznije povratne informacije** pri proveri: „program nije ništa ispisao —
  da li si zaboravio print()?“, razlika u interpunkciji na kraju reda, ispisani
  navodnici, nedostaje/višak na kraju reda, tekst postoji ali sa drugačijim
  velikim/malim slovima ili razmacima, poslednji red koji je program ispisao.
- Vrste zadataka u kursu: napiši program, dopuni kod, pronađi i ispravi grešku,
  napravi malu aplikaciju (zadaci u editoru) i predvidi rezultat / izaberi
  tačan odgovor (u kvizu, sa mogućnošću pokretanja koda).

## Faza 4 — šta je implementirano

- **SQLite baza** (`pyqt6_learning_studio.db`) za sve podatke korisnika:
  završene lekcije (sa datumom), rešeni zadaci (datum prvog rešenja), sačuvan
  kod po lekciji, **istorija svih provera** zadataka, rezultati i **istorija
  svih pokušaja kvizova**, trenutna lekcija, **poslednji otvoreni modul** i
  podešavanja.
- `ProgressManager` ima isti javni interfejs kao ranije, pa ostatak aplikacije
  nije menjan. Sve izmene idu kroz transakcije (ili se upiše sve, ili ništa).
- **Automatski prenos:** pri prvom pokretanju stari `progress.json` se prenosi u
  bazu i preimenuje u `progress.json.migrated` (ne briše se); stara podešavanja
  iz QSettings (brojevi linija, raspored panela...) takođe se prenose.
- **Oporavak:** ako je fajl baze oštećen, sklanja se kao `*.corrupt-<vreme>`,
  pravi se nova baza i korisnik dobija poruku. Baza novije verzije šeme se ne
  otvara (umesto da se pokvari).
- **Podešavanja** (Datoteka → Podešavanja…, Ctrl+,):
  - Editor i lekcije: veličina slova koda (editor, primer, izlaz, kviz),
    brojevi linija, potvrda pre prikaza rešenja.
  - Pokretanje koda: najduže vreme rada (1–120 s) i najviše izlaza.
  - Podaci: putanja baze, „Otvori folder“, rezervna kopija baze, izvoz napretka
    u JSON, brisanje napretka (uz potvrdu i automatsku rezervnu kopiju).
  - „Vrati podrazumevano“. Neispravne ili vrednosti van opsega nikad ne stižu
    do aplikacije.
- Raspored prozora (veličina, razdvajači, bočni panel, veličina lekcije) čuva se
  u bazi i vraća pri sledećem pokretanju.
- Kartica „Zadatak“ prikazuje **tvoje pokušaje**: koliko puta je provera
  pokrenuta i kada je zadatak rešen.

## Faza 5 — šta je implementirano

- **Tamna tema** i opcija **„Prema sistemu“** (prati podešavanje sistema, Qt 6.5+).
  Bira se u Prikaz → Tema ili u Podešavanjima. Pri promeni teme prozor se ponovo
  gradi (sve boje i ikone u novoj temi), a otvorena lekcija, kartica i kod u
  editoru — uključujući nesačuvane izmene — prenose se u novi prozor.
- **Pretraga lekcija** (Ctrl+K, lupa u lekciji, dugme na početnoj): pretražuje
  naslove, ciljeve, objašnjenja, pojmove, primere, zadatke, nagoveštaje i
  kvizove. Ne razlikuje velika/mala slova ni kvačice („uvlacenje“ = „uvlačenje“,
  „dorde“ i „djordje“ = „Đorđe“). Upit od više reči traži sve reči. Rezultati
  su poređani po važnosti, sa isečkom i istaknutim pogotkom.
- **Omiljene lekcije**: zvezdica pored naslova lekcije (ili Ctrl+D), oznaka ★
  i filter „samo omiljene“ u sadržaju kursa, sekcija na početnoj strani. Čuvaju se
  u bazi (šema verzija 2, automatska nadogradnja), a „Obriši sav napredak“ ih ne briše.
- **Programi sa prozorom (PyQt6):**
  - „Pokreni“ otvara pravi prozor; program sa PyQt6 nema vremensko ograničenje
    (radi dok se prozor ne zatvori ili se ne klikne „Zaustavi“).
  - Greška u funkciji koju poziva dugme (slot) **ne ruši prozor** — ispiše se u
    panelu sa rezultatom i objasni, a program nastavlja da radi.
  - **Provera GUI zadataka** (`gui_script` u test slučaju): program se pokreće bez
    prikaza na ekranu, a umesto `app.exec()` izvršava se skripta koja pregleda
    prozor i klikće dugmad, uz pomoćne funkcije `glavni()`, `nadji(tip, sadrzi)`,
    `sve(tip)`, `tekst(w)`, `klikni(dugme)`, `upisi(polje, tekst)`. Zaboravljen
    `show()` ili `app.exec()` daje razumljivu poruku.
- **7 novih lekcija:** 48–53 (Šta je PyQt6, prvi prozor, QApplication i QWidget,
  QLabel i QPushButton, QLineEdit i QTextEdit, signali i slotovi) i završni
  projekat 71 — **Kalkulator sa prozorom** (6 GUI provera: četiri operacije,
  deljenje nulom, neispravan unos).

> Moduli 6–7 (greške, fajlovi, klase) su još u pripremi. PyQt6 lekcije
> su zato napisane tako da se mogu pratiti sa znanjem iz Modula 1–5: pojmovi koji
> im trebaju (`import`, objekat, `def`, `try/except`) ukratko su objašnjeni na
> mestu gde se prvi put koriste, uz uputstvo na lekciju u kojoj se detaljno obrađuju.

## Faza 6 — šta je implementirano

- **Testovi glavnih tokova rada** kroz pravi glavni prozor (12), **pokretanja
  aplikacije i obrade grešaka** (8), widget-a (7) i **„ugrađenog“ Pythona** (9).
  Ukupno 248 testova, 90% pokrivenosti koda; ceo skup stabilno prolazi u ponovljenim
  pokretanjima.
- Ispravljene greške pronađene testovima: veza ka bazi ostajala je otvorena kada je
  fajl baze oštećen i kada plan kursa ne može da se učita; rezervni editor nije
  menjao veličinu slova; strelice u pretrazi nisu radile ako se pritisnu odmah
  posle kucanja.
- **Izbor Python interpretera** (`core/python_locator.py`) i podešavanje
  „Pokretanje koda → Python“: spakovana aplikacija koristi Python sa sistema, a
  ako ga nema, Python ugrađen u paket (`--pls-run`).
- **Samoprovera** `--self-test`.
- **Pakovanje:** PyInstaller (izgrađen i proveren, i bez Pythona na sistemu),
  Arch PKGBUILD (proveren simulacijom `check()` i `package()`; instalirana kopija
  radi iz direktorijuma samo za čitanje), `.desktop` fajl, ikona aplikacije,
  izvorni tarball.

## Verzija 0.7.0 — sadržaj kursa

- **Modul 4 — Petlje i kolekcije** (lekcije 19–27): for i range, while, break i
  continue, liste, torke, skupovi, rečnici, prolazak kroz kolekcije, praktična
  vežba „evidencija zaliha“.
- **Modul 5 — Funkcije i organizacija koda** (lekcije 28–34): def, parametri i
  argumenti (podrazumevane vrednosti, imenovani argumenti), return, lokalni i
  globalni opseg, lambda/sorted/filter/map, import (math, random, datetime),
  organizacija programa i `if __name__ == "__main__"`.
- Zadaci sa funkcijama proveravaju se tako što aplikacija **sama poziva**
  korisnikove funkcije sa različitim argumentima i koristi vraćene vrednosti —
  funkcija koja ispisuje umesto da vrati rezultat ne prolazi.
- Svaka lekcija ima kviz od 5 pitanja (3 teorijska, 1 „šta ispisuje“, 1 „upiši izlaz“);
  odgovori na pitanja sa kodom provereni su pokretanjem koda u testovima.

## Šta dalje

Sve faze iz plana su završene. Najveći preostali posao je **sadržaj kursa**:

| Deo | Stanje |
|---|---|
| Moduli 1–5 (lekcije 1–34: osnove, uslovi, petlje, kolekcije, funkcije) | gotovo |
| Moduli 6–7 (lekcije 35–47: greške, fajlovi, SQLite, pytest, klase) | u pripremi |
| Modul 8 (lekcije 48–60) | 48–53 gotovo, 54–60 u pripremi |
| Modul 9 (lekcije 61–70) | u pripremi |
| Modul 10 (lekcije 71–78) | 71 (Kalkulator) gotovo, ostalo u pripremi |

Nove lekcije se dodaju samo JSON fajlovima (vidi „Format lekcije“) — testovi
automatski proveravaju da im rešenja prolaze, a početni kod ne.

Podaci korisnika: `~/.local/share/PyUcionica/pyqt6-learning-studio/pyqt6_learning_studio.db` (Linux).
