import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

URL_REGEX = re.compile(
    r'(?:https?:\/\/)?'                     # scheme
    r'(?:(?:[a-zA-Z0-9_-]+\.)+[a-zA-Z]{2,})' # host
    r'(?::\d+)?'                             # port
    r'(?:\/[^\s<>"\'\(\)]*)?',               # path
    re.IGNORECASE
)

EMAIL_CLEANUP_REGEX = re.compile(
    r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}',
    re.IGNORECASE
)

IGNORED_DOMAINS = {
    "youtube.com", "youtu.be", "googlevideo.com", "google.com", "ytimg.com",
    "ggpht.com", "gstatic.com", "schema.org", "w3.org", "bit.ly", "cutt.ly", "tinyurl.com"
}

LINK_AGGREGATORS = {
    "linktr.ee": "linktree",
    "beacons.ai": "beacons",
    "stan.store": "stan",
    "taplink.cc": "taplink",
    "lnk.bio": "lnk.bio",
    "campsite.bio": "campsite",
    "linkbio.co": "linkbio",
    "bio.site": "bio.site",
    "allmylinks.com": "allmylinks"
}

SALES_PLATFORMS = {
    "hotmart.com": "hotmart",
    "kiwify.com.br": "kiwify",
    "kiwify.app": "kiwify",
    "eduzz.com": "eduzz",
    "monetizze.com.br": "monetizze",
    "braip.com": "braip",
    "ticto.com.br": "ticto",
    "udemy.com": "udemy",
    "cakto.com.br": "cakto",
    "herospark.com": "herospark"
}

class LinkExtractor:

    @staticmethod
    def normalize_url(raw_url: str) -> str:
        """Sanitizes URL, ensures https:// prefix, and cleans tracking parameters."""
        raw_url = raw_url.strip().rstrip(".,;:!?)")
        if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
            raw_url = "https://" + raw_url

        try:
            parsed = urlparse(raw_url)
            # Remove tracking params (utm_*, ref, etc.)
            query_params = parse_qs(parsed.query, keep_blank_values=False)
            filtered_params = {
                k: v for k, v in query_params.items()
                if not k.startswith("utm_") and not k.startswith("ref") and k not in {"fbclid", "gclid", "igshid", "ref", "source"}
            }
            new_query = urlencode(filtered_params, doseq=True)
            normalized = urlunparse((
                parsed.scheme,
                parsed.netloc.lower(),
                parsed.path.rstrip("/"),
                parsed.params,
                new_query,
                ""
            ))
            return normalized
        except Exception:
            return raw_url

    @staticmethod
    def extract_links_from_texts(texts_with_sources: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Parses multiple texts and categorizes all found URLs.
        texts_with_sources is a list of dicts: [{"text": "...", "source": "channel_description"}, ...]
        """
        all_links: Dict[str, Dict[str, Any]] = {}
        social_links = {
            "instagram": None,
            "tiktok": None,
            "twitter": None,
            "facebook": None,
            "linkedin": None,
            "whatsapp_link": None
        }
        website = None
        link_aggregators: List[Dict[str, Any]] = []
        sales_platforms: List[Dict[str, Any]] = []
        other_links: List[Dict[str, Any]] = []

        seen_normalized_urls = set()

        for item in texts_with_sources:
            raw_text = item.get("text") or ""
            source = item.get("source") or "unknown"

            # Remove email addresses before extracting URLs so that domains in emails are not extracted as URLs
            text = EMAIL_CLEANUP_REGEX.sub(" ", raw_text)

            matches = URL_REGEX.findall(text)
            for match in matches:
                # Basic validation
                if len(match) < 4 or "." not in match:
                    continue
                
                normalized = LinkExtractor.normalize_url(match)
                if normalized in seen_normalized_urls:
                    continue
                seen_normalized_urls.add(normalized)

                try:
                    parsed = urlparse(normalized)
                    domain = parsed.netloc.lower().replace("www.", "")
                except Exception:
                    continue

                if any(ign in domain for ign in IGNORED_DOMAINS):
                    continue

                # Classify URL
                # 1. WhatsApp
                if "wa.me" in domain or "api.whatsapp.com" in domain or "chat.whatsapp.com" in domain:
                    if not social_links["whatsapp_link"]:
                        social_links["whatsapp_link"] = {"url": normalized, "source": source}
                    continue

                # 2. Instagram
                if "instagram.com" in domain:
                    if not social_links["instagram"]:
                        social_links["instagram"] = {"url": normalized, "source": source}
                    continue

                # 3. TikTok
                if "tiktok.com" in domain:
                    if not social_links["tiktok"]:
                        social_links["tiktok"] = {"url": normalized, "source": source}
                    continue

                # 4. Twitter / X
                if "twitter.com" in domain or "x.com" in domain:
                    if not social_links["twitter"]:
                        social_links["twitter"] = {"url": normalized, "source": source}
                    continue

                # 5. Facebook
                if "facebook.com" in domain or "fb.com" in domain:
                    if not social_links["facebook"]:
                        social_links["facebook"] = {"url": normalized, "source": source}
                    continue

                # 6. LinkedIn
                if "linkedin.com" in domain:
                    if not social_links["linkedin"]:
                        social_links["linkedin"] = {"url": normalized, "source": source}
                    continue

                # 7. Link Aggregators
                is_aggregator = False
                for agg_domain, name in LINK_AGGREGATORS.items():
                    if agg_domain in domain:
                        link_aggregators.append({"platform": name, "url": normalized, "source": source})
                        is_aggregator = True
                        break
                if is_aggregator:
                    continue

                # 8. Sales Platforms
                is_sales = False
                for sales_domain, name in SALES_PLATFORMS.items():
                    if sales_domain in domain:
                        sales_platforms.append({"platform": name, "url": normalized, "source": source})
                        is_sales = True
                        break
                if is_sales:
                    continue

                # 9. Own Website
                # If not a known major social network / messenger / file share
                excluded_hosts = {
                    "t.me", "telegram.me", "discord.gg", "discord.com", "spotify.com",
                    "anchor.fm", "apple.com", "amazon.com", "drive.google.com", "dropbox.com"
                }
                if not any(ex in domain for ex in excluded_hosts) and website is None:
                    website = {"url": normalized, "source": source}
                else:
                    other_links.append({"domain": domain, "url": normalized, "source": source})

        return {
            "website": website["url"] if website else None,
            "website_source": website["source"] if website else None,
            "instagram": social_links["instagram"]["url"] if social_links["instagram"] else None,
            "tiktok": social_links["tiktok"]["url"] if social_links["tiktok"] else None,
            "twitter": social_links["twitter"]["url"] if social_links["twitter"] else None,
            "facebook": social_links["facebook"]["url"] if social_links["facebook"] else None,
            "linkedin": social_links["linkedin"]["url"] if social_links["linkedin"] else None,
            "whatsapp_link": social_links["whatsapp_link"]["url"] if social_links["whatsapp_link"] else None,
            "whatsapp_source": social_links["whatsapp_link"]["source"] if social_links["whatsapp_link"] else None,
            "link_aggregators": link_aggregators,
            "sales_platforms": sales_platforms,
            "other_links": other_links
        }
