import json
import logging
import re

from repositories.trialgpt_schema_bootstrap import ensure_trialgpt_schema
from utils.pg_util import pg_corpus_transaction as pg_transaction

TABLE_NAME = "trialgpt_corpus"


def ensure_trialgpt_corpus_table() -> None:
    """Create trialgpt_corpus and every other TrialGPT-owned table if missing."""
    ensure_trialgpt_schema()


# SNOMED-style qualifiers appended to patient disease labels (e.g. "Fever (finding)",
# "Anemia (disorder)") that never appear on trial-corpus disease strings. We strip a
# trailing parenthetical qualifier so the two vocabularies can line up.
_TRAILING_QUALIFIER_RE = re.compile(r"\s*\([^)]*\)\s*$")

# Small hand-maintained synonym map: patient/UI label -> equivalent corpus terms.
# Keys and values are compared in normalized (lowercased, qualifier-stripped) form.
_DISEASE_SYNONYMS = {
    "prediabetes": ["pre-diabetes", "prediabetic state"],
    "pre diabetes": ["pre-diabetes", "prediabetic state"],
    "diabetes": ["diabetes mellitus", "diabetes mellitus, type 2", "diabetes mellitus, type 1"],
    "type 2 diabetes": ["diabetes mellitus, type 2"],
    "type 1 diabetes": ["diabetes mellitus, type 1"],
    "anemia": ["anemia"],
    "covid 19": ["covid-19"],
    "suspected covid-19": ["covid-19"],
    "suspected covid 19": ["covid-19"],
    # Patient SNOMED obesity findings map to trial "obesity" / overweight labels.
    "body mass index 30+ - obesity": ["obesity", "overweight and obesity", "overweight/obesity"],
    "obesity": ["obesity", "overweight and obesity", "overweight/obesity"],
    "sore throat symptom": ["pharyngitis"],
    "acute viral pharyngitis": ["pharyngitis"],
    "headache, unspecified": ["headache", "migraine"],
    "headache": ["headache", "migraine"],
    "migraine": ["migraine", "headache"],
    "migraine without aura": ["migraine"],
    "primary osteoarthritis": ["osteoarthritis"],
    "osteoarthritis": ["osteoarthritis", "osteoarthritis, knee", "osteoarthritis, hip"],
}


def _normalize_disease(value: str) -> str:
    """Lowercase, trim, and strip a trailing SNOMED qualifier like '(finding)'."""
    text = (value or "").strip().lower()
    text = _TRAILING_QUALIFIER_RE.sub("", text).strip()
    text = re.sub(r",\s*unspecified\s*$", "", text, flags=re.IGNORECASE).strip()
    return text


def _expand_disease_terms(diseases) -> list[str]:
    """Build the set of normalized match terms (normalized inputs + known synonyms)."""
    if isinstance(diseases, str):
        diseases = [diseases]
    terms: set[str] = set()
    for raw in diseases or []:
        norm = _normalize_disease(raw)
        if not norm:
            continue
        terms.add(norm)
        for syn in _DISEASE_SYNONYMS.get(norm, []):
            terms.add(_normalize_disease(syn))
        for token in re.split(r"[\s,/\-]+", norm):
            token = token.strip()
            if len(token) >= 4:
                terms.add(token)
    return sorted(terms)


def fetch_all_corpus_locations(*, limit: int = 300) -> list[str]:
    """Distinct trial sites (fallback when disease filter returns no rows)."""
    ensure_trialgpt_corpus_table()
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            SELECT DISTINCT loc AS location
            FROM (
                SELECT jsonb_array_elements_text(t.locations) AS loc
                FROM trialgpt_corpus t
                WHERE t.locations IS NOT NULL
                  AND jsonb_array_length(t.locations) > 0
            ) sub
            ORDER BY location
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall() or []
    return [str(row["location"]) for row in rows if row.get("location")]


