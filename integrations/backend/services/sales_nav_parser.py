"""
Sales Navigator & LinkedIn Search URL Parser
=============================================
Rigorous Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0 (Foundational):
  Parses both standard LinkedIn People search URLs (/search/results/people/) and 
  Sales Navigator search URLs (/sales/search/people, /sales/lead/search).
  Extracts: keywords, title, company, geoUrn/location, industry, seniority, network, school.
- Layer 1 (Environmental Failure Analysis):
  Handles single and double URL-percent encoding (%2528 vs %28), unclosed brackets,
  malformed queries, missing parameters, and unsupported facet formats without exceptions.
  Normalizes connection degrees (FIRST_DEGREE -> F, SECOND_DEGREE -> S, THIRD_DEGREE -> O).
- Layer 2 (Human Paranoia):
  Detects when a user accidentally pastes an individual profile URL (/in/, /sales/lead/ACoA...),
  company page (/company/), or job search (/jobs/), returning clear, actionable feedback.
"""

import re
import urllib.parse
from typing import Dict, Any, Optional, List


def parse_sales_nav_url(url: str) -> Dict[str, Any]:
    """
    Parses a LinkedIn search or Sales Navigator URL into structured Voyager parameters.
    Returns:
    {
        "is_search_url": bool,
        "is_profile_url": bool,
        "is_sales_nav": bool,
        "search_params": Dict[str, str],  # keys: keywords, title, company, school, network, geoUrn, industry, function, companySize, seniority
        "error_message": Optional[str],
        "raw_query": str
    }
    """
    result: Dict[str, Any] = {
        "is_search_url": False,
        "is_profile_url": False,
        "is_sales_nav": False,
        "search_params": {},
        "error_message": None,
        "raw_query": ""
    }

    if not url or not isinstance(url, str):
        result["error_message"] = "URL is empty or invalid"
        return result

    raw = url.strip()
    # Strip enclosing quotes or angle brackets
    for start, end in [("<", ">"), ('"', '"'), ("'", "'"), ("`", "`")]:
        if raw.startswith(start) and raw.endswith(end):
            raw = raw[len(start):-len(end)].strip()
    
    if not raw:
        result["error_message"] = "URL is empty"
        return result

    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "https://" + raw

    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception as e:
        result["error_message"] = f"Invalid URL structure: {e}"
        return result

    netloc = parsed.netloc.lower()
    if "linkedin.com" not in netloc:
        result["error_message"] = "Not a LinkedIn URL"
        return result

    path = parsed.path.lower()

    # Layer 2: Detect individual profile URLs (Human error: pasting person instead of search)
    if "/in/" in path or "/pub/" in path or re.search(r"/sales/(lead|people)/[a-zA-Z0-9_\-]+", path):
        result["is_profile_url"] = True
        result["error_message"] = "This is an individual profile URL, not a search query. Please use Raw Profiles import."
        return result

    # Layer 2: Detect company and jobs URLs
    if "/company/" in path:
        result["error_message"] = "This is a LinkedIn company page URL. Please provide a people search URL."
        return result

    if "/jobs/" in path:
        result["error_message"] = "This is a LinkedIn job search URL. Please provide a people search URL."
        return result

    is_sales_nav = "/sales/" in path
    is_standard_search = "/search/" in path

    if not is_sales_nav and not is_standard_search:
        result["error_message"] = "URL does not point to a LinkedIn search or Sales Navigator page."
        return result

    result["is_search_url"] = True
    result["is_sales_nav"] = is_sales_nav

    # Layer 1: Robust URL decoding (handle double-encoded URLs safely)
    query_str = parsed.query
    if "%25" in query_str:
        try:
            query_str = urllib.parse.unquote(query_str)
        except Exception:
            pass

    qs = urllib.parse.parse_qs(query_str)
    result["raw_query"] = query_str

    search_params: Dict[str, str] = {}

    # 1. Flat query parameter extraction (works for standard search & flat Sales Nav)
    flat_mappings = {
        "keywords": "keywords",
        "title": "title",
        "company": "company",
        "pastCompany": "pastCompany",
        "school": "school",
        "network": "network",
        "geoUrn": "geoUrn",
        "geoIncluded": "geoUrn",
        "industry": "industry",
        "function": "function",
        "companySize": "companySize",
        "seniority": "seniority"
    }

    for qk, vk in flat_mappings.items():
        if qs.get(qk):
            val = qs[qk][0].strip()
            if val:
                search_params[vk] = val

    # 2. LinkedIn Sales Navigator DSL parsing: query=(recentSearchParam:(...),filters:List(...))
    query_param_val = qs.get("query", [""])[0]
    if query_param_val:
        # Decode the query parameter content
        decoded_query = urllib.parse.unquote_plus(query_param_val)

        # Extract keywords from query DSL: (keywords:XYZ) or (keywords:List((text:XYZ)))
        kw_match = re.search(r"keywords\s*:\s*([^,\)]+)", decoded_query, re.IGNORECASE)
        if kw_match and not search_params.get("keywords"):
            kw_val = kw_match.group(1).strip().strip("'\"")
            if kw_val and kw_val.lower() != "null":
                search_params["keywords"] = kw_val

        # Extract CURRENT_TITLE / TITLE
        title_matches = re.findall(
            r"type\s*:\s*(?:CURRENT_TITLE|TITLE)[^)]*?values\s*:\s*List\((.*?)\)\)", 
            decoded_query, 
            re.IGNORECASE | re.DOTALL
        )
        if title_matches and not search_params.get("title"):
            titles: List[str] = []
            for block in title_matches:
                texts = re.findall(r"text\s*:\s*([^,\)]+)", block, re.IGNORECASE)
                titles.extend([t.strip().strip("'\"") for t in texts if t.strip()])
            if titles:
                search_params["title"] = f"({ ' OR '.join(titles) })" if len(titles) > 1 else titles[0]

        # Extract CURRENT_COMPANY / COMPANY
        comp_matches = re.findall(
            r"type\s*:\s*(?:CURRENT_COMPANY|COMPANY)[^)]*?values\s*:\s*List\((.*?)\)\)", 
            decoded_query, 
            re.IGNORECASE | re.DOTALL
        )
        if comp_matches and not search_params.get("company"):
            comps: List[str] = []
            for block in comp_matches:
                texts = re.findall(r"text\s*:\s*([^,\)]+)", block, re.IGNORECASE)
                comps.extend([c.strip().strip("'\"") for c in texts if c.strip()])
            if comps:
                search_params["company"] = f"({ ' OR '.join(comps) })" if len(comps) > 1 else comps[0]

        # Extract REGION / GEO
        geo_matches = re.findall(
            r"type\s*:\s*(?:REGION|GEO)[^)]*?values\s*:\s*List\((.*?)\)\)", 
            decoded_query, 
            re.IGNORECASE | re.DOTALL
        )
        if geo_matches and not search_params.get("geoUrn"):
            geos: List[str] = []
            for block in geo_matches:
                # Prefer id if numeric, otherwise text
                ids = re.findall(r"id\s*:\s*(\d+)", block, re.IGNORECASE)
                if ids:
                    geos.extend(ids)
                else:
                    texts = re.findall(r"text\s*:\s*([^,\)]+)", block, re.IGNORECASE)
                    geos.extend([t.strip().strip("'\"") for t in texts if t.strip()])
            if geos:
                search_params["geoUrn"] = geos[0]

        # Extract INDUSTRY
        ind_matches = re.findall(
            r"type\s*:\s*INDUSTRY[^)]*?values\s*:\s*List\((.*?)\)\)", 
            decoded_query, 
            re.IGNORECASE | re.DOTALL
        )
        if ind_matches and not search_params.get("industry"):
            inds: List[str] = []
            for block in ind_matches:
                texts = re.findall(r"text\s*:\s*([^,\)]+)", block, re.IGNORECASE)
                inds.extend([t.strip().strip("'\"") for t in texts if t.strip()])
            if inds:
                search_params["industry"] = inds[0]

        # Extract SENIORITY_LEVEL
        sen_matches = re.findall(
            r"type\s*:\s*SENIORITY_LEVEL[^)]*?values\s*:\s*List\((.*?)\)\)", 
            decoded_query, 
            re.IGNORECASE | re.DOTALL
        )
        if sen_matches and not search_params.get("seniority"):
            sens: List[str] = []
            for block in sen_matches:
                texts = re.findall(r"text\s*:\s*([^,\)]+)", block, re.IGNORECASE)
                sens.extend([t.strip().strip("'\"") for t in texts if t.strip()])
            if sens:
                search_params["seniority"] = sens[0]

        # Extract NETWORK degree
        net_matches = re.findall(
            r"type\s*:\s*NETWORK[^)]*?values\s*:\s*List\((.*?)\)\)", 
            decoded_query, 
            re.IGNORECASE | re.DOTALL
        )
        if net_matches and not search_params.get("network"):
            nets: List[str] = []
            for block in net_matches:
                texts = re.findall(r"(?:text|id)\s*:\s*([^,\)]+)", block, re.IGNORECASE)
                for t in texts:
                    clean_t = t.strip().strip("'\"").upper()
                    if "FIRST" in clean_t or clean_t == "F":
                        nets.append("F")
                    elif "SECOND" in clean_t or clean_t == "S":
                        nets.append("S")
                    elif "THIRD" in clean_t or clean_t == "O":
                        nets.append("O")
            if nets:
                search_params["network"] = str(list(set(nets)))

    # Layer 1 Fallback: If no structured facets were found in Sales Nav URL, extract any raw text
    if not search_params and is_sales_nav and query_param_val:
        # Grab first identifiable words as keywords fallback
        raw_words = re.findall(r"\b[A-Za-z0-9\-_]{3,}\b", urllib.parse.unquote_plus(query_param_val))
        excluded = {"query", "filters", "list", "type", "values", "recentsearchparam", "id", "dofetchherocard", "true", "false", "text", "selectiontype", "included"}
        meaningful_words = [w for w in raw_words if w.lower() not in excluded]
        if meaningful_words:
            search_params["keywords"] = " ".join(meaningful_words[:5])

    result["search_params"] = search_params
    return result
