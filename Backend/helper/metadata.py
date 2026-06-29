import asyncio
import re
import traceback
import unicodedata
from typing import Optional, List

import PTN

import Backend
from Backend.logger import LOGGER
from Backend.helper.imdb import get_detail, get_season, search_title, search_title_multi
from Backend.helper.settings_manager import SettingsManager
from Backend.helper.encrypt import encode_string
from Backend.helper.split_files import parse_split_info, parse_combined_episodes, strip_part_suffix
from Backend.helper.anime import fetch_anime_metadata, fetch_anime_movie_metadata
from themoviedb import aioTMDb
from rapidfuzz import fuzz
from guessit import guessit as _guessit
from difflib import SequenceMatcher

# IMDbPy fallback (optional — import failure is non-fatal)
try:
    from imdb import Cinemagoer
    _IMDBPY = Cinemagoer()
except Exception:
    _IMDBPY = None

# ── Known series episode database (extensible) ────────────────────────────
# Format: { normalized_key: { aliases: [...], seasons: { N: [titles] } } }
# Used for exact + fuzzy episode title lookup when filenames are messy.
_KNOWN_SERIES_DB: dict = {
    "aida": {
        "aliases": ["aida", "aida", "aida"],
        "canonical": "Aida",
        "seasons": {
            1: [
                "La primera vez", "El divorcio", "La enfermedad", "El colesterol",
                "El primer beso", "La depresion", "El trabajo", "Los estudios",
                "La boda", "La luna de miel", "La vuelta a casa", "El embarazo",
                "La despedida", "El funeral",
            ],
            2: [
                "El regreso", "La nueva casa", "El vecino", "La fiesta",
                "El accidente", "La operacion", "El engaño", "La verdad",
                "La crisis", "El pasado", "La decision", "El secreto",
                "La sorpresa", "El viaje",
            ],
            3: [
                "La ruina", "El dinero", "La apuesta", "El concurso",
                "La infidelidad", "El rumor", "La tentacion", "Las insaciables de Elliot Ness",
                "The fast and the furioso", "La entrevista", "El secuestro",
                "La rebelion", "El sustituto", "La encuesta",
            ],
            4: [
                "Misterioso asesinato en Esperanza Sur", "El ostion The spanish golpe",
                "El pueblo de la alegria", "La liga de la justicia",
                "El inspector", "La mudanza", "El aniversario", "La ruina total",
                "El reencuentro", "La oferta", "El concurso de baile",
                "La despedida de soltera", "El juicio", "La venganza",
            ],
            5: [
                "El regreso de Loren", "La boda de Mauricio", "El secreto de Luisma",
                "La nueva vida", "El accidente de Paz", "La decisión de Chema",
                "El pasado de Eugenia", "La sorpresa de Aida", "El viaje a Benidorm",
                "La envidia", "El rescate", "La mentira",
                "El juego", "La confesion",
            ],
            6: [
                "El atropello", "La prima de Chema", "El concurso de talentos",
                "La reunion", "El negocio", "La adivinacion",
                "El incendio", "La fuga", "El diagnostico",
                "La llegada de Tony", "El secuestro de Fidel", "La sustituta",
                "El campeonato", "La visita",
            ],
            7: [
                "La caza del tesoro", "El recuerdo", "La jefa", "El fichaje",
                "La enfermedad de Barajas", "El enfrentamiento", "La tregua",
                "El atraco", "La herencia", "El cumpleaños",
                "La protesta", "El fugitivo", "La confianza",
                "La despedida",
            ],
            8: [
                "El nuevo Barajas", "La rival", "El misterio", "La invasion",
                "El concurso de recetas", "La fiesta de disfraces", "El secuestro de Nico",
                "La mala suerte", "El castillo", "La competitividad",
                "El experimento", "La duda", "El bazar",
                "La prueba", "El rumor de la semana", "La llamada",
                "El profesor", "La rebelion de los mirones", "El rescate de Aida",
                "La decisión de Paz", "El sustituto de Luisma", "La importancia de llamarse Chema",
                "El fichaje de Mauricio", "La cena de Navidad", "El examen",
                "La llamada de la selva",
            ],
            9: [
                "La vuelta de Tony", "El premio", "La amenaza", "El choque",
                "La fiesta del agua", "El rescate de Loren", "La caravana",
                "El sorteo", "La acampada", "El regreso del hijo prodigo",
                "La suegra", "El pacto", "La tentacion de Machupichu",
                "El cuento", "La fatalidad", "El milagro",
                "La monja", "El mal de amores", "La plaga",
                "El desafio", "La estrella", "El aprendiz",
                "La ganga", "El viaje a la India", "La mentira tiene patas cortas",
                "La boda de paz", "El atraco perfecto", "La despedida de soltero",
                "El examen de conducir", "La noche de los muertos vivientes",
                "La llamada de la selva",
            ],
            10: [
                "El fin del mundo", "La mudanza de Paz", "El viaje de Aida",
                "La nueva era", "El regreso a Esperanza Sur", "La onda expansiva",
                "El secreto de Mauricio", "La ultima cena", "El rescate",
                "La decision", "El testamento", "La mora chanante",
                "El reencuentro", "La despedida", "El milagro de Esperanza Sur",
                "La foto de familia", "El legado", "La promesa",
                "El cambio", "La herencia de Aida", "El fin de una era",
                "La gala de la alegria", "El secreto de Barajas", "La ultima oportunidad",
                "El adiós", "La reunion final",
            ],
        },
    },
}

# Emoji pattern (mirrors the one in pyro.py — used in _aggressive_normalize for DB matching)
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "\uFE00-\uFE0F"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    re.UNICODE,
)

# Hashtag pattern (#word → stripped before matching)
_HASHTAG_RE = re.compile(r"#\w+")

# Series that should always be treated as TV (never as movie)
_SPANISH_TV_SERIES = [
    "aida", "aída", "los simpson", "la que se avecina", "aquí no hay quien viva",
    "el intermedio", "el hormiguero", "cuéntame", "la casa de papel",
    "el ministerio del tiempo", "vis a vis", "merlí", "sé quién eres",
    "fariña", "el pueblo", "caronte", "estoy vivo", "la casa de las flores",
    "club de cuervos", "la niña",
]


def _aggressive_normalize(name: str) -> str:
    """Ultra-aggressive normalization for messy filenames with mixed encodings.

    Handles: accents, underscores, dots, ellipsis, mixed case, trailing cruft.
    Returns a lowercase, ASCII-folded, single-space-separated string.
    """
    if not name:
        return ""
    # 1. Remove common video extensions
    name = re.sub(r'\.(mkv|mp4|avi|ts|m4v|mov|wmv|webm|flv|mpg|mpeg|m2ts|3gp)$',
                  '', name, flags=re.IGNORECASE)
    # 2. Strip emojis
    name = _EMOJI_RE.sub(' ', name)
    # 3. Strip hashtags (never part of a title)
    name = _HASHTAG_RE.sub(' ', name)
    # 4. Unicode normalize (NFD) + strip combining diacritics
    name = unicodedata.normalize('NFD', name)
    name = re.sub(r'[\u0300-\u036f]', '', name)
    # 5. Replace all separators with spaces
    name = re.sub(r'[._\-\[\](){}]+', ' ', name)
    # 6. Replace ellipsis and similar
    name = re.sub(r'[…‥⋮⋯]+', ' ', name)
    # 7. Remove trailing junk like " - ", " .", spaces
    name = name.strip().rstrip('.-_ ')
    # 8. Lowercase
    name = name.lower()
    # 9. Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _normalize_series_title(name: str) -> str:
    """Normalize a series title for database lookup (strip articles, etc.)."""
    n = _aggressive_normalize(name or "")
    # Strip leading articles in Spanish and English
    n = re.sub(r'^(el|la|los|las|the|a|an|un|una)\s+', '', n)
    return n.strip()


