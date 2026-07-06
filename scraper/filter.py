"""Development-item filter and multifamily classifier."""
import re

# Checked in order; first match wins.
_TYPE_PATTERNS = [
    ("rezoning", r"\brezon\w*|\bzoning (change|amendment|district change)|\bchange of zoning"),
    ("pud", r"\bplanned unit development\b|\bPUD\b|\bplanned development\b"),
    ("land-use", r"\bland use (map )?amendment|\bFLUM\b|\bfuture land use|\bcomprehensive plan amendment|\bcomp plan amendment"),
    ("site-plan", r"\bsite plan\b|\bMUSP\b|\bmajor use special permit|\bspecial area plan\b"),
    ("plat", r"\b(re)?plat\b"),
    ("special-exception", r"\bspecial exception\b|\bconditional use\b|\bspecial use permit\b"),
    ("variance", r"\bvariance\b"),
    ("development-agreement", r"\bdevelopment (agreement|order)\b"),
    ("annexation", r"\bannexation\b|\bannex\w*\b"),
    ("other-development", r"\bdensity (increase|bonus)\b|\bnew construction\b|\bmixed[- ]use (project|development)\b|"
                          r"\blive local\b|\b(affordable|workforce) housing\b|\bhousing development\b"),
]
_TYPE_RES = [(t, re.compile(p, re.I)) for t, p in _TYPE_PATTERNS]

_MF_RE = re.compile(
    r"\bmulti[- ]?family\b|\bapartment\w*\b|\bresidential unit|\bdwelling unit|\bdu/ac\b|"
    r"\btownho(me|use)\w*\b|\bcondominium\w*\b|\bcondo\b|\bmixed[- ]use\b|"
    r"\baffordable housing\b|\bworkforce housing\b|\blive local\b|\bsenior (living|housing)\b|"
    r"\btransit[- ]oriented\b|\bTOD\b|\bhigh[- ]density residential\b|\b\d+[- ]unit\b|\bunits\b.*\bresidential\b|"
    r"\brental (units|community|housing)\b",
    re.I,
)

# Boilerplate that disqualifies an item even if a dev keyword appears incidentally.
_EXCLUDE_RE = re.compile(
    r"^(approval of )?minutes\b|\bproclamation\b|\bcommendation\b|"
    r"^appointment\b|\bappointment of members?\b|\breappointment\b|"
    r"^presentation\b|\binvocation\b|\bpledge of allegiance\b",
    re.I,
)


def classify(title: str, body: str = "") -> dict | None:
    """Return {"project_type", "multifamily"} for development items, else None."""
    text = f"{title} {body}".strip()
    if not text:
        return None
    if _EXCLUDE_RE.search(title.strip()):
        return None
    for ptype, rx in _TYPE_RES:
        if rx.search(text):
            return {"project_type": ptype, "multifamily": bool(_MF_RE.search(text))}
    return None
