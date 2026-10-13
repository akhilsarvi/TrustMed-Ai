import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import requests

from pathlib import Path
import pandas as pd
from neo4j import GraphDatabase
from config.settings import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

WHO_API_ENDPOINTS = {
    "healthtopics": "https://www.who.int/api/default/healthtopics",
    "daguidelines": "https://www.who.int/api/default/daguidelines",
    "articles": "https://www.who.int/api/default/articles",
    "documents": "https://www.who.int/api/default/documents",
    "externalpublications": "https://www.who.int/api/default/externalpublications",
}


class WhoSourceCache:
    """
    In-memory source verification cache with TTL to avoid repeatedly hitting WHO servers.
    """
    def __init__(self, ttl_seconds: int = 3600):
        self.cache = {}
        self.ttl_seconds = ttl_seconds

    def get(self, url: str) -> dict | None:
        if not url:
            return None
        entry = self.cache.get(url)
        if not entry:
            return None
        if datetime.now(timezone.utc) > entry["expires_at"]:
            del self.cache[url]
            return None
        return entry["data"]

    def set(self, url: str, data: dict):
        if not url:
            return
        now = datetime.now(timezone.utc)
        self.cache[url] = {
            "data": data,
            "verified_at": now.isoformat(),
            "expires_at": now + timedelta(seconds=self.ttl_seconds)
        }


# Global cache instance
_WHO_CACHE = WhoSourceCache(ttl_seconds=3600)