def _find_known_series(name: str) -> str | None:
    """Check if a filename (aggressively normalized) matches any known series."""
    if not name:
        return None
    norm = _aggressive_normalize(name)
    # Check against the whole filename
    for key, data in _KNOWN_SERIES_DB.items():
        if key in norm:
            return key
        for alias in data.get("aliases", []):
            if alias in norm:
                return key
    # Also check if the title starts with a known series
    title_part = norm.split()[0] if norm.split() else ""
    for key, data in _KNOWN_SERIES_DB.items():
        if title_part in (key, *data.get("aliases", [])):
            return key
        for alias in data.get("aliases", []):
            if title_part == alias:
                return key
    return None


def _normalize_episode_title(raw_title: str) -> str:
    """Clean a raw episode title extracted from a filename."""
    if not raw_title:
        return ""
    t = raw_title.strip()
    # Remove leading/trailing separators
    t = t.strip('.-_[](){} ')
    # Remove trailing " - " pattern
    t = re.sub(r'\s*[-–—]\s*$', '', t)
    # Remove dangling quality tags
    t = re.sub(r'\b(720p|1080p|2160p|4k|uhd|hdtv|webdl|webrip|bluray|x264|x265|hevc|aac|dd5[.]1)\b',
               '', t, flags=re.IGNORECASE)
    # Remove isolated numbers at the end (not episode years)
    t = re.sub(r'\s+\d{3,4}\s*$', '', t)
    # Remove trailing dots that are leftovers
    t = t.rstrip('. ')
    # Collapse spaces
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _extract_episode_title_from_name(name: str, season: int, episode: int) -> str | None:
    """Extract the episode title from a filename by stripping the S/E prefix.

    Works with formats like:
      - 'Aida 3x8 Las insaciables de Elliot Ness' -> 'Las insaciables de Elliot Ness'
      - 'Aida_S09E31_Las…ara el tarado'          -> 'Las…ara el tarado' (fuzzy-recovered)
      - 'Aida 8x26'                                -> None (no title present)
    """
    if not name or season is None or episode is None:
        return None

    norm = _aggressive_normalize(name)

    # Build patterns matching the S/E portion in various formats
    fmt_pairs = [
        rf'\b{season}x{episode:02d}\b',
        rf'\b{season}x{episode:d}\b',
        rf'\bs(?:eason)?0*{season:d}e(?:p(?:isode)?)?0*{episode:d}\b',
        rf'\bs(?:eason)?{season:d}e(?:p(?:isode)?)?{episode:d}\b',
        rf'\be(?:p(?:isode)?)?0*{episode:d}\s*s(?:eason)?0*{season:d}\b',
        rf'\be(?:p(?:isode)?)?{episode:d}\s*s(?:eason)?{season:d}\b',
        rf'\bt(?:emporada)?0*{season:d}e(?:p(?:isode)?)?0*{episode:d}\b',
        rf'\bt(?:emporada)?{season:d}e(?:p(?:isode)?)?{episode:d}\b',
    ]

    for pat in fmt_pairs:
        m = re.search(pat, norm, re.IGNORECASE)
        if m:
            after = norm[m.end():].strip()
            # Remove common trailing cruft
            after = re.sub(
                r'\b(720p|1080p|2160p|4k|uhd|hdtv|web[-\s]?dl|bluray|webrip|x264|x265|hevc|'
                r'mixed|dual|audio|aac|dd\d[.]\d|ac3|dts|h264|10bit)\b',
                '', after, flags=re.IGNORECASE,
            )
            after = re.sub(r'\b(19|20)\d{2}\b', '', after)
            after = re.sub(r'\s+', ' ', after).strip()
            after = after.rstrip('. ')
            if after:
                return _normalize_episode_title(after)
            break

    return None


def _match_known_episode(series_key: str, season: int, episode: int) -> str | None:
    """Look up a known episode title by series + season + episode number."""
    data = _KNOWN_SERIES_DB.get(series_key)
    if not data:
        return None
    seasons = data.get("seasons", {})
    if season not in seasons:
        return None
    eps = seasons[season]
    idx = episode - 1
    if 0 <= idx < len(eps):
        return eps[idx]
    return None


async def _imdbpy_episode_lookup(series_title: str, season: int, episode: int) -> dict | None:
    """Look up episode details via IMDbPy when known-DB lookup fails.

    Returns a dict with 'imdb_id', 'season', 'episode', 'episode_title' if found.
    """
    if _IMDBPY is None:
        return None
    try:
        loop = asyncio.get_event_loop()
        # First search for the series
        results = await loop.run_in_executor(
            None, lambda: _IMDBPY.search_movie(series_title)[:3]
        )
        if not results:
            return None

        # Find best series match
        best = None
        for r in results:
            kind = r.get("kind", "")
            if kind in ("tv series", "tv mini series", "tv"):
                if best is None:
                    best = r
        if best is None:
            best = results[0]

        series_imdb = best.movieID
        # Get series details including episodes
        try:
            series_obj = await loop.run_in_executor(
                None, lambda: _IMDBPY.get_movie(series_imdb)
            )
        except Exception:
            series_obj = None

        if series_obj is None:
            return None

        # Try to get episode data
        try:
            _IMDBPY.update(series_obj, "episodes")
        except Exception:
            pass

        episodes_data = getattr(series_obj, "data", {}).get("episodes", {})
        if not episodes_data:
            # Alternative: try get_all_episodes or similar
            try:
                _IMDBPY.update(series_obj, "episodes")
                episodes_data = series_obj.get("episodes", {})
            except Exception:
                episodes_data = {}

        season_data = episodes_data.get(season, {}) if isinstance(episodes_data, dict) else {}
        if isinstance(season_data, dict) and episode in season_data:
            ep_obj = season_data[episode]
            ep_title = ep_obj.get("title", "") if isinstance(ep_obj, dict) else ""
            if isinstance(ep_obj, dict) and ep_title:
                return {
                    "imdb_id": f"tt{series_imdb}",
                    "season": season,
                    "episode": episode,
                    "episode_title": ep_title,
                }

        # Fallback: try get_episode_details
        try:
            ep_obj = await loop.run_in_executor(
                None, lambda: _IMDBPY.get_episode(series_imdb, season, episode)
            )
        except Exception:
            ep_obj = None

        if ep_obj:
            ep_title = ep_obj.get("title", "")
            if ep_title:
                return {
                    "imdb_id": f"tt{series_imdb}",
                    "season": season,
                    "episode": episode,
                    "episode_title": ep_title,
                }

    except Exception as e:
        LOGGER.warning(f"IMDbPy episode lookup failed for '{series_title}' S{season}E{episode}: {e}")
    return None


def _is_known_tv_series(title: str) -> bool:
    """Check if a title is a known Spanish TV series (never a movie)."""
    if not title:
        return False
    norm = _normalize_series_title(title)
    for s in _SPANISH_TV_SERIES:
        if s == norm or s in norm:
            return True
    # Also check known series DB
    for data in _KNOWN_SERIES_DB.values():
        canon = data.get("canonical", "").lower()
        if canon and (canon == norm or canon in norm):
            return True
    return False


