# pyqt6_learning_studio/core/error_explainer.py
"""Pretvara Python poruke o greškama u objašnjenja razumljiva početniku.

Modul čita traceback (tekst greške), pronalazi vrstu greške, poruku i broj
linije u korisnikovom kodu, a zatim bira objašnjenje na srpskom jeziku i
konkretan savet šta da se proba.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

USER_FILE_NAME = "main.py"

_FILE_LINE_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)')
_EXC_LINE_RE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*?(Error|Exception|Warning|Exit|Interrupt|Iteration))(?::\s?(?P<msg>.*))?$")
_DID_YOU_MEAN_RE = re.compile(r"Did you mean:? '?(?P<name>[^'?]+)'?\??")


@dataclass(frozen=True)
class ErrorInfo:
    """Rastavljena i objašnjena greška.

    Attributes:
        exc_type: Naziv vrste greške (npr. ``"NameError"``).
        message: Originalna poruka Pythona.
        line: Broj linije u korisnikovom kodu (``None`` ako nije poznat).
        title: Kratak naslov objašnjenja na srpskom.
        explanation: Šta greška znači, jednostavnim jezikom.
        tip: Konkretan savet šta da se proveri ili promeni.
    """

    exc_type: str
    message: str
    line: int | None
    title: str
    explanation: str
    tip: str


def parse_traceback(stderr: str) -> tuple[str | None, str, int | None]:
    """Izdvaja (vrsta greške, poruka, linija) iz teksta traceback-a.

    Linija se uzima iz poslednjeg pominjanja korisnikovog fajla, jer je to
    mesto u korisnikovom kodu najbliže nastanku greške.
    """
    exc_type: str | None = None
    message = ""
    line: int | None = None
    for match in _FILE_LINE_RE.finditer(stderr):
        if match.group("file") == USER_FILE_NAME:
            line = int(match.group("line"))
    for raw in reversed(stderr.strip().splitlines()):
        text = raw.strip()
        if not text:
            continue
        match = _EXC_LINE_RE.match(text)
        if match:
            exc_type = match.group("type").split(".")[-1]
            message = (match.group("msg") or "").strip()
            break
    return exc_type, message, line


# ---------------------------------------------------------------------------
# Objašnjenja po vrstama grešaka. Svaka funkcija prima poruku i vraća
# (naslov, objašnjenje, savet).
# ---------------------------------------------------------------------------
Explanation = tuple[str, str, str]


def _syntax_error(msg: str) -> Explanation:
    low = msg.lower()
    title = "Sintaksna greška — Python ne razume kako je kod napisan"
    base = (
        "Sintaksa su pravila pisanja koda, kao gramatika u jeziku. Python je pročitao tvoj "
        "kod pre pokretanja i našao mesto koje ne poštuje ta pravila, pa nije izvršio ništa."
    )
    if "unterminated string" in low or "unterminated triple-quoted" in low or "eol while scanning" in low:
        return (title, base + " Tekst (string) je otvoren navodnikom, ali nije zatvoren.",
                "Proveri da svaki tekst ima navodnik i na početku i na kraju, iste vrste: "
                "\"ovako\" ili 'ovako'.")
    if "was never closed" in low or "unexpected eof" in low:
        return (title, base + " Neka zagrada je otvorena, ali nikada nije zatvorena.",
                "Prebroj zagrade u označenoj liniji: svaka ( mora imati svoju ). "
                "Greška se ponekad prijavljuje linijom ispod stvarnog problema.")
    if "unmatched" in low or "does not match opening parenthesis" in low:
        return (title, base + " Postoji zatvorena zagrada koja nema svoj otvoreni par.",
                "Ukloni višak zagrade ili dodaj onu koja nedostaje na početku.")
    if "missing parentheses in call to 'print'" in low:
        return (title, base + " U Pythonu 3, print je funkcija i zahteva zagrade.",
                "Piši print(\"tekst\") umesto print \"tekst\".")
    if "invalid character" in low:
        return (title, base + " U kodu postoji znak koji Python ne prepoznaje. Najčešće su to "
                "„pametni“ navodnici (“ ” ‘ ’) koji nastaju kopiranjem iz Word-a ili sa interneta.",
                "Obriši navodnike u označenoj liniji i ukucaj ih ponovo sa tastature: \" ili '.")
    if "expected ':'" in low:
        return (title, base + " Na kraju ove linije nedostaje dvotačka (:).",
                "Linije koje počinju sa if, elif, else, for, while, def ili class moraju se završiti dvotačkom.")
    if "perhaps you forgot a comma" in low:
        return (title, base + " Između dve vrednosti verovatno nedostaje zarez.",
                "Kada navodiš više vrednosti, npr. print(\"a\", \"b\"), odvoji ih zarezom.")
    if "maybe you meant '==' " in low or "maybe you meant '=='" in low or "cannot assign to" in low:
        return (title, base + " Pokušao si da dodeliš vrednost nečemu što ne može da je primi. "
                "Možda si hteo da porediš vrednosti?",
                "Za poređenje koristi == (dva znaka jednakosti). Jedan znak = služi za dodeljivanje.")
    if "invalid decimal literal" in low:
        return (title, base + " Broj je spojen sa slovima, ili ime počinje cifrom.",
                "Imena ne smeju počinjati cifrom, a decimalni brojevi pišu se tačkom: 3.14, ne 3,14.")
    return (title, base,
            "Pogledaj označenu liniju i liniju iznad nje. Proveri navodnike, zagrade, "
            "dvotačke i da li su reči tačno napisane.")


def _indentation_error(msg: str) -> Explanation:
    low = msg.lower()
    title = "Greška u uvlačenju (razmacima na početku linije)"
    base = ("U Pythonu razmaci na početku linije imaju značenje: pokazuju koje linije "
            "pripadaju zajedno. Zato se ne smeju dodavati nasumično.")
    if "unexpected indent" in low:
        return (title, base + " Ova linija je uvučena, a ne bi trebalo da bude.",
                "Obriši razmake na početku označene linije, tako da počinje od leve ivice kao linije iznad.")
    if "expected an indented block" in low:
        return (title, base + " Posle linije koja se završava dvotačkom (:) mora da sledi uvučen blok.",
                "Uvuci liniju ispod dvotačke za 4 razmaka (taster Tab u editoru).")
    if "unindent does not match" in low:
        return (title, base + " Uvlačenje ove linije ne odgovara nijednom nivou iznad nje.",
                "Poravnaj liniju tačno sa linijama iznad — najčešće koristi 4, 8, 12... razmaka.")
    return (title, base, "Proveri razmake na početku označene linije.")


def _name_error(msg: str) -> Explanation:
    title = "Nepoznato ime — Python ne zna na šta misliš"
    match = re.search(r"name '([^']+)' is not defined", msg)
    name = match.group(1) if match else None
    suggestion = _DID_YOU_MEAN_RE.search(msg)
    explanation = (
        "Upotrebio si ime (reč) koje Python ne poznaje. Ime mora biti ugrađena funkcija "
        "(npr. print) ili nešto što si ranije sam napravio."
    )
    if name:
        explanation = (f"Python ne zna šta je „{name}“. " + explanation)
    if suggestion:
        tip = f"Da li si mislio na „{suggestion.group('name')}“? Proveri kako je reč napisana."
    elif name and name.lower() in {"print", "input", "int", "float", "str", "len", "range", "true", "false"}:
        correct = {"true": "True", "false": "False"}.get(name.lower(), name.lower())
        tip = f"Python razlikuje velika i mala slova. Piši „{correct}“, a ne „{name}“."
    elif name:
        tip = (f"Ako si hteo da ispišeš tekst „{name}“, stavi ga pod navodnike: \"{name}\". "
               "Ako je to promenljiva, proveri da li si joj dodelio vrednost pre ove linije i da li je ime isto napisano.")
    else:
        tip = "Proveri pravopis imena i da li je definisano pre upotrebe."
    return (title, explanation, tip)


def _type_error(msg: str) -> Explanation:
    low = msg.lower()
    title = "Pogrešan tip podatka"
    base = ("Tip podatka govori kakva je vrednost: tekst (str), ceo broj (int), decimalni broj "
            "(float)... Neke operacije rade samo sa određenim tipovima.")
    if "can only concatenate str" in low or ("unsupported operand" in low and "str" in low):
        return (title, base + " Pokušao si da spojiš tekst i broj pomoću +.",
                "Pretvori broj u tekst sa str(broj), ili koristi zarez u print-u: print(\"Godine:\", 30).")
    if "unsupported operand" in low:
        return (title, base + " Ova matematička operacija ne može da se izvrši nad tim vrstama vrednosti.",
                "Proveri koje vrednosti učestvuju u računu — da li je neka od njih tekst ili None?")
    if "not callable" in low:
        return (title, base + " Pokušao si da „pozoveš“ (dodaš zagrade) nešto što nije funkcija.",
                "Proveri da li si slučajno nazvao promenljivu isto kao funkciju (npr. print = ...), "
                "ili stavio zagrade iza obične vrednosti.")
    if "positional argument" in low or "required" in low and "argument" in low:
        return (title, base + " Funkciji je prosleđen pogrešan broj vrednosti (argumenata).",
                "Proveri koliko vrednosti funkcija očekuje i koliko si joj dao u zagradama.")
    if "not subscriptable" in low:
        return (title, base + " Pokušao si da uzmeš element sa [ ] iz vrednosti koja to ne podržava.",
                "Uglaste zagrade [ ] rade sa listama, tekstom i rečnicima, ali ne sa brojevima.")
    return (title, base, "Proveri tipove vrednosti u označenoj liniji. Funkcija type(x) pokazuje tip.")


def _value_error(msg: str) -> Explanation:
    low = msg.lower()
    title = "Neodgovarajuća vrednost"
    if "invalid literal for int()" in low or "could not convert string to float" in low:
        return (title, "Pokušao si da pretvoriš tekst u broj, ali tekst ne izgleda kao broj.",
                "Proveri šta se pretvara. Za int() tekst mora biti ceo broj, npr. \"42\". "
                "Decimalni brojevi pišu se tačkom: \"3.5\".")
    return (title, "Tip vrednosti je odgovarajući, ali sama vrednost nije prihvatljiva za ovu operaciju.",
            "Ispiši vrednost pomoću print() neposredno pre označene linije da vidiš šta zapravo sadrži.")


def _simple(title: str, explanation: str, tip: str) -> Callable[[str], Explanation]:
    return lambda _msg: (title, explanation, tip)


_EXPLAINERS: dict[str, Callable[[str], Explanation]] = {
    "SyntaxError": _syntax_error,
    "IndentationError": _indentation_error,
    "TabError": _simple(
        "Mešanje tabova i razmaka",
        "U uvlačenju su pomešani tab znaci i razmaci, pa Python ne može da odredi nivo uvlačenja.",
        "Uvlači samo razmacima (4 po nivou). Editor automatski pretvara Tab u razmake.",
    ),
    "NameError": _name_error,
    "UnboundLocalError": _simple(
        "Promenljiva korišćena pre dodele vrednosti",
        "Unutar funkcije koristiš promenljivu pre nego što joj je u toj funkciji dodeljena vrednost.",
        "Dodeli vrednost pre upotrebe, ili prosledi vrednost funkciji kao parametar.",
    ),
    "TypeError": _type_error,
    "ValueError": _value_error,
    "ZeroDivisionError": _simple(
        "Deljenje nulom",
        "Pokušao si da podeliš broj nulom, a to u matematici nije definisano.",
        "Pre deljenja proveri da delilac nije 0, npr. pomoću if delilac != 0:.",
    ),
    "IndexError": _simple(
        "Indeks van opsega",
        "Tražio si element na poziciji koja ne postoji. Pozicije (indeksi) počinju od 0, "
        "pa lista sa 3 elementa ima indekse 0, 1 i 2.",
        "Proveri dužinu sa len() i koristi indeks manji od nje.",
    ),
    "KeyError": _simple(
        "Ključ ne postoji u rečniku",
        "Tražio si vrednost pod ključem koji u rečniku ne postoji.",
        "Proveri tačan naziv ključa (velika/mala slova) ili koristi recnik.get(kljuc).",
    ),
    "AttributeError": _simple(
        "Nepostojeći atribut ili metoda",
        "Pokušao si da koristiš osobinu ili metodu (posle tačke) koju ova vrednost nema.",
        "Proveri pravopis posle tačke i tip vrednosti. Funkcija dir(x) prikazuje šta je dostupno.",
    ),
    "ModuleNotFoundError": _simple(
        "Modul nije pronađen",
        "Pokušao si da uvezeš (import) modul koji nije instaliran ili je pogrešno napisan.",
        "Proveri naziv modula. Ako je to spoljašnja biblioteka, treba je instalirati.",
    ),
    "ImportError": _simple(
        "Greška pri uvozu",
        "Modul postoji, ali iz njega nije moguće uvesti traženo ime.",
        "Proveri tačan naziv onoga što uvoziš posle reči import.",
    ),
    "FileNotFoundError": _simple(
        "Fajl nije pronađen",
        "Program pokušava da otvori fajl koji ne postoji na navedenoj putanji.",
        "Proveri naziv i putanju fajla. Kod se pokreće u privremenom direktorijumu.",
    ),
    "RecursionError": _simple(
        "Previše ugnježdenih poziva funkcije",
        "Funkcija poziva samu sebe bez kraja (beskonačna rekurzija).",
        "Proveri da li funkcija ima uslov kada prestaje da poziva samu sebe.",
    ),
    "EOFError": _simple(
        "Unos nije stigao",
        "Program je pozvao input() i čekao unos, ali unos nije poslat.",
        "Kada program traži unos, upiši ga u polje za unos ispod izlaza i pritisni Enter.",
    ),
    "AssertionError": _simple(
        "Provera (assert) nije prošla",
        "Uslov u naredbi assert nije bio tačan.",
        "Proveri vrednosti koje assert poredi.",
    ),
    "OverflowError": _simple(
        "Broj je prevelik",
        "Rezultat računa je prevelik da bi mogao da se predstavi.",
        "Proveri račun — možda negde postoji beskonačno uvećavanje.",
    ),
    "KeyboardInterrupt": _simple(
        "Program je prekinut",
        "Izvršavanje je prekinuto pre završetka.",
        "Ako se program zaglavio, proveri petlje koje se nikad ne završavaju.",
    ),
}


def explain_error(stderr: str) -> ErrorInfo | None:
    """Pravi objašnjenje greške iz teksta stderr-a.

    Returns:
        :class:`ErrorInfo`, ili ``None`` ako u tekstu nema prepoznatljive greške.
    """
    exc_type, message, line = parse_traceback(stderr)
    if exc_type is None:
        return None
    explainer = _EXPLAINERS.get(exc_type)
    if explainer is None:
        title = f"Greška tipa {exc_type}"
        explanation = "Python je naišao na problem tokom izvršavanja programa."
        tip = "Pročitaj poslednju liniju poruke — ona opisuje šta je pošlo naopako — i proveri označenu liniju koda."
    else:
        title, explanation, tip = explainer(message)
    return ErrorInfo(exc_type, message, line, title, explanation, tip)