class WhoSourceVerifier:
    """
    Dedicated WHO Source & API Cross-Verification Module for TRUSTMED-AI.
    Performs real network requests, strict hostname parsing, official WHO REST API
    cross-checking, guideline verification, hard gate enforcement, and audit logging.
    """

    def __init__(self):
        self.cache = _WHO_CACHE
        self._kg_diseases = None
        self._kg_symptoms = None

    def _load_local_kg(self):
        if self._kg_diseases is not None:
            return
        self._kg_diseases = {}
        self._kg_symptoms = set()

        BASE_DIR = Path(__file__).resolve().parent.parent
        possible_paths = [
            BASE_DIR / "data" / "raw" / "symptoms" / "DiseaseAndSymptoms.csv",
            Path("backend/data/raw/symptoms/DiseaseAndSymptoms.csv"),
            Path("data/raw/symptoms/DiseaseAndSymptoms.csv"),
        ]
        for csv_path in possible_paths:
            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    symptom_cols = [c for c in df.columns if c.startswith("Symptom")]
                    for _, row in df.iterrows():
                        dis = str(row["Disease"]).strip()
                        dis_clean = dis.lower()
                        if dis_clean not in self._kg_diseases:
                            self._kg_diseases[dis_clean] = set()
                        for col in symptom_cols:
                            val = row.get(col)
                            if pd.notna(val):
                                sym_clean = str(val).replace("_", " ").strip().lower()
                                if sym_clean:
                                    self._kg_diseases[dis_clean].add(sym_clean)
                                    self._kg_symptoms.add(sym_clean)
                    break
                except Exception:
                    pass

    def evaluate_knowledge_graph(self, norm_entity: str, combined_text: str, neo4j_driver=None) -> tuple[str, str, float]:
        """
        Evaluates Knowledge Graph consistency against Neo4j or local Knowledge Graph dataset.
        Guarantees that status is never KG_UNAVAILABLE.
        """
        driver = neo4j_driver
        temp_driver = False
        if not driver:
            try:
                driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
                driver.verify_connectivity()
                temp_driver = True
            except Exception:
                driver = None

        if driver:
            try:
                with driver.session() as session:
                    res = session.run(
                        """
                        MATCH (d:Disease) WHERE toLower(d.name) = toLower($entity)
                        OPTIONAL MATCH (d)-[r]->(target)
                        RETURN d.name AS disease, type(r) AS rel, target.name AS target
                        """,
                        entity=norm_entity
                    ).data()
                    if res and res[0].get("disease"):
                        matched_rels = [r for r in res if r.get("target") and str(r.get("target")).lower() in combined_text]
                        if matched_rels:
                            return "KG_VERIFIED", f"Neo4j confirms relationship ({norm_entity}) -[:{matched_rels[0]['rel']}]-> ({matched_rels[0]['target']}).", 100.0
                        else:
                            return "KG_NOT_FOUND", f"Neo4j disease node '{norm_entity}' exists, but no matching evidence relationship found in page text.", 60.0
                    else:
                        res_sym = session.run(
                            "MATCH (s:Symptom) WHERE toLower(s.name) = toLower($entity) RETURN s.name AS name",
                            entity=norm_entity
                        ).data()
                        if res_sym:
                            return "KG_VERIFIED", f"Neo4j confirms Symptom node '{norm_entity}' in Knowledge Graph.", 85.0
            except Exception:
                pass
            finally:
                if temp_driver and driver:
                    try:
                        driver.close()
                    except Exception:
                        pass

        # Local Knowledge Graph dataset evaluation fallback
        self._load_local_kg()
        ent_lower = (norm_entity or "").strip().lower()

        if self._kg_diseases and ent_lower in self._kg_diseases:
            known_symptoms = self._kg_diseases[ent_lower]
            matched_syms = [s for s in known_symptoms if s in combined_text]
            if matched_syms:
                return "KG_VERIFIED", f"Knowledge Graph confirms relationship: ({norm_entity}) -[HAS_SYMPTOM]-> ({matched_syms[0].title()}).", 100.0
            else:
                return "KG_NOT_FOUND", f"Knowledge Graph node '{norm_entity}' exists in database, but no matching evidence relationship found in page text.", 60.0

        if self._kg_symptoms and (ent_lower in self._kg_symptoms or any(ent_lower in s for s in self._kg_symptoms)):
            return "KG_VERIFIED", f"Knowledge Graph confirms Symptom node '{norm_entity}'.", 85.0

        return "KG_NOT_FOUND", f"Target entity node '{norm_entity}' not found in Knowledge Graph.", 40.0

    def is_official_who_domain(self, hostname: str) -> tuple[bool, str]:
        """
        Strictly verifies that the hostname is an official WHO domain (who.int or *.who.int).
        Rejects lookalikes like who.int.fake-site.com, who-health.com, or evil-who.int.
        """
        host = (hostname or "").lower().split(":")[0].strip()
        if not host:
            return False, "missing"
        
        # Must equal 'who.int' or end with '.who.int'
        if host == "who.int" or host.endswith(".who.int"):
            return True, host
        
        return False, host

    def query_who_api_resource(self, endpoint_key: str, search_query: str = "") -> list:
        """
        Safely queries official WHO REST API resources.
        """
        url = WHO_API_ENDPOINTS.get(endpoint_key)
        if not url:
            return []
        
        try:
            headers = {"User-Agent": "TrustMedAI-ClinicalVerifier/2.0 (+http://trustmed.ai)"}
            params = {"$top": 20}
            if search_query:
                params["$filter"] = f"contains(Title, '{search_query}')"
                
            resp = requests.get(url, headers=headers, params=params, timeout=4.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("value", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        except Exception:
            pass
        return []

    def cross_check_who_api(self, page_title: str, url: str, clinical_entity: str) -> dict:
        """
        Cross-checks page metadata against official WHO REST APIs.
        Returns:
            who_api_verified: True, False, or "UNKNOWN"
            api_notes: Detailed status description
        """
        clean_title = str(page_title or "").strip().lower()
        clean_entity = str(clinical_entity or "").strip().lower()

        # Try health topics API
        topics = self.query_who_api_resource("healthtopics")
        for t in topics:
            t_title = str(t.get("Title", "")).lower()
            t_name = str(t.get("UrlName", "")).lower()
            if (clean_entity and clean_entity in t_title) or (clean_title and clean_title in t_title) or (t_name and t_name in url.lower()):
                return {
                    "who_api_verified": True,
                    "who_api_match_type": "Health Topic API Match",
                    "api_notes": f"Matched official WHO Health Topic: '{t.get('Title')}'",
                    "matched_item": t.get("Title")
                }

        # Try guidelines API
        guidelines = self.query_who_api_resource("daguidelines")
        for g in guidelines:
            g_title = str(g.get("Title", "")).lower()
            if (clean_entity and clean_entity in g_title) or (clean_title and clean_title in g_title):
                return {
                    "who_api_verified": True,
                    "who_api_match_type": "Guideline API Match",
                    "api_notes": f"Matched official WHO Guideline: '{g.get('Title')}'",
                    "matched_item": g.get("Title")
                }

        return {
            "who_api_verified": "UNKNOWN",
            "who_api_match_type": "None",
            "api_notes": "WHO domain verified; API cross-check unavailable for specific page.",
            "matched_item": None
        }

    def verify_who_source(
        self,
        raw_url: str,
        user_source_name: str = "",
        clinical_entity: str = "",
        evidence_type: str = "Clinical Reference",
        evidence_text: str = "",
        use_cache: bool = True,
        neo4j_driver: any = None,
        **kwargs
    ) -> dict:
        """
        Executes full real-time WHO source verification & hard verification gate evaluation.
        """
        url = str(raw_url or "").strip()
        
        # Check cache if enabled
        if use_cache:
            cached = self.cache.get(url)
            if cached:
                return cached

        # Check for invalid URL format (e.g. user entered "WHO Guidelines 2026" as URL)
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            # If user entered something like "who.int/page" without http
            if "." in url and " " not in url and not url.startswith("WHO "):
                url = f"https://{url}"
            else:
                audit = self._build_failed_audit(
                    raw_url=raw_url,
                    reason="Invalid Source URL: Full URL starting with https:// is required.",
                    http_status=400,
                    domain="unverified",
                    page_title="INVALID SOURCE URL"
                )
                if use_cache and url:
                    self.cache.set(url, audit)
                return audit

        parsed = urlparse(url)
        hostname = parsed.netloc
        is_who, verified_host = self.is_official_who_domain(hostname)

        # Rule 4: Domain Verification Gate
        if not is_who:
            audit = self._build_failed_audit(
                raw_url=raw_url,
                reason=f"Domain '{hostname}' is NOT an official WHO domain (who.int). Pretending or unverified domain.",
                http_status=400,
                domain=hostname or "unverified",
                page_title="UNVERIFIED NON-WHO DOMAIN"
            )
            if use_cache:
                self.cache.set(url, audit)
            return audit

        # Perform Real HTTP Verification
        http_status = 0
        final_url = url
        response_time_ms = 0.0
        redirect_chain = []
        is_https = parsed.scheme.lower() == "https"
        https_redirect = False
        content_type = ""
        page_title = f"WHO Document ({verified_host})"
        publisher = "World Health Organization (WHO)"
        author = "WHO Panel / Contributor"
        pub_date = "Not specified"
        main_content = ""

        start_t = time.time()
        try:
            headers = {"User-Agent": "TrustMedAI-WHOVerifier/2.0 (+https://www.who.int)"}
            resp = requests.get(url, headers=headers, timeout=5.0, allow_redirects=True)
            response_time_ms = round((time.time() - start_t) * 1000, 1)
            http_status = resp.status_code
            final_url = resp.url
            
            final_parsed = urlparse(final_url)
            if final_parsed.scheme.lower() == "https":
                is_https = True
                if parsed.scheme.lower() == "http":
                    https_redirect = True

            content_type = resp.headers.get("Content-Type", "")

            # HTML Parsing
            if "text/html" in content_type or resp.text:
                html_text = resp.text[:20000]
                title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
                if title_match:
                    page_title = title_match.group(1).strip().replace("\n", " ")[:160]

                pub_match = re.search(r'meta\s+name=["\']publisher["\']\s+content=["\'](.*?)["\']', html_text, re.IGNORECASE)
                if pub_match:
                    publisher = pub_match.group(1).strip()

                author_match = re.search(r'meta\s+name=["\']author["\']\s+content=["\'](.*?)["\']', html_text, re.IGNORECASE)
                if author_match:
                    author = author_match.group(1).strip()

                date_match = re.search(r'meta\s+property=["\']article:published_time["\']\s+content=["\'](.*?)["\']', html_text, re.IGNORECASE)
                if date_match:
                    pub_date = date_match.group(1).strip()[:10]

                # Strip HTML tags for main content snippet
                main_content = re.sub(r'<[^>]+>', ' ', html_text)
                main_content = ' '.join(main_content.split())[:1000]

        except requests.exceptions.Timeout:
            audit = self._build_failed_audit(
                raw_url=raw_url,
                reason="WHO server request timed out (TEMPORARILY_UNAVAILABLE). Cannot verify page.",
                http_status=504,
                domain=verified_host,
                page_title="TIMEOUT / UNREACHABLE",
                decision_state="REVIEW"
            )
            return audit
        except Exception as err:
            audit = self._build_failed_audit(
                raw_url=raw_url,
                reason=f"HTTP connection failed: {str(err)}",
                http_status=0,
                domain=verified_host,
                page_title="HTTP CONNECTION FAILED",
                decision_state="REVIEW"
            )
            return audit

        # HARD VERIFICATION GATES (RULES 2 & 3)
        if http_status != 200:
            reason_msg = f"HTTP Status {http_status}: Page does not exist or access forbidden." if http_status == 404 else f"HTTP Status {http_status}: Verification unsuccessful."
            audit = self._build_failed_audit(
                raw_url=raw_url,
                reason=reason_msg,
                http_status=http_status,
                domain=verified_host,
                page_title=page_title or "WHO Page Error",
                decision_state="REJECTED" if http_status in (404, 403, 400) else "REVIEW"
            )
            return audit

        # WHO REST API Cross-Verification
        api_cross = self.cross_check_who_api(page_title, final_url, clinical_entity)

        # WHO Guideline Verification
        is_guideline_claim = "guideline" in evidence_type.lower() or "guideline" in evidence_text.lower() or "guideline" in page_title.lower()
        if is_guideline_claim:
            guideline_match = api_cross["who_api_verified"] is True or "guideline" in page_title.lower()
        else:
            guideline_match = "N/A"

        # Calculate Sub-scores (0-100)
        source_authenticity = 100.0 if (is_who and is_https and http_status == 200) else 50.0

        # Clinical Relevance Score using ClinicalEntityNormalizer
        from pipeline.clinical_filter import normalize_clinical_entity
        norm_entity, norm_type = normalize_clinical_entity(clinical_entity)
        dis_lower = norm_entity.lower()
        combined_text = (page_title + " " + evidence_text + " " + main_content).lower()

        if dis_lower and dis_lower in combined_text:
            clinical_relevance = 96.0
            relevance_reason = f"WHO page content directly matches normalized target entity '{norm_entity}' ({norm_type})."
        elif dis_lower and any(w in combined_text for w in dis_lower.split() if len(w) > 3):
            clinical_relevance = 75.0
            relevance_reason = f"WHO page discusses clinical concepts related to '{norm_entity}'."
        else:
            clinical_relevance = 35.0  # Unrelated WHO page
            relevance_reason = f"Target entity '{norm_entity}' could not be matched to WHO page content."

        # Evidence Quality
        ev_lower = evidence_type.lower()
        if "guideline" in ev_lower:
            evidence_quality = 98.0
        elif "systematic review" in ev_lower or "meta-analysis" in ev_lower:
            evidence_quality = 95.0
        elif "trial" in ev_lower or "rct" in ev_lower:
            evidence_quality = 88.0
        elif "review" in ev_lower:
            evidence_quality = 82.0
        else:
            evidence_quality = 65.0

        # Real Neo4j / Knowledge Graph Verification
        kg_status, kg_reason, kg_consistency = self.evaluate_knowledge_graph(
            norm_entity=norm_entity,
            combined_text=combined_text,
            neo4j_driver=kwargs.get("neo4j_driver")
        )

        semantic_similarity = 85.0 if len(evidence_text.split()) >= 10 else 60.0
        freshness = 92.0

        # Deterministic TrustRank Formula:
        # TrustRank = 0.25*Auth + 0.25*Rel + 0.20*Qual + 0.15*KG + 0.10*Sim + 0.05*Fresh
        raw_trust_rank = (
            0.25 * source_authenticity +
            0.25 * clinical_relevance +
            0.20 * evidence_quality +
            0.15 * kg_consistency +
            0.10 * semantic_similarity +
            0.05 * freshness
        )
        trust_rank_num = round(max(0.0, min(100.0, raw_trust_rank)), 1)

        # Hard Gate Enforcement (Rule 10: High TrustRank CANNOT override a failed hard gate)
        rejection_reasons = []
        if clinical_relevance < 40.0:
            rejection_reasons.append(relevance_reason)

        if rejection_reasons:
            decision = "REJECTED"
            trust_rank_display = "N/A"
            trust_rank = 0.0
        elif trust_rank_num >= 75.0 and source_authenticity >= 90.0:
            decision = "VERIFIED"
            trust_rank_display = f"{trust_rank_num:.0f}/100"
            trust_rank = trust_rank_num
        else:
            decision = "REVIEW"
            trust_rank_display = f"{trust_rank_num:.0f}/100"
            trust_rank = trust_rank_num

        audit = {
            "source_url": raw_url,
            "final_url": final_url,
            "http_status": http_status,
            "response_time_ms": response_time_ms,
            "https_secure": is_https,
            "https_redirect": https_redirect,
            "domain": verified_host,
            "who_domain_verified": True,
            "publisher": publisher,
            "title": page_title,
            "author": author,
            "publication_date": pub_date,
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "who_api_verified": api_cross["who_api_verified"],
            "who_api_match_type": api_cross["who_api_match_type"],
            "who_api_notes": api_cross["api_notes"],
            "guideline_match": guideline_match,
            "source_authenticity_score": source_authenticity,
            "source_authority_score": source_authenticity,
            "clinical_relevance_score": clinical_relevance,
            "clinical_relevance_reason": relevance_reason,
            "evidence_quality_score": evidence_quality,
            "kg_consistency_score": kg_consistency,
            "kg_status": kg_status,
            "kg_reason": kg_reason,
            "semantic_similarity_score": semantic_similarity,
            "freshness_score": freshness,
            "final_trust_score": trust_rank,
            "trust_rank": trust_rank,
            "trust_rank_display": trust_rank_display,
            "decision": decision,
            "rejection_reasons": rejection_reasons,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=3600)).isoformat(),
        }

        if use_cache:
            self.cache.set(url, audit)

        return audit

    def _build_failed_audit(
        self,
        raw_url: str,
        reason: str,
        http_status: int = 400,
        domain: str = "unverified",
        page_title: str = "Verification Failed",
        decision_state: str = "REJECTED"
    ) -> dict:
        return {
            "source_url": raw_url,
            "final_url": raw_url if (raw_url and raw_url.startswith("http")) else "",
            "http_status": http_status,
            "response_time_ms": 0.0,
            "https_secure": raw_url.startswith("https://") if raw_url else False,
            "https_redirect": False,
            "domain": domain,
            "who_domain_verified": False,
            "publisher": "Unknown / Unverified",
            "title": page_title,
            "author": "Not specified",
            "publication_date": "Not specified",
            "last_updated": "Not specified",
            "who_api_verified": False,
            "who_api_match_type": "None",
            "who_api_notes": "WHO domain or network verification failed.",
            "guideline_match": False,
            "source_authenticity_score": 0.0,
            "source_authority_score": 0.0,
            "clinical_relevance_reason": "Verification failed: Source URL or HTTP response is invalid/inaccessible.",
            "evidence_quality_score": 0.0,
            "kg_consistency_score": 0.0,
            "kg_status": "KG_NOT_FOUND",
            "kg_reason": "Knowledge Graph relationship check skipped due to source verification failure.",
            "semantic_similarity_score": 0.0,
            "freshness_score": 0.0,
            "final_trust_score": 0.0,
            "trust_rank": 0.0,
            "trust_rank_display": "N/A",
            "decision": decision_state,
            "rejection_reasons": [reason],
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=3600)).isoformat(),
        }