def _apply_known_series_corrections(filename: str, parsed: dict) -> dict:
    """Apply known-series corrections to parsed metadata.

    1. Detect known TV series in the filename (overrides movie detection)
    2. Look up episode title from known DB if filename lacks it
    3. Fix season/episode if known DB says differently
    """
    if not filename or not parsed:
        return parsed

    result = dict(parsed)
    norm = _aggressive_normalize(filename)

    # Detect known series
    series_key = _find_known_series(norm)
    if not series_key:
        return result

    # Force TV type if we detected a known series
    series_data = _KNOWN_SERIES_DB.get(series_key, {})
    canonical = series_data.get("canonical", series_key)
    if not result.get("title"):
        result["title"] = canonical
    else:
        # Check if the parsed title looks like the series (fuzzy)
        title_sim = _title_similarity(result["title"], canonical)
        if title_sim < 0.5:
            # Parsed title is probably an episode title, not the series title
            # Keep the parsed episode info but fix series title
            result["title"] = canonical

    season = result.get("season")
    episode = result.get("episode")

    if season is not None and episode is not None:
        # Try to get known episode title
        known_title = _match_known_episode(series_key, int(season), int(episode))
        if known_title:
            # Check if the filename actually has a title string
            extracted_title = _extract_episode_title_from_name(filename, int(season), int(episode))
            if extracted_title:
                # Fuzzy match extracted vs known
                sim = _title_similarity(extracted_title, known_title)
                if sim < 0.4:
                    # Extracted title is too different — replace with known
                    result["episode_title"] = known_title
                    LOGGER.info(
                        f"Known-series correction: '{canonical}' S{season:02d}E{episode:02d} "
                        f"extracted='{extracted_title}' vs known='{known_title}' "
                        f"(sim={sim:.2f})"
                    )
                else:
                    result["episode_title"] = extracted_title
                    LOGGER.info(
                        f"Known-series match: '{canonical}' S{season:02d}E{episode:02d} "
                        f"-> '{known_title}'"
                    )
            else:
                # No title in filename — use known title
                result["episode_title"] = known_title
                LOGGER.info(
                    f"Known-series title fill: '{canonical}' S{season:02d}E{episode:02d} -> '{known_title}'"
                )

    # Force media_type to tv for known series
    if not result.get("media_type"):
        result["media_type"] = "tv"

    return result


def _preprocess_raw_name(name: str) -> str:
    """Clean raw input text before metadata parsing.

    Handles text that may not have gone through pyro.clean_filename():
    - Strips emojis
    - Strips hashtags (#word → empty)
    - Strips Spanish subtitle/filler words
    - Collapses whitespace (including newlines)
    """
    if not name:
        return ""
    name = _EMOJI_RE.sub(" ", name)
    name = _HASHTAG_RE.sub(" ", name)
    # Collapse newlines and extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _fuzzy_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    try:
        set_ratio = fuzz.token_set_ratio(a, b) / 100.0
        sort_ratio = fuzz.token_sort_ratio(a, b) / 100.0
        a_tokens, b_tokens = a.split(), b.split()
        if a_tokens and b_tokens:
            coverage = min(len(a_tokens), len(b_tokens)) / max(len(a_tokens), len(b_tokens))
        else:
            coverage = 0.0
        return max(sort_ratio, set_ratio * coverage)
    except Exception:
        return SequenceMatcher(None, a, b).ratio()


_CINEMETA_THRESHOLD = 0.60
_TMDB_THRESHOLD = 0.55
_STRONG_MATCH = 0.92
_ALT_TITLE_LOOKUPS = 5

IMDB_CACHE: dict = {}
TMDB_SEARCH_CACHE: dict = {}
TMDB_DETAILS_CACHE: dict = {}
EPISODE_CACHE: dict = {}
ALT_TITLES_CACHE: dict = {}

API_SEMAPHORE = asyncio.Semaphore(12)

_MULTIPART_RE = re.compile(r"(?:part|cd|disc|disk)[s._-]*\d+(?=\.\w+$)", re.IGNORECASE)

# Combined files are grouped in the Specials folder (season 0) as a single
# "Season N Combined" entry per real season.
COMBINED_SEASON = 0
COMBINED_EPISODE_BASE = 1000


# Re-file a combined entry into its season's single Combined slot inside Specials.
# A range/Full label is appended to the quality so distinct combined files coexist
# while an identical re-upload still replaces correctly under replace mode.
def _apply_combined_override(payload: dict, combined: dict) -> None:
    season, start, end = combined["season"], combined["start"], combined["end"]
    payload["season_number"] = COMBINED_SEASON
    payload["episode_number"] = COMBINED_EPISODE_BASE + season
    payload["episode_title"] = f"Season {season} Combined"
    label = "Full" if start is None else f"E{start:02d}-E{end:02d}"
    payload["quality"] = f"{payload.get('quality') or 'HD'} {label}"
    if not payload.get("episode_backdrop"):
        payload["episode_backdrop"] = payload.get("backdrop") or payload.get("poster") or ""

_tmdb_client: aioTMDb | None = None
_tmdb_client_key: str | None = None


# Return a cached TMDb client, rebuilding it when the configured API key changes.
def get_tmdb_client() -> aioTMDb:
    global _tmdb_client, _tmdb_client_key
    current_key = SettingsManager.current().tmdb_api
    if _tmdb_client is None or _tmdb_client_key != current_key:
        _tmdb_client = aioTMDb(key=current_key, language="en-US", region="US")
        _tmdb_client_key = current_key
    return _tmdb_client


def format_tmdb_image(path: str, size="w500") -> str:
    return f"https://image.tmdb.org/t/p/{size}{path}" if path else ""

def get_tmdb_logo(images) -> str:
    logos = getattr(images, "logos", None) if images else None
    if not logos:
        return ""
    for logo in logos:
        if getattr(logo, "iso_639_1", None) == "en" and getattr(logo, "file_path", None):
            return format_tmdb_image(logo.file_path, "w300")
    for logo in logos:
        if getattr(logo, "file_path", None):
            return format_tmdb_image(logo.file_path, "w300")
    return ""

def format_imdb_images(imdb_id: str) -> dict:
    if not imdb_id:
        return {"poster": "", "backdrop": "", "logo": ""}
    return {
        "poster": f"https://images.metahub.space/poster/small/{imdb_id}/img",
        "backdrop": f"https://images.metahub.space/background/medium/{imdb_id}/img",
        "logo": f"https://images.metahub.space/logo/medium/{imdb_id}/img",
    }


def extract_default_id(text: str) -> str | None:
    if not text:
        return None
    bare_imdb = re.search(r"\b(tt\d{7,10})\b", text)
    if bare_imdb:
        return bare_imdb.group(1)
    imdb_url = re.search(r"/title/(tt\d+)", text)
    if imdb_url:
        return imdb_url.group(1)
    tmdb_url = re.search(r"/(?:movie|tv)/(\d+)", text)
    if tmdb_url:
        return tmdb_url.group(1)
    return None

def _split_default_id(default_id) -> tuple[str | None, int | None, bool, bool]:
    if not default_id:
        return None, None, False, False
    value = str(default_id).strip()
    if value.startswith("tt"):
        return value, None, True, False
    if value.isdigit():
        return None, int(value), False, True
    return None, None, False, False

def _normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"^\b(the|a|an)\b\s+", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def _title_similarity(t1: str, t2: str) -> float:
    n1, n2 = _normalize_title(t1), _normalize_title(t2)
    if not n1 or not n2:
        return 0.0
    return _fuzzy_ratio(n1, n2)

def _year_from_str(year_val) -> int:
    if not year_val:
        return 0
    m = re.search(r"(\d{4})", str(year_val))
    return int(m.group(1)) if m else 0

def _score_candidate(
    query_title: str,
    query_year: Optional[int],
    result_title: str,
    result_year: int,
    year_reliable: bool = True,
) -> float:
    score = _title_similarity(query_title, result_title)
    
    if score < 0.5:
        return score

    if query_year and result_year:
        diff = abs(int(query_year) - result_year)
        if year_reliable:
            if diff > 2:
                score = max(0.0, score - 0.10 * (diff - 2))
            elif score >= 0.80:
                if diff == 0:
                    score = min(1.0, score + 0.20)
                elif diff == 1:
                    score = min(1.0, score + 0.07)
        else:
            if diff == 0 and score >= 0.80:
                score = min(1.0, score + 0.05)
    return score

def _build_query_variants(title: str, year: Optional[int] = None) -> List[str]:
    variants: List[str] = [title]
    if year:
        variants.append(f"{title} {year}")

    stripped = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title)).strip()
    if stripped and stripped.lower() != title.lower():
        variants.append(stripped)
        if year:
            variants.append(f"{stripped} {year}")

    no_article = re.sub(r"^\b(the|a|an)\b\s+", "", title, flags=re.IGNORECASE).strip()
    if no_article and no_article.lower() != title.lower():
        variants.append(no_article)

    seen: set = set()
    ordered: List[str] = []
    for v in variants:
        key = v.lower()
        if v and key not in seen:
            seen.add(key)
            ordered.append(v)
    return ordered

