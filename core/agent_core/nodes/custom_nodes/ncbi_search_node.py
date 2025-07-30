import logging
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional
from datetime import datetime
from urllib.parse import quote_plus

from ...framework.tool_registry import tool_registry
from ..base_tool_node import BaseToolNode

logger = logging.getLogger(__name__)

@tool_registry(
    toolset_name="biomedical_tools",
    name="ncbi_pubmed_search",
    description="Searches PubMed/NCBI database for clinical and biomedical literature. Returns structured results with abstracts, publication details, and metadata. Supports advanced search filters for study types, publication dates, and clinical relevance.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for PubMed. Use medical subject headings (MeSH terms) and clinical keywords. Examples: 'diabetes mellitus type 2 treatment', 'COVID-19 vaccine efficacy', 'cardiac arrest CPR outcomes'"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of articles to retrieve (1-100, default: 20)",
                "minimum": 1,
                "maximum": 100,
                "default": 20
            },
            "publication_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by publication types. Options: 'Clinical Trial', 'Randomized Controlled Trial', 'Meta-Analysis', 'Systematic Review', 'Review', 'Case Reports', 'Observational Study'",
                "default": []
            },
            "date_range": {
                "type": "object",
                "properties": {
                    "start_year": {"type": "integer", "description": "Start year (e.g., 2020)"},
                    "end_year": {"type": "integer", "description": "End year (e.g., 2024)"}
                },
                "description": "Optional date range filter"
            },
            "include_abstracts": {
                "type": "boolean",
                "description": "Whether to fetch full abstracts (default: true)",
                "default": True
            }
        },
        "required": ["query"]
    },
    default_knowledge_item_type="PUBMED_SEARCH_RESULTS"
)
class NCBISearchNode(BaseToolNode):
    """
    NCBI PubMed search tool for clinical literature access.
    Uses NCBI E-utilities API (esearch and efetch) to retrieve biomedical literature.
    """
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    
    async def exec_async(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute PubMed search using NCBI E-utilities API.
        
        Returns:
            Dictionary with status, search results, and metadata
        """
        try:
            tool_params = prep_res.get("tool_params", {})
            shared_context = prep_res.get("shared_context", {})
            
            query = tool_params.get("query", "").strip()
            max_results = min(tool_params.get("max_results", 20), 100)
            publication_types = tool_params.get("publication_types", [])
            date_range = tool_params.get("date_range", {})
            include_abstracts = tool_params.get("include_abstracts", True)
            
            if not query:
                return {
                    "status": "error",
                    "error_message": "Search query cannot be empty"
                }
            
            logger.info("ncbi_search_started", extra={
                "query": query, 
                "max_results": max_results,
                "include_abstracts": include_abstracts
            })
            
            # Check knowledge base for cached results
            kb = shared_context.get('refs', {}).get('run', {}).get('runtime', {}).get("knowledge_base")
            cache_key = f"ncbi_search://{query}_{max_results}_{str(publication_types)}_{str(date_range)}"
            
            if kb:
                cached_result = await kb.get_item_by_uri(cache_key)
                if cached_result:
                    logger.info("ncbi_search_cache_hit", extra={"query": query})
                    cached_data = cached_result.get("content", {})
                    return {
                        "status": "success",
                        "payload": {
                            "query": query,
                            "source": "knowledge_base_cache",
                            "total_results": cached_data.get("total_results", 0),
                            "articles": cached_data.get("articles", []),
                            "search_metadata": cached_data.get("search_metadata", {})
                        }
                    }
            
            # Build search query with filters
            search_query = self._build_search_query(query, publication_types, date_range)
            
            # Step 1: Search for PMIDs
            pmids = await self._search_pmids(search_query, max_results)
            
            if not pmids:
                return {
                    "status": "success",
                    "payload": {
                        "query": query,
                        "total_results": 0,
                        "articles": [],
                        "message": "No articles found matching the search criteria"
                    }
                }
            
            # Step 2: Fetch article details
            articles = await self._fetch_article_details(pmids, include_abstracts)
            
            # Prepare results
            search_results = {
                "query": query,
                "total_results": len(articles),
                "articles": articles,
                "search_metadata": {
                    "search_query_used": search_query,
                    "publication_types_filter": publication_types,
                    "date_range_filter": date_range,
                    "max_results_requested": max_results,
                    "search_timestamp": datetime.utcnow().isoformat()
                }
            }
            
            # Prepare knowledge base items
            knowledge_items = []
            if articles:
                knowledge_items.append({
                    "item_type": "PUBMED_SEARCH_RESULTS",
                    "content": search_results,
                    "source_uri": cache_key,
                    "metadata": {
                        "query": query,
                        "result_count": len(articles),
                        "search_type": "pubmed_clinical_search"
                    }
                })
            
            return {
                "status": "success",
                "payload": search_results,
                "_knowledge_items_to_add": knowledge_items
            }
            
        except Exception as e:
            logger.error("ncbi_search_error", extra={"error": str(e)}, exc_info=True)
            return {
                "status": "error",
                "error_message": f"NCBI search failed: {str(e)}"
            }
    
    def _build_search_query(self, query: str, publication_types: List[str], date_range: Dict) -> str:
        """Build NCBI search query with filters."""
        search_parts = [query]
        
        # Add publication type filters
        if publication_types:
            pub_type_map = {
                'Clinical Trial': 'Clinical Trial[ptyp]',
                'Randomized Controlled Trial': 'Randomized Controlled Trial[ptyp]',
                'Meta-Analysis': 'Meta-Analysis[ptyp]',
                'Systematic Review': 'Systematic Review[ptyp]',
                'Review': 'Review[ptyp]',
                'Case Reports': 'Case Reports[ptyp]',
                'Observational Study': 'Observational Study[ptyp]'
            }
            
            pub_filters = [pub_type_map.get(pt, pt) for pt in publication_types if pt in pub_type_map]
            if pub_filters:
                search_parts.append(f"({' OR '.join(pub_filters)})")
        
        # Add date range filter
        if date_range:
            start_year = date_range.get('start_year')
            end_year = date_range.get('end_year')
            if start_year and end_year:
                search_parts.append(f"{start_year}:{end_year}[pdat]")
            elif start_year:
                search_parts.append(f"{start_year}:3000[pdat]")
            elif end_year:
                search_parts.append(f"1900:{end_year}[pdat]")
        
        return " AND ".join(search_parts)
    
    async def _search_pmids(self, query: str, max_results: int) -> List[str]:
        """Search for PMIDs using esearch API."""
        params = {
            'db': 'pubmed',
            'term': query,
            'retmax': str(max_results),
            'retmode': 'xml',
            'sort': 'relevance'
        }
        
        url = f"{self.BASE_URL}esearch.fcgi"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    raise Exception(f"NCBI esearch API returned status {response.status}")
                
                xml_content = await response.text()
                root = ET.fromstring(xml_content)
                
                # Extract PMIDs
                pmids = []
                for id_elem in root.findall('.//Id'):
                    if id_elem.text:
                        pmids.append(id_elem.text)
                
                return pmids
    
    async def _fetch_article_details(self, pmids: List[str], include_abstracts: bool) -> List[Dict[str, Any]]:
        """Fetch article details using efetch API."""
        if not pmids:
            return []
        
        params = {
            'db': 'pubmed',
            'id': ','.join(pmids),
            'retmode': 'xml',
            'rettype': 'abstract' if include_abstracts else 'medline'
        }
        
        url = f"{self.BASE_URL}efetch.fcgi"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status != 200:
                    raise Exception(f"NCBI efetch API returned status {response.status}")
                
                xml_content = await response.text()
                root = ET.fromstring(xml_content)
                
                articles = []
                for article_elem in root.findall('.//PubmedArticle'):
                    article_data = self._parse_article_xml(article_elem, include_abstracts)
                    if article_data:
                        articles.append(article_data)
                
                return articles
    
    def _parse_article_xml(self, article_elem, include_abstracts: bool) -> Optional[Dict[str, Any]]:
        """Parse individual article XML element."""
        try:
            citation = article_elem.find('.//MedlineCitation')
            if citation is None:
                return None
            
            pmid_elem = citation.find('.//PMID')
            pmid = pmid_elem.text if pmid_elem is not None else "Unknown"
            
            article = citation.find('.//Article')
            if article is None:
                return None
            
            # Title
            title_elem = article.find('.//ArticleTitle')
            title = title_elem.text if title_elem is not None else "No title available"
            
            # Authors
            authors = []
            author_list = article.find('.//AuthorList')
            if author_list is not None:
                for author in author_list.findall('.//Author'):
                    last_name = author.find('.//LastName')
                    first_name = author.find('.//ForeName')
                    if last_name is not None:
                        author_name = last_name.text
                        if first_name is not None:
                            author_name += f", {first_name.text}"
                        authors.append(author_name)
            
            # Journal
            journal_elem = article.find('.//Journal/Title')
            journal = journal_elem.text if journal_elem is not None else "Unknown journal"
            
            # Publication date
            pub_date = article.find('.//PubDate')
            pub_date_str = "Unknown date"
            if pub_date is not None:
                year = pub_date.find('.//Year')
                month = pub_date.find('.//Month')
                if year is not None:
                    pub_date_str = year.text
                    if month is not None:
                        pub_date_str += f" {month.text}"
            
            # Abstract
            abstract = ""
            if include_abstracts:
                abstract_elem = article.find('.//Abstract/AbstractText')
                if abstract_elem is not None:
                    abstract = abstract_elem.text or ""
            
            # DOI
            doi = ""
            article_ids = article_elem.find('.//ArticleIdList')
            if article_ids is not None:
                for article_id in article_ids.findall('.//ArticleId'):
                    if article_id.get('IdType') == 'doi':
                        doi = article_id.text or ""
                        break
            
            # Publication types
            pub_types = []
            pub_type_list = article.find('.//PublicationTypeList')
            if pub_type_list is not None:
                for pub_type in pub_type_list.findall('.//PublicationType'):
                    if pub_type.text:
                        pub_types.append(pub_type.text)
            
            return {
                "pmid": pmid,
                "title": title,
                "authors": authors[:10],  # Limit to first 10 authors
                "journal": journal,
                "publication_date": pub_date_str,
                "abstract": abstract,
                "doi": doi,
                "publication_types": pub_types,
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "doi_url": f"https://doi.org/{doi}" if doi else ""
            }
            
        except Exception as e:
            logger.warning("article_parse_error", extra={"error": str(e)})
            return None