def upsert_trial_corpus(data: dict):
    ensure_trialgpt_corpus_table()

    with pg_transaction(dict_cursor=False) as (conn, cursor):

        cursor.execute(
            """
            INSERT INTO trialgpt_corpus (
                nct_id,
                title,
                text,
                inclusion_criteria,
                exclusion_criteria,
                source_type,
                countries,
                locations,
                locations_detailed,
                diseases,
                drugs,
                phase,
                enrollment,
                min_age,
                max_age,
                sex,
                overall_status,
                raw_json,
                start_date,
                completion_date,
                updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            ON CONFLICT (nct_id)
            WHERE nct_id IS NOT NULL
            DO UPDATE SET
                title = EXCLUDED.title,
                text = EXCLUDED.text,
                inclusion_criteria = EXCLUDED.inclusion_criteria,
                exclusion_criteria = EXCLUDED.exclusion_criteria,
                countries = EXCLUDED.countries,
                locations = EXCLUDED.locations,
                locations_detailed = EXCLUDED.locations_detailed,
                diseases = EXCLUDED.diseases,
                drugs = EXCLUDED.drugs,
                phase = EXCLUDED.phase,
                enrollment = EXCLUDED.enrollment,
                min_age = EXCLUDED.min_age,
                max_age = EXCLUDED.max_age,
                sex = EXCLUDED.sex,
                overall_status = EXCLUDED.overall_status,
                raw_json = EXCLUDED.raw_json,
                start_date = EXCLUDED.start_date,
                completion_date = EXCLUDED.completion_date,
                updated_at = now();
            """,
            (
                data.get("nct_id"),
                data.get("title"),
                data.get("text"),
                json.dumps(data.get("inclusion_criteria")),
                json.dumps(data.get("exclusion_criteria")),
                data.get("source_type"),
                json.dumps(data.get("countries", [])),
                json.dumps(data.get("locations", [])),
                json.dumps(data.get("locations_detailed", [])),
                json.dumps(data.get("diseases", [])),
                json.dumps(data.get("drugs", [])),
                data.get("phase"),
                json.dumps(data.get("enrollment", {})), 
                data.get("min_age"),
                data.get("max_age"),
                data.get("sex"),
                data.get("overall_status"),
                json.dumps(data.get("raw_json", {})),
                data.get("start_date"),        
                data.get("completion_date"),   
            ),
        )

    logger = logging.getLogger("trial_ingestion")
    logger.info(f"Trial stored in DB: {data.get('nct_id')}")

    return {"status": "success", "nct_id": data.get("nct_id")}



def get_all_regions():
    ensure_trialgpt_corpus_table()
    with pg_transaction() as (_, cur):
        cur.execute("""
            SELECT DISTINCT jsonb_array_elements_text(countries) AS country
            FROM trialgpt_corpus
            WHERE countries IS NOT NULL
            ORDER BY country
        """)
        rows = cur.fetchall()

        return [row["country"] for row in rows if row["country"]]
    

    

def fetch_trial_by_id(nct_id):
    with pg_transaction() as (_, cur):
        cur.execute("""
            SELECT nct_id, title, text, diseases, drugs, inclusion_criteria, exclusion_criteria
            FROM trialgpt_corpus
            WHERE nct_id = %s
            LIMIT 1
        """, (nct_id,))
        return cur.fetchone()
    


def fetch_trials_by_ids(nct_ids: list):
    if not nct_ids:
        return []

    with pg_transaction() as (_, cur):
        cur.execute(
            """
            SELECT *
            FROM trialgpt_corpus
            WHERE nct_id = ANY(%s)
            """,
            (nct_ids,)
        )

        # If using DictCursor, rows are already dicts
        rows = cur.fetchall()
        return rows    


def fetch_all_trials():
    ensure_trialgpt_corpus_table()
    with pg_transaction() as (_, cur):
        cur.execute("""
            SELECT
                nct_id,
                title,
                text,
                diseases,
                drugs,
                inclusion_criteria,
                exclusion_criteria
            FROM trialgpt_corpus
        """)
        return cur.fetchall()
    


def fetch_trials_by_country(country):
    with pg_transaction() as (_, cur):
        cur.execute("""
            SELECT
                nct_id,
                title,
                text,
                diseases,
                drugs,
                inclusion_criteria,
                exclusion_criteria
            FROM trialgpt_corpus
            WHERE countries @> %s::jsonb
        """, (json.dumps([country]),))
        return cur.fetchall()
    