def _first(value):
    return value[0] if isinstance(value, list) else value

def _spanish_parse(name: str) -> dict:
    """Parse Spanish / alternative filename formats that PTN or guessit may miss.

    Handles:
      - 1x01, 01x01, 1X01, 01X01
      - E01S01, E1S1, Ep01S01 (episode-first order)
      - T01E01 / Temporada 1 Episodio 1 / Capitulo 1
      - Season/Episode followed by an episode title in the filename
      - Various separators: spaces, dots, underscores, bars
    """
    result = {}
    if not name:
        return result

    lower = name.lower()

    # ── Pattern A: E01S01 / E1S1 / Ep01S01 / Episodio01Temporada01 ──────
    # Accepts zero-or-more separator between episode number and season prefix
    # so both "E1 S1" and "E1S1" (compact, no space) are matched.
    m = re.search(
        r'(?:E|Ep|Episodio)[\s._-]*(\d{1,3})'
        r'[\s._-]*'
        r'(?:S|Season|T|Temporada)[\s._-]*(\d{1,2})',
        name, re.IGNORECASE,
    )
    if m:
        result['episode'] = int(m.group(1))
        result['season'] = int(m.group(2))

    # ── Pattern B: 1x01, 01x01, Temporada 1 x Episodio 01 ────────────────
    if 'season' not in result:
        m = re.search(
            r'(?:(?:S|Season|T|Temporada)[\s._-]*)?'
            r'(\d{1,2})[\s._]*[xX][\s._]*'
            r'(?:E|Ep|Episodio|Capitulo)?[\s._]*'
            r'(\d{1,3})',
            name, re.IGNORECASE,
        )
        if m:
            result['season'] = int(m.group(1))
            result['episode'] = int(m.group(2))

    # ── Pattern C: Temporada 1 Capitulo 1 (full Spanish words) ──────────
    if 'season' not in result:
        m = re.search(
            r'(?:T|Temporada)[\s._-]*(\d{1,2})'
            r'[\s._-]+'
            r'(?:E|Ep|Episodio|Capitulo)[\s._-]*(\d{1,3})',
            name, re.IGNORECASE,
        )
        if m:
            result['season'] = int(m.group(1))
            result['episode'] = int(m.group(2))

    # ── Extract title: everything before the matched pattern ─────────────
    if 'season' in result and not result.get('title'):
        # Find where the season/ep pattern starts
        se_positions = []
        for pat in [
            r'(?:E|Ep|Episodio)[\s._-]*\d{1,3}[\s._-]*(?:S|Season|T|Temporada)[\s._-]*\d{1,2}',
            r'(?:(?:S|Season|T|Temporada)[\s._-]*)?\d{1,2}[\s._]*[xX][\s._]*(?:E|Ep|Episodio|Capitulo)?[\s._]*\d{1,3}',
            r'(?:T|Temporada)[\s._-]*\d{1,2}[\s._-]+(?:E|Ep|Episodio|Capitulo)[\s._-]*\d{1,3}',
        ]:
            match = re.search(pat, name, re.IGNORECASE)
            if match:
                se_positions.append(match.start())
        if se_positions:
            cut = min(se_positions)
            title_candidate = name[:cut].strip().rstrip('.-_ []()')
            if title_candidate:
                result['title'] = title_candidate

    return result


def parse_media_name(name: str) -> dict:
    # Pre-process: strip emojis, hashtags, filler words before PTN
    name = _preprocess_raw_name(name)
    try:
        ptn = PTN.parse(name) or {}
    except Exception as e:
        LOGGER.warning(f"PTN parsing failed for {name}: {e}")
        ptn = {}

    parsed = {
        "title": ptn.get("title"),
        "year": ptn.get("year"),
        "season": ptn.get("season"),
        "episode": ptn.get("episode"),
        "quality": ptn.get("resolution"),
        "excess": ptn.get("excess"),
    }

    if _guessit:
        try:
            g = _guessit(name)
            parsed["title"] = parsed["title"] or _first(g.get("title"))
            parsed["year"] = parsed["year"] or _first(g.get("year"))
            parsed["season"] = parsed["season"] or _first(g.get("season"))
            parsed["episode"] = parsed["episode"] or _first(g.get("episode"))
            parsed["quality"] = parsed["quality"] or _first(g.get("screen_size"))
        except Exception as e:
            LOGGER.warning(f"GuessIt parsing failed for {name}: {e}")

    # Spanish/alternative format parser — fills what PTN + guessit missed
    sp = _spanish_parse(name)
    if sp.get("season") is not None and parsed.get("season") is None:
        parsed["season"] = sp["season"]
    if sp.get("episode") is not None and parsed.get("episode") is None:
        parsed["episode"] = sp["episode"]
    if sp.get("title") and not parsed.get("title"):
        parsed["title"] = sp["title"]

    # Known-series corrections: fix title, look up episode title, force TV type
    parsed = _apply_known_series_corrections(name, parsed)

    return parsed

async def safe_imdb_search(title: str, type_: str, year: Optional[int] = None) -> str | None:
    cache_key = f"imdb::{type_}::{title}::{year}"
    if cache_key in IMDB_CACHE:
        return IMDB_CACHE[cache_key]

    query_variants = _build_query_variants(title, year)
    best_id: str | None = None
    best_score = 0.0
    best_title = ""

    year_reliable = type_ == "movie"

    for query in query_variants:
        try:
            async with API_SEMAPHORE:
                results = await search_title_multi(query=query, type=type_, limit=8)
            for r in results:
                score = _score_candidate(
                    title, year, r.get("title", ""), _year_from_str(r.get("year", "")),
                    year_reliable=year_reliable,
                )
                if score > best_score:
                    best_score, best_id, best_title = score, r.get("id"), r.get("title", "")
                if best_score >= _STRONG_MATCH:
                    break
        except Exception as e:
            LOGGER.warning(f"Cinemeta search variant '{query}' [{type_}] failed: {e}")
        if best_score >= _STRONG_MATCH:
            break

    if best_score >= _CINEMETA_THRESHOLD and best_id:
        LOGGER.info(f"Cinemeta match: '{title}' (year={year}) -> '{best_title}' [{best_id}] (score={best_score:.2f})")
        IMDB_CACHE[cache_key] = best_id
        return best_id

    if best_id:
        LOGGER.info(
            f"Cinemeta low-confidence for '{title}' (year={year}, type={type_}) | "
            f"best '{best_title}' [{best_id}] score={best_score:.2f} -> falling back to TMDb"
        )
    else:
        LOGGER.info(f"Cinemeta returned no results for '{title}' (year={year}, type={type_}) -> falling back to TMDb")

    IMDB_CACHE[cache_key] = None
    return None

async def _tmdb_raw_search(title: str, media_type: str, year: Optional[int]):
    client = get_tmdb_client()
    async with API_SEMAPHORE:
        if media_type == "movie":
            results = await (client.search().movies(query=title, year=year) if year else client.search().movies(query=title))
            if not results and year:
                results = await client.search().movies(query=title)
            return results
        return await client.search().tv(query=title)

async def safe_tmdb_search(title: str, type_: str, year: Optional[int] = None):
    cache_key = f"tmdb_search::{type_}::{title}::{year}"
    if cache_key in TMDB_SEARCH_CACHE:
        return TMDB_SEARCH_CACHE[cache_key]

    try:
        results = await _tmdb_raw_search(title, type_, year)
        best = await _pick_best_tmdb_result(results, title, year, type_)
        if best is None and results:
            top = results[0]
            top_title = getattr(top, "title" if type_ == "movie" else "name", "?")
            LOGGER.info(f"TMDb '{title}' (year={year}) top result '{top_title}' did not meet threshold")
        TMDB_SEARCH_CACHE[cache_key] = best
        return best
    except Exception as e:
        LOGGER.error(f"TMDb search failed for '{title}' [{type_}]: {e}")
        TMDB_SEARCH_CACHE[cache_key] = None
        return None

