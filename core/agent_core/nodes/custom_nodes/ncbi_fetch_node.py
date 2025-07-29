import logging
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from ...framework.tool_registry import tool_registry
from ..base_tool_node import BaseToolNode

logger = logging.getLogger(__name__)

@tool_registry(
    toolset_name="biomedical_tools",
    name="ncbi_fetch_article",
    description="Fetches detailed article information from PubMed/NCBI by PMID (PubMed ID). Returns comprehensive metadata, full abstracts, author information, MeSH terms, and citation details. Supports batch retrieval for multiple articles.",
    parameters={
        "type": "object",
        "properties": {
            "pmids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of PubMed IDs (PMIDs) to fetch. Example: ['12345678', '87654321']",
                "minItems": 1,
                "maxItems": 50
            },
            "pmid": {
                "type": "string", 
                "description": "Single PubMed ID (PMID) to fetch. Alternative to pmids array for single article."
            },
            "include_mesh_terms": {
                "type": "boolean",
                "description": "Whether to include MeSH (Medical Subject Headings) terms (default: true)",
                "default": True
            },
            "include_references": {
                "type": "boolean",
                "description": "Whether to include reference list if available (default: false)",
                "default": False
            },
            "include_grants": {
                "type": "boolean",
                "description": "Whether to include grant/funding information (default: true)",
                "default": True
            }
        },
        "oneOf": [
            {"required": ["pmids"]},
            {"required": ["pmid"]}
        ]
    },
    default_knowledge_item_type="PUBMED_ARTICLE_DETAILS"
)
class NCBIFetchNode(BaseToolNode):
    """
    NCBI PubMed article fetch tool for detailed literature retrieval.
    Uses NCBI E-utilities efetch API to get comprehensive article information.
    """
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    
    async def exec_async(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fetch detailed article information from PubMed by PMID(s).
        
        Returns:
            Dictionary with article details and metadata
        """
        try:
            tool_params = prep_res.get("tool_params", {})
            shared_context = prep_res.get("shared_context", {})
            
            # Handle both single PMID and array of PMIDs
            pmids = tool_params.get("pmids", [])
            single_pmid = tool_params.get("pmid")
            
            if single_pmid:
                pmids = [single_pmid]
            
            if not pmids:
                return {
                    "status": "error",
                    "error_message": "At least one PMID must be provided"
                }
            
            # Validate PMIDs
            valid_pmids = []
            for pmid in pmids:
                pmid_str = str(pmid).strip()
                if pmid_str.isdigit():
                    valid_pmids.append(pmid_str)
                else:
                    logger.warning("invalid_pmid", extra={"pmid": pmid_str})
            
            if not valid_pmids:
                return {
                    "status": "error",
                    "error_message": "No valid PMIDs provided. PMIDs must be numeric."
                }
            
            include_mesh = tool_params.get("include_mesh_terms", True)
            include_references = tool_params.get("include_references", False)
            include_grants = tool_params.get("include_grants", True)
            
            logger.info("ncbi_fetch_started", extra={
                "pmids": valid_pmids,
                "include_mesh": include_mesh,
                "include_references": include_references
            })
            
            # Check knowledge base for cached articles
            kb = shared_context.get('refs', {}).get('run', {}).get('runtime', {}).get("knowledge_base")
            cached_articles = []
            pmids_to_fetch = []
            
            if kb:
                for pmid in valid_pmids:
                    cache_key = f"ncbi_article://{pmid}_detailed"
                    cached_result = await kb.get_item_by_uri(cache_key)
                    if cached_result:
                        logger.info("ncbi_fetch_cache_hit", extra={"pmid": pmid})
                        cached_articles.append(cached_result.get("content", {}))
                    else:
                        pmids_to_fetch.append(pmid)
            else:
                pmids_to_fetch = valid_pmids
            
            # Fetch uncached articles
            fetched_articles = []
            if pmids_to_fetch:
                fetched_articles = await self._fetch_detailed_articles(
                    pmids_to_fetch, include_mesh, include_references, include_grants
                )
            
            # Combine cached and fetched articles
            all_articles = cached_articles + fetched_articles
            
            if not all_articles:
                return {
                    "status": "success",
                    "payload": {
                        "pmids_requested": valid_pmids,
                        "articles_found": 0,
                        "articles": [],
                        "message": "No articles found for the provided PMIDs"
                    }
                }
            
            # Prepare knowledge base items for newly fetched articles
            knowledge_items = []
            for article in fetched_articles:
                if article.get("pmid"):
                    knowledge_items.append({
                        "item_type": "PUBMED_ARTICLE_DETAILS",
                        "content": article,
                        "source_uri": f"ncbi_article://{article['pmid']}_detailed",
                        "metadata": {
                            "pmid": article["pmid"],
                            "title": article.get("title", "")[:100],
                            "fetch_type": "detailed_article",
                            "fetch_timestamp": datetime.utcnow().isoformat()
                        }
                    })
            
            return {
                "status": "success",
                "payload": {
                    "pmids_requested": valid_pmids,
                    "articles_found": len(all_articles),
                    "articles": all_articles,
                    "fetch_metadata": {
                        "cached_articles": len(cached_articles),
                        "newly_fetched": len(fetched_articles),
                        "fetch_timestamp": datetime.utcnow().isoformat()
                    }
                },
                "_knowledge_items_to_add": knowledge_items
            }
            
        except Exception as e:
            logger.error("ncbi_fetch_error", extra={"error": str(e)}, exc_info=True)
            return {
                "status": "error",
                "error_message": f"NCBI article fetch failed: {str(e)}"
            }
    
    async def _fetch_detailed_articles(self, pmids: List[str], include_mesh: bool, 
                                     include_references: bool, include_grants: bool) -> List[Dict[str, Any]]:
        """Fetch detailed article information using efetch API."""
        if not pmids:
            return []
        
        params = {
            'db': 'pubmed',
            'id': ','.join(pmids),
            'retmode': 'xml',
            'rettype': 'full'
        }
        
        url = f"{self.BASE_URL}efetch.fcgi"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=90)) as response:
                if response.status != 200:
                    raise Exception(f"NCBI efetch API returned status {response.status}")
                
                xml_content = await response.text()
                root = ET.fromstring(xml_content)
                
                articles = []
                for article_elem in root.findall('.//PubmedArticle'):
                    article_data = self._parse_detailed_article_xml(
                        article_elem, include_mesh, include_references, include_grants
                    )
                    if article_data:
                        articles.append(article_data)
                
                return articles
    
    def _parse_detailed_article_xml(self, article_elem, include_mesh: bool, 
                                  include_references: bool, include_grants: bool) -> Optional[Dict[str, Any]]:
        """Parse detailed article XML with comprehensive information."""
        try:
            citation = article_elem.find('.//MedlineCitation')
            if citation is None:
                return None
            
            pmid_elem = citation.find('.//PMID')
            pmid = pmid_elem.text if pmid_elem is not None else "Unknown"
            
            article = citation.find('.//Article')
            if article is None:
                return None
            
            # Basic information
            title_elem = article.find('.//ArticleTitle')
            title = title_elem.text if title_elem is not None else "No title available"
            
            # Detailed author information
            authors = self._parse_authors(article)
            
            # Journal information
            journal_info = self._parse_journal_info(article)
            
            # Publication date
            pub_date_info = self._parse_publication_date(article)
            
            # Abstract with sections
            abstract_info = self._parse_structured_abstract(article)
            
            # Article IDs (DOI, PMC, etc.)
            article_ids = self._parse_article_ids(article_elem)
            
            # Publication types
            pub_types = self._parse_publication_types(article)
            
            # Language
            language_elem = article.find('.//Language')
            language = language_elem.text if language_elem is not None else "eng"
            
            # Keywords (if available)
            keywords = self._parse_keywords(citation)
            
            # MeSH terms
            mesh_terms = []
            if include_mesh:
                mesh_terms = self._parse_mesh_terms(citation)
            
            # Grant information
            grants = []
            if include_grants:
                grants = self._parse_grants(article)
            
            # References (if requested)
            references = []
            if include_references:
                references = self._parse_references(article_elem)
            
            # Conflict of interest statement
            coi_statement = self._parse_conflict_of_interest(article)
            
            return {
                "pmid": pmid,
                "title": title,
                "authors": authors,
                "journal": journal_info,
                "publication_date": pub_date_info,
                "abstract": abstract_info,
                "article_ids": article_ids,
                "publication_types": pub_types,
                "language": language,
                "keywords": keywords,
                "mesh_terms": mesh_terms,
                "grants": grants,
                "references": references,
                "conflict_of_interest": coi_statement,
                "urls": {
                    "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "doi": article_ids.get("doi_url", ""),
                    "pmc": article_ids.get("pmc_url", "")
                },
                "fetch_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.warning("detailed_article_parse_error", extra={"error": str(e)})
            return None
    
    def _parse_authors(self, article) -> List[Dict[str, Any]]:
        """Parse detailed author information."""
        authors = []
        author_list = article.find('.//AuthorList')
        if author_list is not None:
            for author in author_list.findall('.//Author'):
                author_info = {}
                
                last_name = author.find('.//LastName')
                first_name = author.find('.//ForeName')
                initials = author.find('.//Initials')
                
                if last_name is not None:
                    author_info["last_name"] = last_name.text
                    full_name = last_name.text
                    
                    if first_name is not None:
                        author_info["first_name"] = first_name.text
                        full_name += f", {first_name.text}"
                    elif initials is not None:
                        author_info["initials"] = initials.text
                        full_name += f", {initials.text}"
                    
                    author_info["full_name"] = full_name
                
                # Affiliation
                affiliation = author.find('.//AffiliationInfo/Affiliation')
                if affiliation is not None:
                    author_info["affiliation"] = affiliation.text
                
                if author_info:
                    authors.append(author_info)
        
        return authors
    
    def _parse_journal_info(self, article) -> Dict[str, str]:
        """Parse detailed journal information."""
        journal_info = {}
        journal = article.find('.//Journal')
        
        if journal is not None:
            title = journal.find('.//Title')
            if title is not None:
                journal_info["title"] = title.text
            
            iso_abbr = journal.find('.//ISOAbbreviation')
            if iso_abbr is not None:
                journal_info["iso_abbreviation"] = iso_abbr.text
            
            issn = journal.find('.//ISSN')
            if issn is not None:
                journal_info["issn"] = issn.text
                journal_info["issn_type"] = issn.get('IssnType', '')
            
            volume = journal.find('.//JournalIssue/Volume')
            if volume is not None:
                journal_info["volume"] = volume.text
            
            issue = journal.find('.//JournalIssue/Issue')
            if issue is not None:
                journal_info["issue"] = issue.text
        
        return journal_info
    
    def _parse_publication_date(self, article) -> Dict[str, str]:
        """Parse publication date information."""
        pub_date_info = {}
        
        # Article date
        article_date = article.find('.//ArticleDate')
        if article_date is not None:
            year = article_date.find('.//Year')
            month = article_date.find('.//Month')
            day = article_date.find('.//Day')
            
            if year is not None:
                pub_date_info["year"] = year.text
                date_str = year.text
                if month is not None:
                    pub_date_info["month"] = month.text
                    date_str += f"-{month.text.zfill(2)}"
                    if day is not None:
                        pub_date_info["day"] = day.text
                        date_str += f"-{day.text.zfill(2)}"
                pub_date_info["article_date"] = date_str
        
        # Journal issue date
        pub_date = article.find('.//PubDate')
        if pub_date is not None:
            year = pub_date.find('.//Year')
            month = pub_date.find('.//Month')
            if year is not None:
                journal_date = year.text
                if month is not None:
                    journal_date += f" {month.text}"
                pub_date_info["journal_date"] = journal_date
        
        return pub_date_info
    
    def _parse_structured_abstract(self, article) -> Dict[str, Any]:
        """Parse structured abstract with sections."""
        abstract_info = {"text": "", "sections": []}
        
        abstract = article.find('.//Abstract')
        if abstract is not None:
            abstract_texts = abstract.findall('.//AbstractText')
            
            if abstract_texts:
                full_text = []
                sections = []
                
                for abs_text in abstract_texts:
                    text_content = abs_text.text or ""
                    label = abs_text.get('Label', '')
                    
                    if label:
                        sections.append({
                            "label": label,
                            "text": text_content
                        })
                        full_text.append(f"{label}: {text_content}")
                    else:
                        full_text.append(text_content)
                
                abstract_info["text"] = " ".join(full_text)
                abstract_info["sections"] = sections
        
        return abstract_info
    
    def _parse_article_ids(self, article_elem) -> Dict[str, str]:
        """Parse article identifiers (DOI, PMC, etc.)."""
        ids = {}
        article_ids = article_elem.find('.//ArticleIdList')
        
        if article_ids is not None:
            for article_id in article_ids.findall('.//ArticleId'):
                id_type = article_id.get('IdType', '')
                id_value = article_id.text or ""
                
                ids[id_type] = id_value
                
                # Create URLs for common ID types
                if id_type == 'doi':
                    ids["doi_url"] = f"https://doi.org/{id_value}"
                elif id_type == 'pmc':
                    ids["pmc_url"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{id_value}/"
        
        return ids
    
    def _parse_publication_types(self, article) -> List[str]:
        """Parse publication types."""
        pub_types = []
        pub_type_list = article.find('.//PublicationTypeList')
        
        if pub_type_list is not None:
            for pub_type in pub_type_list.findall('.//PublicationType'):
                if pub_type.text:
                    pub_types.append(pub_type.text)
        
        return pub_types
    
    def _parse_keywords(self, citation) -> List[str]:
        """Parse author keywords."""
        keywords = []
        keyword_list = citation.find('.//KeywordList')
        
        if keyword_list is not None:
            for keyword in keyword_list.findall('.//Keyword'):
                if keyword.text:
                    keywords.append(keyword.text)
        
        return keywords
    
    def _parse_mesh_terms(self, citation) -> List[Dict[str, Any]]:
        """Parse MeSH (Medical Subject Headings) terms."""
        mesh_terms = []
        mesh_heading_list = citation.find('.//MeshHeadingList')
        
        if mesh_heading_list is not None:
            for mesh_heading in mesh_heading_list.findall('.//MeshHeading'):
                descriptor = mesh_heading.find('.//DescriptorName')
                if descriptor is not None:
                    mesh_term = {
                        "descriptor": descriptor.text,
                        "major_topic": descriptor.get('MajorTopicYN', 'N') == 'Y',
                        "qualifiers": []
                    }
                    
                    # Parse qualifiers
                    for qualifier in mesh_heading.findall('.//QualifierName'):
                        mesh_term["qualifiers"].append({
                            "name": qualifier.text,
                            "major_topic": qualifier.get('MajorTopicYN', 'N') == 'Y'
                        })
                    
                    mesh_terms.append(mesh_term)
        
        return mesh_terms
    
    def _parse_grants(self, article) -> List[Dict[str, str]]:
        """Parse grant/funding information."""
        grants = []
        grant_list = article.find('.//GrantList')
        
        if grant_list is not None:
            for grant in grant_list.findall('.//Grant'):
                grant_info = {}
                
                grant_id = grant.find('.//GrantID')
                if grant_id is not None:
                    grant_info["grant_id"] = grant_id.text
                
                agency = grant.find('.//Agency')
                if agency is not None:
                    grant_info["agency"] = agency.text
                
                country = grant.find('.//Country')
                if country is not None:
                    grant_info["country"] = country.text
                
                if grant_info:
                    grants.append(grant_info)
        
        return grants
    
    def _parse_references(self, article_elem) -> List[str]:
        """Parse reference list (if available)."""
        # Note: References are not typically available through efetch
        # This is a placeholder for potential future enhancement
        return []
    
    def _parse_conflict_of_interest(self, article) -> str:
        """Parse conflict of interest statement."""
        # Look for COI statement in various locations
        coi_sections = [
            './/CoiStatement',
            './/ConflictOfInterestStatement'
        ]
        
        for section in coi_sections:
            coi_elem = article.find(section)
            if coi_elem is not None and coi_elem.text:
                return coi_elem.text
        
        return ""