def fetch_locations_by_disease(selected_disease):
    """Single-disease wrapper; uses the same normalized matching as the plural form."""
    return fetch_locations_by_diseases(selected_disease)



def fetch_locations_by_diseases(diseases):
    """Return distinct trial locations for the given disease(s).

    Patient disease labels (SNOMED-style, e.g. "Fever (finding)", "Anemia (disorder)")
    and trial-corpus disease strings use different vocabularies, so a strict full-string
    equality misses almost everything (only exact overlaps like "COVID-19" matched).

    We instead:
      * strip trailing SNOMED qualifiers on BOTH sides,
      * expand a small synonym map (e.g. prediabetes -> pre-diabetes),
      * match on normalized equality OR substring containment (the normalized input
        term appearing inside the trial disease, e.g. "fever" in "dengue fever",
        "anemia" in "anemia, sickle cell"). Substring is gated to terms >= 4 chars to
        avoid spurious matches on tiny fragments.
    """
    if not diseases:
        return []

    terms = _expand_disease_terms(diseases)
    if not terms:
        return []

    substring_terms = [t for t in terms if len(t) >= 4]
    if not substring_terms:
        substring_terms = ["__no_substr_match__"]
    ensure_trialgpt_corpus_table()

    with pg_transaction() as (_, cur):
        cur.execute(
            r"""
            WITH input(term) AS (
                SELECT DISTINCT unnest(%(terms)s::text[])
            ),
            substr_input(term) AS (
                SELECT DISTINCT unnest(%(substr_terms)s::text[])
            )
            SELECT DISTINCT jsonb_array_elements_text(t.locations) AS location
            FROM trialgpt_corpus t
            WHERE t.locations IS NOT NULL
              AND jsonb_array_length(t.locations) > 0
              AND EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(t.diseases) d
                CROSS JOIN LATERAL (
                    SELECT btrim(regexp_replace(lower(d), '\s*\([^)]*\)\s*$', '')) AS nd
                ) nrm
                WHERE nrm.nd = ANY(%(terms)s)
                   OR EXISTS (
                        SELECT 1 FROM substr_input s
                        WHERE nrm.nd LIKE '%%' || s.term || '%%'
                   )
              )
            ORDER BY location
            """,
            {"terms": terms, "substr_terms": substring_terms},
        )

        rows = cur.fetchall()
        return [row["location"] for row in rows if row["location"]]
    


# def fetch_trials_by_location(location):
#     with pg_transaction() as (_, cur):
#         cur.execute("""
#             SELECT
#                 nct_id,
#                 title,
#                 text,
#                 diseases,
#                 drugs,
#                 inclusion_criteria,
#                 exclusion_criteria
#             FROM trialgpt_corpus
#             WHERE locations @> %s::jsonb
#         """, (json.dumps([location]),))
#         return cur.fetchall()


def fetch_trials_by_location(locations):
    """Load trials matching region filters (country codes expand to corpus phrases)."""

    loc_terms = _expand_location_match_terms(locations)
    if not loc_terms:
        return []

    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT
                nct_id,
                title,
                text,
                diseases,
                drugs,
                inclusion_criteria,
                exclusion_criteria
            FROM trialgpt_corpus t
            WHERE {_location_match_sql("t.locations")}
            """,
            {"loc_terms": loc_terms},
        )

        return cur.fetchall()
    

def fetch_trials_by_location_and_diseases(locations, diseases):

    loc_terms = _expand_location_match_terms(locations)
    if not loc_terms:
        return []

    terms = _expand_disease_terms(diseases)
    if not terms:
        return []

    substring_terms = [t for t in terms if len(t) >= 4]

    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            WITH substr_input(term) AS (
                SELECT DISTINCT unnest(%(substr_terms)s::text[])
            )
            SELECT
                nct_id,
                title,
                text,
                diseases,
                drugs,
                inclusion_criteria,
                exclusion_criteria
            FROM trialgpt_corpus t
            WHERE {_location_match_sql("t.locations")}
              AND EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(t.diseases) d
                CROSS JOIN LATERAL (
                    SELECT btrim(regexp_replace(lower(d), '\\s*\\([^)]*\\)\\s*$', '')) AS nd
                ) nrm
                WHERE nrm.nd = ANY(%(terms)s)
                   OR EXISTS (
                        SELECT 1 FROM substr_input s
                        WHERE nrm.nd LIKE '%%' || s.term || '%%'
                   )
              )
            """,
            {
                "loc_terms": loc_terms,
                "terms": terms,
                "substr_terms": substring_terms,
            },
        )

        return cur.fetchall()