def _tmdb_title_year(item, media_type: str) -> tuple[str, int]:
    if media_type == "movie":
        date = getattr(item, "release_date", None)
        return getattr(item, "title", "") or "", getattr(date, "year", 0) if date else 0
    date = getattr(item, "first_air_date", None)
    return getattr(item, "name", "") or "", getattr(date, "year", 0) if date else 0

async def _pick_best_tmdb_result(results, query_title: str, query_year: Optional[int], media_type: str):
    if not results:
        return None

    year_reliable = media_type == "movie"

    scored = []
    best_item, best_score = None, 0.0
    for item in results:
        r_title, r_year = _tmdb_title_year(item, media_type)
        score = _score_candidate(query_title, query_year, r_title, r_year, year_reliable=year_reliable)
        scored.append((score, item, r_year))
        if score > best_score:
            best_score, best_item = score, item

    if best_score >= _STRONG_MATCH:
        return best_item

    scored.sort(key=lambda x: x[0], reverse=True)
    for _, item, r_year in scored[:_ALT_TITLE_LOOKUPS]:
        alt_titles = await _tmdb_alternative_titles(media_type, getattr(item, "id", None))
        for alt in alt_titles:
            alt_score = _score_candidate(query_title, query_year, alt, r_year, year_reliable=year_reliable)
            if alt_score > best_score:
                best_score, best_item = alt_score, item
                if best_score >= _STRONG_MATCH:
                    break
        if best_score >= _STRONG_MATCH:
            break

    return best_item if best_score >= _TMDB_THRESHOLD and best_item is not None else None

async def _tmdb_alternative_titles(media_type: str, tmdb_id) -> list[str]:
    if not tmdb_id:
        return []
    cache_key = (media_type, tmdb_id)
    if cache_key in ALT_TITLES_CACHE:
        return ALT_TITLES_CACHE[cache_key]
    titles: list[str] = []
    try:
        client = get_tmdb_client()
        async with API_SEMAPHORE:
            target = client.movie(tmdb_id) if media_type == "movie" else client.tv(tmdb_id)
            alt = await target.alternative_titles()
        entries = list(getattr(alt, "titles", None) or []) + list(getattr(alt, "results", None) or [])
        titles = [t for t in (getattr(e, "title", "") for e in entries) if t]
    except Exception as e:
        LOGGER.warning(f"TMDb alternative-titles fetch failed for {media_type} id={tmdb_id}: {e}")
    ALT_TITLES_CACHE[cache_key] = titles
    return titles

async def _tmdb_details(media_type: str, item_id):
    cache_key = (media_type, item_id)
    if cache_key in TMDB_DETAILS_CACHE:
        return TMDB_DETAILS_CACHE[cache_key]
    try:
        client = get_tmdb_client()
        async with API_SEMAPHORE:
            target = client.movie(item_id) if media_type == "movie" else client.tv(item_id)
            details = await target.details(append_to_response="external_ids,credits")
            details.images = await target.images()
        TMDB_DETAILS_CACHE[cache_key] = details
        return details
    except Exception as e:
        LOGGER.warning(f"TMDb {media_type} details fetch failed for id={item_id}: {e}")
        TMDB_DETAILS_CACHE[cache_key] = None
        return None

async def _tmdb_episode_details(tv_id, season, episode):
    key = (tv_id, season, episode)
    if key in EPISODE_CACHE:
        return EPISODE_CACHE[key]
    try:
        async with API_SEMAPHORE:
            details = await get_tmdb_client().episode(tv_id, season, episode).details()
        EPISODE_CACHE[key] = details
        return details
    except Exception:
        EPISODE_CACHE[key] = None
        return None

async def _cached_imdb_detail(imdb_id: str, media_type: str):
    cached = IMDB_CACHE.get(imdb_id)
    if isinstance(cached, dict):
        return cached
    async with API_SEMAPHORE:
        detail = await get_detail(imdb_id=imdb_id, media_type=media_type)
    IMDB_CACHE[imdb_id] = detail
    return detail

async def _cached_imdb_season(imdb_id: str, season, episode):
    key = f"{imdb_id}::{season}::{episode}"
    if key in EPISODE_CACHE:
        return EPISODE_CACHE[key]
    async with API_SEMAPHORE:
        ep = await get_season(imdb_id=imdb_id, season_id=season, episode_id=episode)
    EPISODE_CACHE[key] = ep
    return ep

async def _tmdb_external_imdb_id(media_type: str, tmdb_id) -> str | None:
    try:
        details = await _tmdb_details(media_type, tmdb_id)
        ext = getattr(details, "external_ids", None) if details else None
        return getattr(ext, "imdb_id", None) if ext else None
    except Exception:
        return None



def _extract_cast(details) -> list:
    credits = getattr(details, "credits", None) or {}
    cast = getattr(credits, "cast", []) or []
    return [getattr(c, "name", None) or getattr(c, "original_name", None) for c in cast]


# Collect ISO 3166-1 country codes from a TMDb details object (origin_country
# and production_countries), used by the auto-catalog classifier.
def _tmdb_country_codes(details) -> list:
    codes: list = []
    for code in (getattr(details, "origin_country", None) or []):
        if code and code not in codes:
            codes.append(code)
    for country in (getattr(details, "production_countries", None) or []):
        code = getattr(country, "iso_3166_1", None) or (country.get("iso_3166_1") if isinstance(country, dict) else None)
        if code and code not in codes:
            codes.append(code)
    return codes


def _format_runtime(minutes) -> str:
    return f"{minutes} min" if minutes else ""


# Build the indexer movie payload from a TMDb details object.
def _build_tmdb_movie_payload(movie, quality, encoded_string) -> dict:
    release = getattr(movie, "release_date", None)
    return {
        "tmdb_id": movie.id,
        "imdb_id": getattr(getattr(movie, "external_ids", None), "imdb_id", None),
        "title": movie.title,
        "year": getattr(release, "year", 0) if release else 0,
        "rate": getattr(movie, "vote_average", 0) or 0,
        "description": movie.overview or "",
        "poster": format_tmdb_image(movie.poster_path),
        "backdrop": format_tmdb_image(movie.backdrop_path, "original"),
        "logo": get_tmdb_logo(getattr(movie, "images", None)),
        "cast": _extract_cast(movie),
        "runtime": str(_format_runtime(getattr(movie, "runtime", None))),
        "media_type": "movie",
        "genres": [g.name for g in (movie.genres or [])],
        "original_language": getattr(movie, "original_language", None),
        "origin_country": _tmdb_country_codes(movie),
        "quality": quality,
        "encoded_string": encoded_string,
    }


# Build the indexer TV payload from TMDb series + episode details.
def _build_tmdb_tv_payload(tv, ep, season, episode, quality, encoded_string) -> dict:
    first_air = getattr(tv, "first_air_date", None)
    series_runtime = tv.episode_run_time[0] if getattr(tv, "episode_run_time", None) else None
    runtime = _format_runtime((getattr(ep, "runtime", None) if ep else None) or series_runtime)
    fallback_ep_title = f"S{season:02d}E{episode:02d}"
    return {
        "tmdb_id": tv.id,
        "imdb_id": getattr(getattr(tv, "external_ids", None), "imdb_id", None),
        "title": tv.name,
        "year": getattr(first_air, "year", 0) if first_air else 0,
        "rate": getattr(tv, "vote_average", 0) or 0,
        "description": tv.overview or "",
        "poster": format_tmdb_image(tv.poster_path),
        "backdrop": format_tmdb_image(tv.backdrop_path, "original"),
        "logo": get_tmdb_logo(getattr(tv, "images", None)),
        "genres": [g.name for g in (tv.genres or [])],
        "media_type": "tv",
        "cast": _extract_cast(tv),
        "runtime": str(runtime),
        "original_language": getattr(tv, "original_language", None),
        "origin_country": _tmdb_country_codes(tv),
        "season_number": season,
        "episode_number": episode,
        "episode_title": getattr(ep, "name", fallback_ep_title) if ep else fallback_ep_title,
        "episode_backdrop": format_tmdb_image(getattr(ep, "still_path", None), "original") if ep else "",
        "episode_overview": getattr(ep, "overview", "") if ep else "",
        "episode_released": ep.air_date.strftime("%Y-%m-%dT05:00:00.000Z") if (ep and getattr(ep, "air_date", None)) else "",
        "quality": quality,
        "encoded_string": encoded_string,
    }


