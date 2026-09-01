import re
from .brightdata import fetch_jobs
from claude import summarize_jobs

JUNIOR_TITLE_RE = re.compile(
    r"\b(intern|internship|trainee|graduate\b|entry.level|off.cycle|campus (hire|recruitment)|"
    r"working student|apprentice|junior)\b", re.I
)

FINANCE_INDUSTRY_RE = re.compile(
    r"\bfinancial services\b|\bbanking\b|\binvestment management\b|\binvestment banking\b|"
    r"\bcapital markets\b|\bfunds and trusts\b", re.I
)

PE_VC_RE = re.compile(
    r"\bprivate equity\b|\bventure capital\b|\bv\.?c\.? fund\b|\bbuyout\b|\bgrowth equity\b",
    re.I
)

REAL_ESTATE_RE = re.compile(
    r"\breal estate\b|\breit\b|\bproperty (management|fund)\b|\breal asset\b", re.I
)

FAMILY_OFFICE_RE = re.compile(r"\bfamily office\b", re.I)
PUBLIC_MARKET_RE = re.compile(
    r"\bequit(y|ies)\b|\bhedge fund\b|\bpublic market\b|\bportfolio manage(r|ment)\b|"
    r"\basset management\b|\bwealth management\b|\bglobal markets\b|\bfixed income\b|"
    r"\bmutual fund\b|\bresearch analyst\b|\btrader\b|\bmacro\b", re.I
)

# years-of-experience: only exclude if a number is explicitly stated and it's below 8
YEARS_RE = re.compile(r"(\d{1,2})\+?\s*(?:to|-|–)\s*(\d{1,2})\+?\s*years?|\b(\d{1,2})\+?\s*years?", re.I)

BANK_NAME_RE = re.compile(
    r"\bHSBC\b|\bUOB\b|\bOCBC\b|\bDBS\b|\bCitibank\b|\bCiti\b|\bJPMorgan\b|\bJ\.?P\.? ?Morgan\b|"
    r"\bBNP Paribas\b|\bStandard Chartered\b|\bCIMB\b|\bRHB\b|\bIndosuez\b|\bJulius Baer\b|"
    r"\bPictet\b|\bCredit Suisse\b|\bUBS\b|\bDeutsche Bank\b|\bBarclays\b|\bGoldman Sachs\b|"
    r"\bMorgan Stanley\b|\bBank of America\b|\bMaybank\b|\bANZ\b|\bICBC\b|\bBank of China\b|"
    r"\bEFG\b|\bBordier\b|\bLombard Odier\b|\bCoutts\b|\bRBC\b|\bSociete Generale\b|\bMizuho\b|"
    r"\bMUFG\b|\bSumitomo Mitsui\b|\bNomura\b|\bDaiwa\b", re.I
)
BANK_INDUSTRY_RE = re.compile(r"bank", re.I)
BANK_TITLE_RE = re.compile(r"\bprivate bank\w*\b|\bbanker\b|\bbank\b", re.I)

POD_SHOP_RE = re.compile(
    r"\bMillennium\b|\bCitadel\b|\bPoint ?72\b|\bExodusPoint\b|\bBalyasny\b|\bSchonfeld\b|"
    r"\bVerition\b|\bSquarepoint\b|\bQube\b|\bMarshall Wace\b|\bBrevan Howard\b|\bGraham Capital\b|"
    r"\bCapstone\b|\bEisler\b|\bWorldQuant\b|\bDRW\b|\bTrexquant\b|\bDiameter Capital\b|"
    r"\bHudson Bay Capital\b|\bRokos\b|\bElement Capital\b|\bWalleye\b|\bFreeport\b|\bD1 Capital\b|"
    r"\bWoodline\b|\bBlue Pool\b|\bCinctive\b|\bKirkoswald\b",
    re.I
)

LANGUAGE_RE = re.compile(
    r"\bMandarin\b|\bCantonese\b|\bChinese\b|\bJapanese\b|\bKorean\b|\bFrench\b|\bGerman\b|"
    r"\bSpanish\b|\bThai\b|\bVietnamese\b|\bBahasa\b|\bMalay\b|\bIndonesian\b|\bTagalog\b|"
    r"\bHindi\b|\bArabic\b|\bItalian\b|\bPortuguese\b|\bDutch\b|\bRussian\b|\bTamil\b|"
    r"\bBurmese\b|\bKhmer\b|\bLao\b",
    re.I
)

DESCRIPTION_INNER_RE = re.compile(r'relative overflow-hidden">\s*(.*?)\s*<button', re.S)


def _extract_description(job):
    formatted = job.get("job_description_formatted") or ""
    m = DESCRIPTION_INNER_RE.search(formatted)
    if m:
        return m.group(1).strip()
    return (job.get("job_summary") or "").strip().replace("\n", "<br>")


def run_job_search(record_limit=100):
    """
    Fetches raw LinkedIn job listings from Bright Data and applies the full
    filter stack: dedupe, junior titles, PE/VC, real estate, non-finance
    industries, <8yrs-stated experience, banks/private banks, pod shops,
    non-English language requirements. Returns a list of kept job dicts
    (each with a relevance "score" and extracted "description_html"),
    sorted highest score first.
    """
    raw = fetch_jobs(record_limit=record_limit)

    seen_ids = set()
    kept = []

    for d in raw:
        if "error" in d or not d.get("job_title"):
            continue

        jid = d.get("job_posting_id")
        if jid in seen_ids:
            continue
        seen_ids.add(jid)

        title = d.get("job_title", "")
        company = d.get("company_name", "") or ""
        summary = d.get("job_summary", "") or ""
        industries = d.get("job_industries", "") or ""
        haystack = f"{title} {industries}"
        full_text = f"{title} {summary} {industries}"

        if JUNIOR_TITLE_RE.search(title):
            continue
        if PE_VC_RE.search(haystack):
            continue
        if REAL_ESTATE_RE.search(haystack):
            continue
        if not FINANCE_INDUSTRY_RE.search(industries):
            continue

        year_nums = []
        for m in YEARS_RE.finditer(summary):
            for g in m.groups():
                if g:
                    year_nums.append(int(g))
        if year_nums and max(year_nums) < 8:
            continue

        if (BANK_NAME_RE.search(company) or BANK_INDUSTRY_RE.search(industries)
                or BANK_TITLE_RE.search(title) or BANK_INDUSTRY_RE.search(company)):
            continue

        if POD_SHOP_RE.search(company):
            continue

        if LANGUAGE_RE.search(summary):
            continue

        score = 0
        if FAMILY_OFFICE_RE.search(full_text):
            score += 2
        if PUBLIC_MARKET_RE.search(full_text):
            score += 1

        kept.append({
            "score": score,
            "job_title": title,
            "company_name": company,
            "job_location": d.get("job_location", ""),
            "url": d.get("url", "#"),
            "job_posted_date": d.get("job_posted_date", ""),
            "job_summary": summary,
            "description_html": _extract_description(d),
        })

    kept.sort(key=lambda x: x["score"], reverse=True)

    one_liners = summarize_jobs(kept)
    for job, one_liner in zip(kept, one_liners):
        job["one_liner"] = one_liner

    return kept