# UI/API region codes -> corpus location needles (substring match, case-insensitive).
# Corpus stores city strings like "Miami, Florida, United States", not "US".
_LOCATION_ALIASES = {
    "us": ["united states", "usa", "u.s.", "u.s.a."],
    "usa": ["united states", "usa", "u.s.", "u.s.a."],
    "united states": ["united states", "usa", "u.s.", "u.s.a."],
    "uk": ["united kingdom", "england", "scotland", "wales", "great britain"],
    "united kingdom": ["united kingdom", "england", "scotland", "wales", "great britain"],
    "gb": ["united kingdom", "england", "scotland", "wales", "great britain"],
}


def _normalize_location_list(locations):
    if not locations:
        return []
    if isinstance(locations, str):
        locations = [locations]
    if not isinstance(locations, list):
        raise ValueError("locations must be string or list")
    return [str(loc).strip() for loc in locations if loc and str(loc).strip()]


def _expand_location_match_terms(locations) -> list[str]:
    """
    Expand region filters into lowercase needles for corpus location matching.

    Short country codes (e.g. US) expand to full-country phrases so they match
    city strings like "Miami, Florida, United States". Original tokens are kept
    for exact/city matches.
    """
    terms: set[str] = set()
    for raw in _normalize_location_list(locations):
        token = raw.strip()
        if not token:
            continue
        lower = token.lower()
        terms.add(lower)
        for alias in _LOCATION_ALIASES.get(lower, []):
            alias_l = alias.lower().strip()
            if alias_l:
                terms.add(alias_l)
    return sorted(terms)


def _location_match_sql(column: str = "t.locations") -> str:
    """SQL predicate: location filter null/empty OR any element matches a needle."""
    return f"""
        (
            %(loc_terms)s::text[] IS NULL
            OR cardinality(%(loc_terms)s::text[]) = 0
            OR EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text({column}) loc
                WHERE EXISTS (
                    SELECT 1
                    FROM unnest(%(loc_terms)s::text[]) term
                    WHERE lower(loc) = term
                       OR lower(loc) LIKE '%%' || term || '%%'
                )
            )
        )
    """