# Build the indexer movie payload from Cinemeta/IMDb details.
def _build_imdb_movie_payload(imdb, imdb_id, title, quality, encoded_string) -> dict:
    images = format_imdb_images(imdb_id)
    return {
        "tmdb_id": imdb.get("moviedb_id") or None,
        "imdb_id": imdb_id,
        "title": imdb.get("title", title),
        "year": imdb.get("releaseDetailed", {}).get("year", 0),
        "rate": imdb.get("rating", {}).get("star", 0),
        "description": imdb.get("plot", ""),
        "poster": images["poster"],
        "backdrop": images["backdrop"],
        "logo": images["logo"],
        "cast": imdb.get("cast", []),
        "runtime": str(imdb.get("runtime") or ""),
        "media_type": "movie",
        "genres": imdb.get("genre", []),
        "quality": quality,
        "encoded_string": encoded_string,
    }


# Build the indexer TV payload from Cinemeta/IMDb series + episode details.
def _build_imdb_tv_payload(imdb, ep, imdb_id, title, season, episode, quality, encoded_string) -> dict:
    images = format_imdb_images(imdb_id)
    return {
        "tmdb_id": imdb.get("moviedb_id") or None,
        "imdb_id": imdb_id,
        "title": imdb.get("title", title),
        "year": imdb.get("releaseDetailed", {}).get("year", 0),
        "rate": imdb.get("rating", {}).get("star", 0),
        "description": imdb.get("plot", ""),
        "poster": images["poster"],
        "backdrop": images["backdrop"],
        "logo": images["logo"],
        "cast": imdb.get("cast", []),
        "runtime": str(imdb.get("runtime") or ""),
        "genres": imdb.get("genre", []),
        "media_type": "tv",
        "season_number": season,
        "episode_number": episode,
        "episode_title": ep.get("title", f"S{season:02d}E{episode:02d}"),
        "episode_backdrop": ep.get("image", ""),
        "episode_overview": ep.get("plot", ""),
        "episode_released": str(ep.get("released", "")),
        "quality": quality,
        "encoded_string": encoded_string,
    }


# ----------------- Main entry-point -----------------

# True when a file's channel is configured as an anime channel.
def _is_anime_channel(channel) -> bool:
    anime_channels = SettingsManager.current().anime_channels
    if not anime_channels:
        return False
    target = str(channel).replace("-100", "")
    return any(str(c).strip().replace("-100", "") == target for c in anime_channels)


# Resolve anime TV metadata, filling the imdb_id from tmdb when ani.zip lacks it.
async def _fetch_anime_tv(title, season, episode, encoded_string, year, quality) -> dict | None:
    try:
        result = await fetch_anime_metadata(title, season, episode, encoded_string, year, quality)
    except Exception as e:
        LOGGER.warning(f"[ANIME] metadata error for '{title}': {e}")
        return None
    if result is None:
        return None
    if not result.get("imdb_id") and result.get("tmdb_id"):
        result["imdb_id"] = await _tmdb_external_imdb_id("tv", result["tmdb_id"])
    if not result.get("imdb_id"):
        LOGGER.info(f"[ANIME] No imdb id for '{title}' -> falling back to TMDb/Cinemeta")
        return None
    LOGGER.info(f"[ANIME] Matched '{result.get('title')}' [{result.get('imdb_id')}] S{season:02d}E{episode:02d}")
    return result


# Resolve anime movie metadata, filling the imdb_id from tmdb when ani.zip lacks it.
async def _fetch_anime_movie(title, encoded_string, year, quality) -> dict | None:
    try:
        result = await fetch_anime_movie_metadata(title, encoded_string, year, quality)
    except Exception as e:
        LOGGER.warning(f"[ANIME] movie metadata error for '{title}': {e}")
        return None
    if result is None:
        return None
    if not result.get("imdb_id") and result.get("tmdb_id"):
        result["imdb_id"] = await _tmdb_external_imdb_id("movie", result["tmdb_id"])
    if not result.get("imdb_id"):
        LOGGER.info(f"[ANIME] No imdb id for movie '{title}' -> falling back to TMDb/Cinemeta")
        return None
    LOGGER.info(f"[ANIME] Matched movie '{result.get('title')}' [{result.get('imdb_id')}]")
    return result


# Parse a filename/caption and resolve full movie or TV metadata for the indexer.
async def metadata(filename: str, channel: int, msg_id, override_id: str = None) -> dict | None:
    if _MULTIPART_RE.search(filename):
        LOGGER.info(f"Skipping {filename}: split video file not meant to be combined in Stremio")
        return None

    # Detect split parts (.001/.002 etc.) on the RAW name first, then parse all
    # metadata from the part-stripped name. If the numeric suffix is left in
    # place the parser misreads it as an episode number (and the year as a
    # season), e.g. a movie split "Memories (2013) ...mkv.001" wrongly becomes
    # "Memories S2013E01". Split detection is orthogonal to combined-episode
    # detection: a file can be BOTH split AND a combined/whole-season file, so
    # the parts of a split combined file still group (via group_key) and
    # recombine instead of landing in the combined folder as separate entries.
    split_info = parse_split_info(filename)
    part_number = split_info[1] if split_info else None
    parse_target = strip_part_suffix(filename) if split_info else filename

    try:
        parsed = parse_media_name(parse_target)
    except Exception as e:
        LOGGER.error(f"Parsing failed for {filename}: {e}\n{traceback.format_exc()}")
        return None

    combined = parse_combined_episodes(parse_target)

    excess = parsed.get("excess")
    if not combined and excess and any("combined" in item.lower() for item in excess):
        LOGGER.info(f"Skipping {filename}: contains 'combined'")
        return None

    title = parsed.get("title")
    season = parsed.get("season")
    episode = parsed.get("episode")
    year = parsed.get("year")
    quality = parsed.get("quality")

    if combined:
        season, episode = combined["season"], combined["start"] or 1
    elif isinstance(season, list) or isinstance(episode, list):
        LOGGER.warning(f"Invalid season/episode format for {filename}: {parsed}")
        return None
    elif season and not episode:
        # Season pack with no episode number (e.g. "Season 01") -> whole-season combined.
        combined = {"season": season, "start": None, "end": None}
        episode = 1
    if not quality:
        quality = "Unknown"
        LOGGER.info(f"No resolution found for {filename}, using 'Unknown' (parsed={parsed})")
    if not title:
        LOGGER.info(f"No title parsed from: {filename} (parsed={parsed})")
        return None

    default_id = _resolve_default_id(override_id, filename)

    try:
        encoded_string = await encode_string({"chat_id": channel, "msg_id": msg_id})
    except Exception:
        encoded_string = None

    group_key = f"{channel}:{quality}:{split_info[0]}" if split_info else None

    anime_channel = _is_anime_channel(channel)

    try:
        if season and episode:
            LOGGER.info(f"Fetching TV metadata: {title} S{season:02d}E{episode:02d} (year={year})")
            result = None
            if not default_id and anime_channel:
                result = await _fetch_anime_tv(title, season, episode, encoded_string, year, quality)
            if result is None:
                result = await fetch_tv_metadata(title, season, episode, encoded_string, year, quality, default_id)
            # Fallback 1: IMDbPy series search -> TV metadata
            if result is None and not default_id:
                LOGGER.info(f"TV fallback: trying IMDbPy for '{title}' S{season:02d}E{episode:02d}")
                imdbpy_id = await _imdbpy_search(title, "tv", year)
                if imdbpy_id:
                    result = await fetch_tv_metadata(title, season, episode, encoded_string, year, quality, default_id=imdbpy_id)
            # Fallback 2: IMDbPy episode-level lookup
            if result is None:
                ep_lookup = await _imdbpy_episode_lookup(title, int(season), int(episode))
                if ep_lookup:
                    LOGGER.info(
                        f"IMDbPy episode lookup gave '{ep_lookup.get('episode_title')}' "
                        f"for '{title}' S{season:02d}E{episode:02d} (imdb_id={ep_lookup.get('imdb_id')})"
                    )
                    result = await fetch_tv_metadata(
                        title, season, episode, encoded_string, year, quality,
                        default_id=ep_lookup["imdb_id"],
                    )
            # Fallback 3: known-series episode_title from parser
            if result is None and parsed.get("episode_title"):
                known_ep_title = parsed["episode_title"]
                LOGGER.info(
                    f"No API metadata found for '{title}' S{season:02d}E{episode:02d} — "
                    f"building minimal payload with known title '{known_ep_title}'"
                )
                result = {
                    "title": title,
                    "episode_title": known_ep_title,
                    "season_number": season,
                    "episode_number": episode,
                    "quality": quality,
                    "encoded_string": encoded_string,
                    "media_type": "tv",
                    "year": year or 0,
                    "rate": 0,
                    "description": "",
                    "poster": "",
                    "backdrop": "",
                    "logo": "",
                    "cast": [],
                    "runtime": "",
                    "genres": [],
                    "episode_backdrop": "",
                    "episode_overview": "",
                    "episode_released": "",
                }
            if result is not None and combined:
                _apply_combined_override(result, combined)
        else:
            LOGGER.info(f"Fetching Movie metadata: {title} (year={year})")
            result = None
            if not default_id and anime_channel:
                result = await _fetch_anime_movie(title, encoded_string, year, quality)
            if result is None:
                result = await fetch_movie_metadata(title, encoded_string, year, quality, default_id)
            if result is None and not default_id:
                LOGGER.info(f"Movie fallback: trying IMDbPy for '{title}' (year={year})")
                imdbpy_id = await _imdbpy_search(title, "movie", year)
                if imdbpy_id:
                    result = await fetch_movie_metadata(title, encoded_string, year, quality, default_id=imdbpy_id)
        if result is not None:
            if anime_channel:
                result["is_anime"] = True
            result["group_key"] = group_key
            result["part_number"] = part_number
        return result
    except Exception as e:
        LOGGER.error(f"Error while fetching metadata for {filename}: {e}\n{traceback.format_exc()}")
        return None


