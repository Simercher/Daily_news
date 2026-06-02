from __future__ import annotations
import hashlib, re, unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from dateutil import parser
TRACKING_PREFIXES = ("utm_",)
TRACKING_PARAMS = {"fbclid","gclid","mc_cid","mc_eid","igshid","ref","ref_src"}
SOURCE_SUFFIX_RE = re.compile(r"\s*[-|—–]\s*([\w\s.]+)$")

def canonicalize_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    scheme = (parts.scheme or "https").lower(); netloc = parts.netloc.lower()
    if netloc.startswith("www."): netloc = netloc[4:]
    query = [(k,v) for k,v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith(TRACKING_PREFIXES) and k.lower() not in TRACKING_PARAMS]
    path = re.sub(r"/+$", "", parts.path or "/")
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))

def url_hash(url: str) -> str:
    return hashlib.sha256(canonicalize_url(url).encode()).hexdigest()

def normalize_title(title: str) -> str:
    s = unicodedata.normalize("NFKC", title or "").lower()
    s = SOURCE_SUFFIX_RE.sub("", s)
    s = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def to_utc(value) -> datetime:
    if isinstance(value, datetime): dt = value
    else: dt = parser.parse(str(value))
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
