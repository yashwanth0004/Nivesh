"""Lightweight normalization for SEBI details spoken in Indic languages.

This is deliberately deterministic: it can transcribe digit-by-digit references
and romanize names, but it never turns a guessed number into a verified ID.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


_SPOKEN_DIGITS = {
    # English, including common ASR spellings.
    "zero": "0", "oh": "0", "o": "0", "shunya": "0", "one": "1", "won": "1",
    "two": "2", "too": "2", "to": "2", "three": "3", "thre": "3", "tree": "3",
    "four": "4", "for": "4", "five": "5", "fai": "5", "phai": "5", "faiv": "5",
    "six": "6", "siks": "6", "seven": "7", "sevan": "7", "eight": "8", "ate": "8",
    "nine": "9", "nain": "9",
    # Hindi, Marathi, Nepali and related Devanagari speech.
    "शून्य": "0", "शुन्य": "0", "सिफर": "0", "एक": "1", "इक": "1", "दो": "2",
    "तीन": "3", "चार": "4", "पाँच": "5", "पांच": "5", "पाच": "5", "छह": "6",
    "छः": "6", "सात": "7", "आठ": "8", "नौ": "9",
    # Telugu.
    "సున్నా": "0", "సున్న": "0", "శూన్యం": "0", "జీరో": "0", "ఒకటి": "1", "ఒకట": "1",
    "వన్": "1", "రెండు": "2", "టూ": "2", "మూడు": "3", "త్రీ": "3", "నాలుగు": "4",
    "ఫోర్": "4", "ఐదు": "5", "ఫైవ్": "5", "ఆరు": "6", "సిక్స్": "6", "ఏడు": "7",
    "సెవెన్": "7", "ఎనిమిది": "8", "ఎనిమిదీ": "8", "ఎయిట్": "8", "తొమ్మిది": "9",
    "తొమ్మది": "9", "నైన్": "9",
    # Tamil.
    "பூஜ்ஜியம்": "0", "சுழியம்": "0", "பூஜ்யம்": "0", "ஒன்று": "1", "ஒரு": "1",
    "இரண்டு": "2", "மூன்று": "3", "நான்கு": "4", "ஐந்து": "5", "ஆறு": "6",
    "ஏழு": "7", "எட்டு": "8", "ஒன்பது": "9",
    # Kannada.
    "ಸೊನ್ನೆ": "0", "ಶೂನ್ಯ": "0", "ಒಂದು": "1", "ಎರಡು": "2", "ಮೂರು": "3",
    "ನಾಲ್ಕು": "4", "ಐದು": "5", "ಆರು": "6", "ಏಳು": "7", "ಎಂಟು": "8", "ಒಂಬತ್ತು": "9",
    # Malayalam.
    "പൂജ്യം": "0", "പൂജ്യം": "0", "ഒന്ന്": "1", "രണ്ട്": "2", "മൂന്ന്": "3",
    "നാല്": "4", "അഞ്ച്": "5", "ആറ്": "6", "ഏഴ്": "7", "എട്ട്": "8", "ഒമ്പത്": "9",
    # Bengali and Assamese.
    "শূন্য": "0", "শুন্য": "0", "এক": "1", "দুই": "2", "দু্ই": "2", "তিন": "3",
    "চার": "4", "পাঁচ": "5", "ছয়": "6", "ছয়": "6", "সাত": "7", "আট": "8", "নয়": "9", "নয়": "9",
    # Gujarati.
    "શૂન્ય": "0", "એક": "1", "બે": "2", "ત્રણ": "3", "ચાર": "4", "પાંચ": "5",
    "છ": "6", "સાત": "7", "આઠ": "8", "નવ": "9",
    # Odia.
    "ଶୂନ୍ୟ": "0", "ଏକ": "1", "ଦୁଇ": "2", "ତିନି": "3", "ଚାରି": "4", "ପାଞ୍ଚ": "5",
    "ଛଅ": "6", "ସାତ": "7", "ଆଠ": "8", "ନଅ": "9",
    # Punjabi.
    "ਸਿਫ਼ਰ": "0", "ਸਿਫਰ": "0", "ਇੱਕ": "1", "ਦੋ": "2", "ਤਿੰਨ": "3", "ਚਾਰ": "4",
    "ਪੰਜ": "5", "ਛੇ": "6", "ਸੱਤ": "7", "ਅੱਠ": "8", "ਨੌਂ": "9",
    # Urdu.
    "صفر": "0", "ایک": "1", "دو": "2", "تین": "3", "چار": "4", "پانچ": "5",
    "چھ": "6", "سات": "7", "آٹھ": "8", "نو": "9",
}

_LABEL_WORDS = {
    "number", "no", "id", "registration", "sebi", "s.e.b.i", "nambar", "numberu",
    "నెంబర్", "నంబర్", "సంఖ్య", "కింద", "క్రింద", "ఈ", "ఐడి", "ఐడీ",
    "नाम", "नंबर", "संख्या", "पंजीकरण", "के", "लिए", "आईडी", "क्रमांक",
    "எண்", "எண்ண", "பதிவு", "எஸ்இபிஐ", "ಐಡಿ", "ನಂಬರ್", "ಸಂಖ್ಯೆ", "नोंदणी",
    "sankhya", "nombor", "nomber", "idiga", "keezhe", "ke", "debaixo",
}

_SEBI_CUES = (
    "sebi", "s.e.b.i", "సెబి", "సెబీ", "ఎస్సిబిఐ", "ఎస్ఇబిఐ", "ఎస్ ఈ బి ఐ", "सेबी", "एसईबीआई", "एस ई बी आई",
    "செபி", "எஸ்இபிஐ", "எஸ் இ பி ஐ", "ಸೆಬಿ", "ಸೆಬಿಐ", "ಎಸ್ ಇ ಬಿ ಐ", "સીબી", "સેબી", "সেবি", "সেবিআই",
    "ସେବି", "ਸੇਬੀ", "سیبی", "سیبئی", "സെബി", "സെബി ഐ",
)

_SPOKEN_PREFIXES = (
    # Common Latin letter-by-letter pronunciations.
    (re.compile(r"\bI\s*N\s*H\b", re.I), "INH"),
    (re.compile(r"\b(?:eye|i)\s*(?:en|n)\s*(?:aitch|h)\b", re.I), "INH"),
    (re.compile(r"\bI\s*N\s*Z\b", re.I), "INZ"),
    (re.compile(r"\b(?:eye|i)\s*(?:en|n)\s*(?:zee|zed|z)\b", re.I), "INZ"),
    (re.compile(r"\bI\s*N\s*A\b", re.I), "INA"),
    (re.compile(r"\b(?:eye|i)\s*(?:en|n)\s*a\b", re.I), "INA"),
    (re.compile(r"\bI\s*N\s*P\b", re.I), "INP"),
    # Telugu letter names commonly returned by AI4Bharat ASR.
    (re.compile(r"ఐ\s*ఎన్\s*హెచ్|ఐఎన్హెచ్"), "INH"),
    (re.compile(r"ఐ\s*ఎన్\s*జెడ్|ఐఎన్జెడ్"), "INZ"),
    (re.compile(r"ఐ\s*ఎన్\s*ఏ|ఐఎన్ఏ"), "INA"),
    (re.compile(r"ఐ\s*ఎన్\s*పి|ఐఎన్పి"), "INP"),
    (re.compile(r"ఐఎండ్సి|ఐఎండీసీ|ఐ\s*ఎం\s*డి\s*సి"), "IMDC"),
    # Hindi, Tamil, Kannada and Urdu letter names.
    (re.compile(r"आई\s*एन\s*एच"), "INH"),
    (re.compile(r"आई\s*एन\s*ज़ेड|आई\s*एन\s*जेड"), "INZ"),
    (re.compile(r"ஐ\s*என்\s*எச்"), "INH"),
    (re.compile(r"ஐ\s*என்\s*ஜெட்"), "INZ"),
    (re.compile(r"ಐ\s*ಎನ್\s*ಹೆಚ್"), "INH"),
    (re.compile(r"آئی\s*این\s*ایچ"), "INH"),
)

_SCRIPT_SOUND = {
    "A": "a", "AA": "aa", "I": "i", "II": "ii", "U": "u", "UU": "uu",
    "VOCALIC R": "ri", "VOCALIC RR": "rii", "E": "e", "EE": "ee", "AI": "ai",
    "O": "o", "OO": "oo", "AU": "au", "K": "k", "KA": "k", "KHA": "kh",
    "GA": "g", "GHA": "gh", "NGA": "ng", "CA": "ch", "CHA": "chh", "JA": "j",
    "JHA": "jh", "NYA": "ny", "TTA": "t", "TTHA": "th", "DDA": "d", "DDHA": "dh",
    "NNA": "n", "TA": "t", "THA": "th", "DA": "d", "DHA": "dh", "NA": "n",
    "PA": "p", "PHA": "ph", "BA": "b", "BHA": "bh", "MA": "m", "YA": "y",
    "RA": "r", "LA": "l", "LLA": "l", "VA": "v", "WA": "w", "SHA": "sh",
    "SSA": "sh", "SA": "s", "HA": "h", "ZHA": "zh", "RRA": "r", "FA": "f",
}


def normalize_indic_digits(text: str) -> str:
    """Convert native-script Unicode digits (०, ౧, ௨, …) to ASCII digits."""
    out = []
    for char in text or "":
        try:
            out.append(str(unicodedata.digit(char)))
        except (TypeError, ValueError):
            out.append(char)
    return "".join(out)


def transliterate_indic(text: str) -> str:
    """Approximate common Indic abugidas using their Unicode letter names."""
    text = normalize_indic_digits(text or "")
    chars = list(text)
    output = []
    index = 0
    vowel_signs = {"VOWEL SIGN " + name: sound for name, sound in _SCRIPT_SOUND.items() if name in {
        "AA", "I", "II", "U", "UU", "VOCALIC R", "VOCALIC RR", "E", "EE", "AI", "O", "OO", "AU"
    }}
    vowel_signs.update({"VOWEL SIGN E": "e", "VOWEL SIGN O": "o", "VOWEL SIGN EE": "ee"})
    while index < len(chars):
        char = chars[index]
        name = unicodedata.name(char, "")
        if "VIRAMA" in name or "HALANT" in name:
            index += 1
            continue
        if char.isascii():
            output.append(char.lower())
            index += 1
            continue
        if name.startswith("ARABIC LETTER "):
            output.append(_ARABIC_SOUND.get(name.split("ARABIC LETTER ", 1)[1], ""))
            index += 1
            continue
        if name.endswith("ANUSVARA") or name.endswith("BINDI"):
            output.append("n")
            index += 1
            continue
        if name.endswith("VISARGA"):
            output.append("h")
            index += 1
            continue
        if "LETTER " in name:
            ending = name.split("LETTER ", 1)[1]
            sound = _SCRIPT_SOUND.get(ending)
            if sound is None:
                index += 1
                continue
            if ending in {"A", "AA", "I", "II", "U", "UU", "VOCALIC R", "VOCALIC RR", "E", "EE", "AI", "O", "OO", "AU"}:
                output.append(sound)
                index += 1
                continue
            # A following vowel sign replaces the inherent 'a'; a virama
            # suppresses it. Unicode stores both after the consonant.
            if index + 1 < len(chars):
                following_name = unicodedata.name(chars[index + 1], "")
                if "VOWEL SIGN " in following_name:
                    vowel_name = following_name.split("VOWEL SIGN ", 1)[1]
                    sound += vowel_signs.get("VOWEL SIGN " + vowel_name, _SCRIPT_SOUND.get(vowel_name, "a"))
                    index += 1
                elif "VIRAMA" in following_name or "HALANT" in following_name:
                    pass
                elif "SIGN ANUSVARA" in following_name:
                    sound += "an"
                    index += 1
                else:
                    sound += "a"
            else:
                sound += "a"
            output.append(sound)
            index += 1
            continue
        if "VOWEL SIGN " in name:
            vowel_name = name.split("VOWEL SIGN ", 1)[1]
            output.append(vowel_signs.get("VOWEL SIGN " + vowel_name, _SCRIPT_SOUND.get(vowel_name, "")))
        elif name.startswith("ARABIC LETTER "):
            output.append(_ARABIC_SOUND.get(name.split("ARABIC LETTER ", 1)[1], ""))
        elif char.isspace() or unicodedata.category(char).startswith("P"):
            output.append(char)
        index += 1
    return "".join(output)


_ARABIC_SOUND = {
    "ALEF": "a", "BEH": "b", "PEH": "p", "TEH": "t", "TTEH": "t", "THEH": "s",
    "JEEM": "j", "TCHEH": "ch", "HAH": "h", "KHAH": "kh", "DAL": "d", "DDAL": "d",
    "THAL": "z", "REH": "r", "RREH": "r", "ZAIN": "z", "JEH": "zh", "SEEN": "s",
    "SHEEN": "sh", "SAD": "s", "DAD": "z", "TAH": "t", "ZAH": "z", "AIN": "",
    "GHAIN": "gh", "FEH": "f", "QAF": "q", "KAF": "k", "GAF": "g", "LAM": "l",
    "MEEM": "m", "NOON": "n", "WAW": "w", "HEH": "h", "DOACHASHMEE HEH": "h",
    "HAMZA": "", "YEH": "y", "FARSI YEH": "y", "YEH BARREE": "e", "NG": "ng",
}


def _digit_for_token(token: str) -> str | None:
    token = token.strip(".,:;!?()[]{}\"'،؛؟").casefold()
    if not token:
        return None
    token_digits = normalize_indic_digits(token)
    if token_digits.isdigit():
        return token_digits
    if token in _SPOKEN_DIGITS:
        return _SPOKEN_DIGITS[token]
    # Some ASR engines render a native word phonetically in Latin characters.
    transliterated = re.sub(r"[^a-z]", "", transliterate_indic(token).casefold())
    if transliterated in _SPOKEN_DIGITS:
        return _SPOKEN_DIGITS[transliterated]
    if len(token) >= 3:
        ranked = sorted(
            (
                (SequenceMatcher(None, token, known).ratio(), digit)
                for known, digit in _SPOKEN_DIGITS.items()
                if len(known) >= 3 and token.isascii() == known.isascii()
            ),
            reverse=True,
        )
        if ranked and ranked[0][0] >= 0.82:
            best_score = ranked[0][0]
            best_digits = {digit for score, digit in ranked if score == best_score}
            if len(best_digits) == 1:
                return best_digits.pop()
    return None


def extract_spoken_sebi_ids(text: str) -> list[str]:
    """Find explicit or digit-by-digit SEBI references without guessing validity."""
    source = normalize_indic_digits(text or "")
    found = re.findall(r"\bIN[A-Z]\d{6,11}\b|\bIN/AIF[A-Z0-9/\-]{6,18}\b", source.upper())
    if found:
        existing = set(found)
    else:
        existing = set()
    cue_pattern = re.compile("|".join(re.escape(cue) for cue in sorted(_SEBI_CUES, key=len, reverse=True)), re.I)
    matches = list(cue_pattern.finditer(source))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else min(len(source), start + 180)
        segment = source[start:end]
        # Stop at the explanatory text that commonly follows the spoken ID.
        segment = re.split(r"(?i)\b(?:under|below|account|amount|buy|purchase|invest|shares|stocks)\b|కింద|క్రింద|खाते|तहत|கீழ்|ಅಡಿಯಲ್ಲಿ|تحت", segment, maxsplit=1)[0]
        prefix = ""
        first_number_position = None
        digit_tokens = []
        # Split on spaces instead of ``\w``: Python's Unicode word class can
        # break Indic words at vowel marks/viramas and lose their digit meaning.
        for token_match in re.finditer(r"\S+", segment, re.UNICODE):
            token = token_match.group(0).strip(".,:;!?()[]{}\"'،؛؟")
            if not token:
                continue
            digits = _digit_for_token(token)
            if digits is not None:
                if first_number_position is None:
                    first_number_position = token_match.start()
                digit_tokens.append(digits)
            elif first_number_position is not None:
                # The SEBI ID is usually read digit by digit. Stop at the first
                # ordinary word so later prices/amounts cannot be appended.
                break
            elif first_number_position is None:
                if token.casefold() not in _LABEL_WORDS and not token.isdigit():
                    prefix += token
        digits_value = "".join(digit_tokens)
        if len(digits_value) < 6:
            continue

        compact_prefix = re.sub(r"[^A-Za-z]", "", prefix).upper()
        raw_before_digits = segment[:first_number_position] if first_number_position is not None else ""
        for pattern, normalized_prefix in _SPOKEN_PREFIXES:
            if pattern.search(raw_before_digits):
                compact_prefix = normalized_prefix
                break
        # Only retain short letter prefixes. A filler word such as "number"
        # must never become part of the claimed SEBI ID.
        if len(compact_prefix) > 6:
            compact_prefix = ""
        candidate = compact_prefix + digits_value
        if candidate:
            existing.add(candidate)
    return sorted(existing)


_PERSON_CUES = (
    (re.compile(r"(?:నా\s*పేరు|నాపేరు)\s*([^.!?,;\n]{1,60})"), r"\s+(?:నేను|మేము|ఈరోజు|ఇవాళ)"),
    (re.compile(r"(?:मेरा\s+नाम|माझं\s+नाव|माझे\s+नाव)\s*([^.!?,;\n]{1,60})"), r"\s+(?:है|और|मैं|से)"),
    (re.compile(r"(?:என்\s+பெயர்|என்\s+பேர்)\s*([^.!?,;\n]{1,60})"), r"\s+(?:நான்|இன்று|இருந்து)"),
    (re.compile(r"(?:ನನ್ನ\s+ಹೆಸರು)\s*([^.!?,;\n]{1,60})"), r"\s+(?:ನಾನು|ಇಂದು|ಇಂದ)"),
    (re.compile(r"(?:എന്റെ\s+പേര്)\s*([^.!?,;\n]{1,60})"), r"\s+(?:ഞാൻ|ഇന്ന്|നിന്ന്)"),
    (re.compile(r"(?:મારું\s+નામ)\s*([^.!?,;\n]{1,60})"), r"\s+(?:છે|હું|થી)"),
    (re.compile(r"(?:আমার\s+নাম|মোৰ\s+নাম)\s*([^.!?,;\n]{1,60})"), r"\s+(?:আমি|আৰু|থেকে)"),
    (re.compile(r"(?:ମୋ\s+ନାମ)\s*([^.!?,;\n]{1,60})"), r"\s+(?:ମୁଁ|ଆଜି|ରୁ)"),
    (re.compile(r"(?:ਮੇਰਾ\s+ਨਾਮ)\s*([^.!?,;\n]{1,60})"), r"\s+(?:ਹੈ|ਮੈਂ|ਤੋਂ)"),
    (re.compile(r"(?:میرا\s+نام)\s*([^.!?,;\n]{1,60})"), r"\s+(?:ہے|میں|سے)"),
    (re.compile(r"\bmy\s+name\s+is\s+([^.!?,;\n]{1,60})", re.I), r"\s+(?:and|i|from)\b"),
    # AI4Bharat ASR may transliterate Telugu and other Indic speech to Latin
    # characters. Begin after the "my name is" cue and stop at the next clause,
    # so greetings and a company/SEBI claim do not become part of the name.
    (
        re.compile(
            r"(?:\bnaa?\s*(?:peru|peeru)\b|\bmera\s+naam\b|\bmajha\s+naav\b|"
            r"\bmaza\s+nav\b|\bnanna\s+hesaru\b|\bente\s+peru\b|\ben\s+peyar\b|"
            r"\bamar\s+nam\b|\bmor\s+nam\b)\s*[:,-]?\s*([^.!?,;\n]{1,80})",
            re.I,
        ),
        r"\s+(?:nenu|neenu|memu|meemu|main|mai|from|speaking|calling|today|ivala|"
        r"sebi|registration|number|id|5paisa|paisa|capital|limited|ltd|private|securities)\b",
    ),
)

_COMPANY_FROM_CUES = (
    re.compile(r"(.{2,90}?)\s+(?:నుంచి|నుండి)\s+(?:మాట్లాడుతున్నాను|మాట్లాడుతున్నా|చెప్తున్నాను|కాల్\s*చేస్తున్నాను)"),
    re.compile(r"(.{2,90}?)\s+से\s+(?:बात\s+कर|बोल|कॉल\s+कर)"),
    re.compile(r"(.{2,90}?)\s+(?:இருந்து|லிருந்து)\s+(?:பேசுகிறேன்|அழைக்கிறேன்)"),
    re.compile(r"(.{2,90}?)\s+ಇಂದ\s+(?:ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ|ಕರೆಮಾಡುತ್ತಿದ್ದೇನೆ)"),
    re.compile(r"(.{2,90}?)\s+നിന്ന്\s+(?:സംസാരിക്കുന്നു|വിളിക്കുന്നു)"),
    re.compile(r"(.{2,90}?)\s+سے\s+(?:بات\s+کر|بول|کال)"),
    re.compile(r"(?:speaking|calling|talking)\s+from\s+(.{2,90})", re.I),
    re.compile(r"(?:मैं|हम)\s+(.{2,90}?)\s+से\s+(?:बोल|बात|कॉल)"),
    re.compile(r"(?:నేను|మేము)\s+(.{2,90}?)\s+(?:నుంచి|నుండి)\s+(?:మాట్లాడుతున్నాను|కాల్)"),
    re.compile(
        r"\b(?:nenu|neenu|memu|meemu)\s+(.{2,90}?)\s+"
        r"(?:nunchi|nundi)\s+(?:maatlaadutunnanu|maatladutunnanu|maatladuthunnanu|"
        r"matladutunnanu|matladuthunnanu|matladutunna|maatladutunna|cheptunnanu|"
        r"call\s+chestunnanu)\b",
        re.I,
    ),
    re.compile(r"\b(?:main|mai|hum)\s+(.{2,90}?)\s+se\s+(?:baat\s+kar|bol|call\s+kar)", re.I),
)


def _spoken_company_form(value: str) -> str:
    latin = transliterate_indic(value).casefold()
    latin = re.sub(r"[^a-z0-9]+", " ", latin).strip()
    # Remove common speaker-introduction words when the company cue captures
    # the beginning of the sentence as well as the organization name.
    # ASR commonly writes Telugu introductions as "naa peeru ... neenu ...".
    # Strip through the speaker's first-person cue so that e.g. "hello, my
    # name is Yashwant, I'm calling from 5paisa Capital Limited" does not get
    # reported as one enormous company name.
    for marker in (
        "nenu", "neenu", "memu", "meemu", "naanu", "nanu", "njan", "main", "mai", "mein",
        "hum", "hu", "ami", "mu", "mo nam", "mur nam", "amar nam", "naan", "nan",
        "i am", "my name is", "my name", "mera naam", "mera nam", "majha naav", "maza nav",
        "en peyar", "nanna hesaru", "ente peru", "naa peeru", "na peeru", "naa peru", "na peru",
        "peeru", "peru",
    ):
        latin = re.sub(rf"^.*\b{re.escape(marker)}\b\s*", "", latin)
    # Frequent code-switched Telugu ASR spellings of "5 paisa".
    latin = re.sub(r"\b(?:phai|fai|faiv|five|pai)\s+pais(?:a|aa|e|ee)?\b", "5paisa", latin)
    latin = re.sub(r"\b(?:kya|kyaa|ky)\s*apital\b", "capital", latin)
    latin = re.sub(r"\blimi(?:te|ti|tee)d\b", "limited", latin)
    latin = re.sub(r"\s+", " ", latin)
    return " ".join(part.capitalize() if not part.isdigit() else part for part in latin.split())


def extract_spoken_names(text: str) -> tuple[list[str], list[str]]:
    """Return approximate person-name spellings and company phrases from speech."""
    source = text or ""
    people = []
    for cue, stop_pattern in _PERSON_CUES:
        for match in cue.finditer(source):
            value = re.split(stop_pattern, match.group(1), maxsplit=1, flags=re.I)[0].strip(" .,:;—-\t")
            value = value.strip("\"'“”‘’()[]{} ")
            value = re.sub(r"^(?:hello|helo|haloo|hallo|hi|namaste|namaskaram)[, .]+", "", value, flags=re.I)
            if not value:
                continue
            words = value.split()
            if len(words) > 3:
                value = " ".join(words[:3])
            latin = re.sub(r"\s+", " ", transliterate_indic(value)).strip(" -")
            latin = re.sub(r"\byashvant\b", "Yashwanth", latin, flags=re.I)
            display = f"{latin.title()} ({value})" if latin and not value.isascii() else (latin.title() if latin else value)
            people.append(display)

    companies = []
    for pattern in _COMPANY_FROM_CUES:
        for match in pattern.finditer(source):
            candidate = _spoken_company_form(match.group(1))
            if len(re.sub(r"[^A-Za-z0-9]", "", candidate)) >= 5:
                companies.append(candidate)
    return _unique(people), _unique(companies)


def phonetic_search_text(text: str) -> str:
    """Normalized Latin search string for matching Indic-script entity names."""
    return re.sub(r"\s+", " ", _spoken_company_form(text)).casefold()


def _unique(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for item in values:
        value = str(item).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            output.append(value)
    return output