# Pick a default id from the override, the global setting, then the filename itself.
def _resolve_default_id(override_id, filename) -> str | None:
    for source in (override_id, getattr(Backend, "USE_DEFAULT_ID", None), filename):
        if not source:
            continue
        try:
            found = extract_default_id(source) or (override_id if source is override_id else None)
        except Exception:
            found = None
        if found:
            return found
    return None


# ── IMDbPy fallback (used when Cinemeta + TMDb both fail) ────────────────

async def _imdbpy_search(title: str, media_type: str, year: int | None = None) -> str | None:
    """Search IMDb via IMDbPy (cinemagoer) as a last-resort fallback."""
    if _IMDBPY is None:
        return None
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: _IMDBPY.search_movie(title)[:5]
        )
        if not results:
            return None
        best = None
        best_score = 0.0
        for r in results:
            r_title = r.get("title", "")
            r_year = r.get("year")
            score = _title_similarity(title, r_title)
            if year and r_year:
                diff = abs(int(year) - int(r_year))
                if diff > 2:
                    score *= 0.5
                elif diff == 0:
                    score *= 1.2
            if score > best_score:
                best_score = score
                best = r
        if best and best_score >= _CINEMETA_THRESHOLD:
            imdb_id = best.movieID
            LOGGER.info(
                f"IMDbPy fallback match: '{title}' -> '{best.get('title')}' "
                f"(id=tt{imdb_id}, score={best_score:.2f})"
            )
            return f"tt{imdb_id}"
    except Exception as e:
        LOGGER.warning(f"IMDbPy search failed for '{title}': {e}")
    return None


# ----------------- TV metadata -----------------

# Resolve TV metadata, preferring Cinemeta and falling back to TMDb.
async def fetch_tv_metadata(title, season, episode, encoded_string, year=None, quality=None, default_id=None) -> dict | None:
    imdb_id, tmdb_id, explicit_imdb_id, use_tmdb = _split_default_id(default_id)
    imdb_tv = None
    imdb_ep = None

    if not imdb_id and not tmdb_id:
        imdb_id = await safe_imdb_search(title, "tvSeries", year)
        use_tmdb = not bool(imdb_id)

    if imdb_id and not use_tmdb:
        try:
            imdb_tv = await _cached_imdb_detail(imdb_id, "tvSeries")
            imdb_ep = await _cached_imdb_season(imdb_id, season, episode)
        except Exception as e:
            LOGGER.warning(f"IMDb TV fetch failed [{imdb_id}] -> {e}")
            imdb_tv = imdb_ep = None
            use_tmdb = True

    # Guard against Cinemeta returning a wrong hit (skipped for user-supplied ids).
    if imdb_tv and not use_tmdb and not explicit_imdb_id:
        sim = _title_similarity(title, imdb_tv.get("title", ""))
        if sim < _CINEMETA_THRESHOLD:
            LOGGER.info(f"IMDb TV title mismatch for '{title}': got '{imdb_tv.get('title', '')}' (sim={sim:.2f}) -> TMDb")
            imdb_tv = None
            use_tmdb = True

    # Cross-reference: if Cinemeta didn't provide moviedb_id, try to get real TMDb ID
    # so the payload has a valid tmdb_id and the DB dedup by tmdb_id works.
    if imdb_tv and not use_tmdb and not imdb_tv.get("moviedb_id") and not explicit_imdb_id:
        try:
            tmdb_result = await safe_tmdb_search(title, "tv", year)
            if tmdb_result and getattr(tmdb_result, "id", None):
                imdb_tv["moviedb_id"] = tmdb_result.id
                LOGGER.info(
                    f"Cross-referenced TMDb id={tmdb_result.id} for '{title}' "
                    f"(imdb_id={imdb_id}) from Cinemeta data"
                )
        except Exception:
            pass

    if use_tmdb or not imdb_tv:
        LOGGER.info(f"No valid Cinemeta TV data for '{title}' S{season:02d}E{episode:02d} -> using TMDb")
        if not tmdb_id:
            tmdb_search = await safe_tmdb_search(title, "tv", year) or (await safe_tmdb_search(title, "tv", None) if year else None)
            if not tmdb_search:
                LOGGER.info(f"No TMDb TV result for '{title}' S{season:02d}E{episode:02d} (year={year})")
                return None
            tmdb_id = tmdb_search.id

        tv = await _tmdb_details("tv", tmdb_id)
        if not tv:
            LOGGER.info(f"TMDb TV details failed for id={tmdb_id} ('{title}')")
            return None
        ep = await _tmdb_episode_details(tmdb_id, season, episode)
        return _build_tmdb_tv_payload(tv, ep, season, episode, quality, encoded_string)

    return _build_imdb_tv_payload(imdb_tv, imdb_ep or {}, imdb_id, title, season, episode, quality, encoded_string)


# ----------------- Movie metadata -----------------