def filter_nct_ids_by_location_and_diseases(
    nct_ids: list,
    locations=None,
    diseases=None,
) -> list[str]:
    """Preserve NCT order while keeping only IDs that match region and/or disease filters.

    Disease matching uses SNOMED-strip + synonym + substring logic.
    Location matching expands country codes (US → United States) and substring-matches
    corpus location city strings.
    """
    ordered = [str(n).strip() for n in (nct_ids or []) if n and str(n).strip()]
    if not ordered:
        return []

    loc_terms = _expand_location_match_terms(locations)
    has_disease_filter = bool(diseases)
    terms = _expand_disease_terms(diseases) if has_disease_filter else []
    if has_disease_filter and not terms:
        return []
    if not loc_terms and not terms:
        return ordered

    substring_terms = [t for t in terms if len(t) >= 4]
    params = {
        "nct_ids": ordered,
        "loc_terms": loc_terms or None,
        "terms": terms or None,
        "substr_terms": substring_terms or [],
    }

    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            WITH substr_input(term) AS (
                SELECT DISTINCT unnest(COALESCE(%(substr_terms)s::text[], ARRAY[]::text[]))
            )
            SELECT t.nct_id
            FROM trialgpt_corpus t
            WHERE t.nct_id = ANY(%(nct_ids)s)
              AND {_location_match_sql("t.locations")}
              AND (
                    %(terms)s::text[] IS NULL
                    OR EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements_text(t.diseases) d
                        CROSS JOIN LATERAL (
                            SELECT btrim(
                                regexp_replace(lower(d), '\\s*\\([^)]*\\)\\s*$', '')
                            ) AS nd
                        ) nrm
                        WHERE nrm.nd = ANY(%(terms)s)
                           OR EXISTS (
                                SELECT 1 FROM substr_input s
                                WHERE nrm.nd LIKE '%%' || s.term || '%%'
                           )
                    )
              )
            """,
            params,
        )
        matched = {row["nct_id"] for row in (cur.fetchall() or [])}

    return [nct for nct in ordered if nct in matched]


def fetch_nct_ids_by_location_and_diseases(
    locations=None,
    diseases=None,
    limit: int = 50,
) -> list[str]:
    """Return NCT IDs matching optional region and/or disease filters (for RAG backfill)."""
    loc_terms = _expand_location_match_terms(locations)
    terms = _expand_disease_terms(diseases) if diseases else []
    if not loc_terms and not terms:
        return []

    substring_terms = [t for t in terms if len(t) >= 4]
    limit = max(1, int(limit or 50))

    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            WITH substr_input(term) AS (
                SELECT DISTINCT unnest(COALESCE(%(substr_terms)s::text[], ARRAY[]::text[]))
            )
            SELECT t.nct_id
            FROM trialgpt_corpus t
            WHERE {_location_match_sql("t.locations")}
              AND (
                    %(terms)s::text[] IS NULL
                    OR EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements_text(t.diseases) d
                        CROSS JOIN LATERAL (
                            SELECT btrim(
                                regexp_replace(lower(d), '\\s*\\([^)]*\\)\\s*$', '')
                            ) AS nd
                        ) nrm
                        WHERE nrm.nd = ANY(%(terms)s)
                           OR EXISTS (
                                SELECT 1 FROM substr_input s
                                WHERE nrm.nd LIKE '%%' || s.term || '%%'
                           )
                    )
              )
            ORDER BY t.nct_id
            LIMIT %(limit)s
            """,
            {
                "loc_terms": loc_terms or None,
                "terms": terms or None,
                "substr_terms": substring_terms or [],
                "limit": limit,
            },
        )
        return [row["nct_id"] for row in (cur.fetchall() or []) if row.get("nct_id")]





def fetch_locations_by_nct_ids(nct_ids: list):

    if not nct_ids:
        return {}

    with pg_transaction() as (conn, cursor):

        cursor.execute(
            """
            SELECT 
                nct_id,
                title,
                locations,
                locations_detailed,
                phase,
                enrollment,
                overall_status,
                start_date,
                completion_date
            FROM trialgpt_corpus
            WHERE nct_id = ANY(%s)
            """,
            (nct_ids,)
        )

        rows = cursor.fetchall()

    location_map = {}

    for row in rows:
        location_map[row["nct_id"]] = {
            "locations": row.get("locations") or [],
            "locations_detailed": row.get("locations_detailed") or [],
            "title": row.get("title"),
            "phase": row.get("phase"),
            "enrollment": row.get("enrollment"),
            "overall_status": row.get("overall_status"),
            "start_date": row.get("start_date"),
            "completion_date": row.get("completion_date"),
        }

    return location_map



def fetch_location_details_by_regions(regions):
    if not regions:
        return []

    if isinstance(regions, str):
        regions = [regions]

    with pg_transaction() as (_, cur):
        cur.execute("""
            SELECT locations_detailed
            FROM trialgpt_corpus
            WHERE locations ?| %s
        """, (regions,))

        rows = cur.fetchall()

    results = []

    for row in rows:
        detailed_list = row.get("locations_detailed") or []

        for d in detailed_list:
            key = ", ".join(filter(None, [
                d.get("city"),
                d.get("state"),
                d.get("country")
            ]))

            if key in regions:
                results.append(d)

    return results