# Resolve movie metadata, preferring Cinemeta and falling back to TMDb.
async def fetch_movie_metadata(title, encoded_string, year=None, quality=None, default_id=None) -> dict | None:
    imdb_id, tmdb_id, explicit_imdb_id, use_tmdb = _split_default_id(default_id)
    imdb_details = None

    if not imdb_id and not tmdb_id:
        imdb_id = await safe_imdb_search(title, "movie", year)
        use_tmdb = not bool(imdb_id)

    if imdb_id and not use_tmdb:
        try:
            imdb_details = await _cached_imdb_detail(imdb_id, "movie")
        except Exception as e:
            LOGGER.warning(f"IMDb movie fetch failed [{title}] -> {e}")
            imdb_details = None
            use_tmdb = True

    # Guard against Cinemeta returning a wrong hit (skipped for user-supplied ids).
    if imdb_details and not use_tmdb and not explicit_imdb_id:
        sim = _title_similarity(title, imdb_details.get("title", ""))
        if sim < _CINEMETA_THRESHOLD:
            LOGGER.info(f"IMDb movie title mismatch for '{title}': got '{imdb_details.get('title', '')}' (sim={sim:.2f}) -> TMDb")
            imdb_details = None
            use_tmdb = True

    # Cross-reference TMDb ID when Cinemeta doesn't provide moviedb_id
    if imdb_details and not use_tmdb and not imdb_details.get("moviedb_id") and not explicit_imdb_id:
        try:
            tmdb_result = await safe_tmdb_search(title, "movie", year)
            if tmdb_result and getattr(tmdb_result, "id", None):
                imdb_details["moviedb_id"] = tmdb_result.id
                LOGGER.info(
                    f"Cross-referenced TMDb id={tmdb_result.id} for movie '{title}' "
                    f"(imdb_id={imdb_id}) from Cinemeta data"
                )
        except Exception:
            pass

    if use_tmdb or not imdb_details:
        LOGGER.info(f"No valid Cinemeta movie data for '{title}' (year={year}) -> using TMDb")
        if not tmdb_id:
            tmdb_result = await safe_tmdb_search(title, "movie", year) or (await safe_tmdb_search(title, "movie", None) if year else None)
            if not tmdb_result:
                LOGGER.info(f"No TMDb movie found for '{title}' (year={year})")
                return None
            tmdb_id = tmdb_result.id

        movie = await _tmdb_details("movie", tmdb_id)
        if not movie:
            LOGGER.info(f"TMDb movie details failed for id={tmdb_id} ('{title}')")
            return None
        return _build_tmdb_movie_payload(movie, quality, encoded_string)

    return _build_imdb_movie_payload(imdb_details, imdb_id, title, quality, encoded_string)


# ----------------- Candidate search (used by the /set command UI) -----------------

# Build a single candidate dict for the picker UI.
def _candidate_entry(source, title, year, imdb_id, tmdb_id, poster, backdrop, subtitle) -> dict:
    return {
        "source": source,
        "title": title or "",
        "year": year or "",
        "imdb_id": imdb_id,
        "tmdb_id": tmdb_id,
        "poster": poster,
        "backdrop": backdrop,
        "subtitle": subtitle,
    }


# Search IMDb + TMDb for picker candidates of the given media type.
async def _search_candidates(query: str, media_type: str, year: int | None = None, limit: int = 8) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []

    imdb_type = "movie" if media_type == "movie" else "tvSeries"
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()

    try:
        imdb_hit = await search_title(query=query, type=imdb_type)
        if imdb_hit and imdb_hit.get("id"):
            seen.add(("imdb", imdb_hit["id"]))
            results.append(_candidate_entry(
                "imdb", imdb_hit.get("title", ""), imdb_hit.get("year", ""),
                imdb_hit.get("id"), imdb_hit.get("moviedb_id"),
                imdb_hit.get("poster", ""), "", "IMDb / Cinemeta",
            ))
    except Exception as e:
        LOGGER.warning(f"IMDb {media_type} candidate search failed for '{query}': {e}")

    try:
        tmdb_results = await _tmdb_raw_search(query, media_type, year if media_type == "movie" else None)
        for item in (tmdb_results or [])[:limit]:
            tmdb_id = getattr(item, "id", None)
            if not tmdb_id or ("tmdb", str(tmdb_id)) in seen:
                continue
            seen.add(("tmdb", str(tmdb_id)))
            imdb_id = await _tmdb_external_imdb_id(media_type, tmdb_id)
            r_title, r_year = _tmdb_title_year(item, media_type)
            results.append(_candidate_entry(
                "tmdb", r_title, r_year or "", imdb_id, tmdb_id,
                format_tmdb_image(getattr(item, "poster_path", None)),
                format_tmdb_image(getattr(item, "backdrop_path", None), "original"),
                "TMDb",
            ))
    except Exception as e:
        LOGGER.warning(f"TMDb {media_type} candidate search failed for '{query}': {e}")

    return results[:limit]


# Search movie candidates for the picker UI.
async def search_movie_candidates(query: str, year: int | None = None, limit: int = 8) -> list[dict]:
    return await _search_candidates(query, "movie", year, limit)


# Search TV candidates for the picker UI.
async def search_tv_candidates(query: str, limit: int = 8) -> list[dict]:
    return await _search_candidates(query, "tv", None, limit)


# ----------------- Manual /set command helpers -----------------

# Reshape an indexer payload into the manual-rescan response shape.
def _to_selection_payload(data: dict, media_type: str) -> dict:
    return {
        "tmdb_id": data.get("tmdb_id"),
        "imdb_id": data.get("imdb_id"),
        "title": data.get("title"),
        "release_year": data.get("year"),
        "rating": data.get("rate"),
        "description": data.get("description"),
        "poster": data.get("poster"),
        "backdrop": data.get("backdrop"),
        "logo": data.get("logo"),
        "genres": data.get("genres", []),
        "cast": data.get("cast", []),
        "runtime": data.get("runtime"),
        "media_type": media_type,
    }


# Fetch full movie metadata for a manually selected id.
async def fetch_selected_movie_metadata(selected_id: str) -> dict | None:
    selected_id = str(selected_id).strip()
    if not selected_id:
        return None
    data = await fetch_movie_metadata(
        title="manual-rescan", encoded_string=None, year=None, quality=None, default_id=selected_id
    )
    return _to_selection_payload(data, "movie") if data else None


# Fetch full TV metadata for a manually selected id.
async def fetch_selected_tv_metadata(selected_id: str) -> dict | None:
    selected_id = str(selected_id).strip()
    imdb_id, tmdb_id, _, use_tmdb = _split_default_id(selected_id)
    if not imdb_id and not tmdb_id:
        return None

    imdb_tv = None
    if imdb_id and not use_tmdb:
        try:
            imdb_tv = await get_detail(imdb_id=imdb_id, media_type="tvSeries")
        except Exception:
            imdb_tv = None
            use_tmdb = True

    if use_tmdb or not imdb_tv:
        if not tmdb_id and imdb_tv and imdb_tv.get("moviedb_id"):
            try:
                tmdb_id = int(imdb_tv["moviedb_id"])
            except Exception:
                tmdb_id = None
        if not tmdb_id:
            return None

        tv = await _tmdb_details("tv", tmdb_id)
        if not tv:
            return None
        first_air = getattr(tv, "first_air_date", None)
        runtime = _format_runtime(tv.episode_run_time[0] if getattr(tv, "episode_run_time", None) else None)
        return {
            "tmdb_id": tv.id,
            "imdb_id": getattr(getattr(tv, "external_ids", None), "imdb_id", None),
            "title": tv.name,
            "release_year": getattr(first_air, "year", 0) if first_air else 0,
            "rating": getattr(tv, "vote_average", 0) or 0,
            "description": tv.overview or "",
            "poster": format_tmdb_image(tv.poster_path),
            "backdrop": format_tmdb_image(tv.backdrop_path, "original"),
            "logo": get_tmdb_logo(getattr(tv, "images", None)),
            "genres": [g.name for g in (tv.genres or [])],
            "cast": _extract_cast(tv),
            "runtime": str(runtime),
            "media_type": "tv",
        }

    images = format_imdb_images(imdb_id)
    return {
        "tmdb_id": int(imdb_tv.get("moviedb_id")) if imdb_tv.get("moviedb_id") else None,
        "imdb_id": imdb_id,
        "title": imdb_tv.get("title", ""),
        "release_year": imdb_tv.get("releaseDetailed", {}).get("year", 0),
        "rating": imdb_tv.get("rating", {}).get("star", 0),
        "description": imdb_tv.get("plot", ""),
        "poster": images["poster"],
        "backdrop": images["backdrop"],
        "logo": images["logo"],
        "genres": imdb_tv.get("genre", []),
        "cast": imdb_tv.get("cast", []),
        "runtime": str(imdb_tv.get("runtime") or ""),
        "media_type": "tv",
    }
