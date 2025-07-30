import logging
import asyncio
import aiohttp
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from urllib.parse import urlencode

from ...framework.tool_registry import tool_registry
from ..base_tool_node import BaseToolNode

logger = logging.getLogger(__name__)

@tool_registry(
    toolset_name="clinical_research",
    name="clinical_trials",
    description="Searches ClinicalTrials.gov database for clinical trials and research studies. Returns structured results with trial details, eligibility criteria, locations, and study status. Supports filtering by condition, intervention, location, study phase, and recruitment status.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "General search query for clinical trials. Use medical terms, condition names, or intervention names. Examples: 'melanoma BRAF inhibitor', 'diabetes insulin therapy', 'COVID-19 vaccine'"
            },
            "condition": {
                "type": "string",
                "description": "Specific medical condition or disease. Examples: 'Diabetes Mellitus', 'Breast Cancer', 'Alzheimer Disease'"
            },
            "intervention": {
                "type": "string", 
                "description": "Treatment or intervention being studied. Examples: 'Pembrolizumab', 'Radiation Therapy', 'Behavioral Intervention'"
            },
            "location": {
                "type": "string",
                "description": "Geographic location for trials. Examples: 'United States', 'California', 'Boston', 'Germany'"
            },
            "recruitment_status": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by recruitment status. Options: 'Recruiting', 'Not yet recruiting', 'Active, not recruiting', 'Completed', 'Suspended', 'Terminated', 'Withdrawn'. Can specify multiple statuses.",
                "default": []
            },
            "study_phase": {
                "type": "array", 
                "items": {"type": "string"},
                "description": "Filter by study phase. Options: 'Early Phase 1', 'Phase 1', 'Phase 2', 'Phase 3', 'Phase 4', 'Not Applicable'. Can specify multiple phases to include studies in any of those phases.",
                "default": []
            },
            "study_type": {
                "type": "string",
                "description": "Type of study. Options: 'Interventional', 'Observational', 'Expanded Access'",
                "default": "Interventional"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of studies to retrieve (1-1000, default: 50)",
                "minimum": 1,
                "maximum": 1000,
                "default": 50
            },
            "sort_by": {
                "type": "string",
                "description": "Sort results by field. Options: 'LastUpdatePostDate', 'StudyFirstPostDate', 'PrimaryCompletionDate'",
                "default": "LastUpdatePostDate"
            },
            "sort_order": {
                "type": "string",
                "description": "Sort order. Options: 'asc', 'desc'",
                "default": "desc"
            }
        },
        "required": []
    },
    default_knowledge_item_type="CLINICAL_TRIALS_SEARCH_RESULTS"
)
class ClinicalTrialsNode(BaseToolNode):
    """
    ClinicalTrials.gov search tool for clinical trial research.
    Uses ClinicalTrials.gov API v2.0 to retrieve clinical study information.
    """
    
    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
    
    async def exec_async(self, prep_res: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute clinical trials search using ClinicalTrials.gov API v2.0.
        
        Returns:
            Dictionary with status, search results, and metadata
        """
        try:
            tool_params = prep_res.get("tool_params", {})
            shared_context = prep_res.get("shared_context", {})
            
            # Extract search parameters
            query = tool_params.get("query", "").strip()
            condition = tool_params.get("condition", "").strip()
            intervention = tool_params.get("intervention", "").strip()
            location = tool_params.get("location", "").strip()
            recruitment_status = tool_params.get("recruitment_status", [])
            study_phase = tool_params.get("study_phase", [])
            study_type = tool_params.get("study_type", "Interventional")
            max_results = min(tool_params.get("max_results", 50), 1000)
            sort_by = tool_params.get("sort_by", "LastUpdatePostDate")
            sort_order = tool_params.get("sort_order", "desc")
            
            # Validate that at least one search parameter is provided
            if not any([query, condition, intervention, location]):
                return {
                    "status": "error",
                    "error_message": "At least one search parameter (query, condition, intervention, or location) must be provided"
                }
            
            logger.info("clinical_trials_search_started", extra={
                "query": query,
                "condition": condition,
                "intervention": intervention,
                "max_results": max_results
            })
            
            # Build search parameters
            search_params = self._build_search_params(
                query, condition, intervention, location, recruitment_status,
                study_phase, study_type, max_results, sort_by, sort_order
            )
            
            # Check knowledge base for cached results
            kb = shared_context.get('refs', {}).get('run', {}).get('runtime', {}).get("knowledge_base")
            cache_key = f"clinical_trials://{self._generate_cache_key(search_params)}"
            
            if kb:
                cached_result = await kb.get_item_by_uri(cache_key)
                if cached_result:
                    logger.info("clinical_trials_cache_hit", extra={"cache_key": cache_key})
                    cached_data = cached_result.get("content", {})
                    return {
                        "status": "success",
                        "payload": {
                            **cached_data,
                            "source": "knowledge_base_cache"
                        }
                    }
            
            # Fetch data from ClinicalTrials.gov API
            trials_data = await self._fetch_clinical_trials(search_params)
            
            if not trials_data.get("studies"):
                return {
                    "status": "success",
                    "payload": {
                        "search_parameters": search_params,
                        "total_results": 0,
                        "studies": [],
                        "message": "No clinical trials found matching the search criteria"
                    }
                }
            
            # Process and structure the results
            processed_results = self._process_trial_results(trials_data, search_params)
            
            # Prepare knowledge base items
            knowledge_items = []
            if processed_results.get("studies"):
                knowledge_items.append({
                    "item_type": "CLINICAL_TRIALS_SEARCH_RESULTS",
                    "content": processed_results,
                    "source_uri": cache_key,
                    "metadata": {
                        "search_query": query,
                        "condition": condition,
                        "intervention": intervention,
                        "result_count": len(processed_results["studies"]),
                        "search_type": "clinical_trials_search"
                    }
                })
            
            return {
                "status": "success",
                "payload": processed_results,
                "_knowledge_items_to_add": knowledge_items
            }
            
        except Exception as e:
            logger.error("clinical_trials_search_error", extra={"error": str(e)}, exc_info=True)
            return {
                "status": "error",
                "error_message": f"Clinical trials search failed: {str(e)}"
            }
    
    def _build_search_params(self, query: str, condition: str, intervention: str, 
                           location: str, recruitment_status: List[str], study_phase: List[str],
                           study_type: str, max_results: int, sort_by: str, sort_order: str) -> Dict[str, Any]:
        """Build search parameters for ClinicalTrials.gov API v2.0."""
        params = {
            "pageSize": max_results,
            "countTotal": "true",
            "format": "json"
        }
        
        # Add sort parameter if specified
        if sort_by:
            params["sort"] = f"{sort_by}:{sort_order}" if sort_order else sort_by
        
        # Add query parameters (these are correct for API v2.0)
        if query:
            params["query.term"] = query
        if condition:
            params["query.cond"] = condition
        if intervention:
            params["query.intr"] = intervention
        if location:
            params["query.locn"] = location
        
        # Add recruitment status filter (API v2.0 uses filter.overallStatus)
        if recruitment_status:
            # Map user-friendly values to API v2.0 enum values
            mapped_statuses = [self._map_recruitment_status(status) for status in recruitment_status]
            params["filter.overallStatus"] = ",".join(mapped_statuses)
        
        # Build advanced filter for phase and study type using Essie syntax
        advanced_filters = []
        
        if study_phase:
            # Map user-friendly phase values to API v2.0 enum values
            mapped_phases = [self._map_study_phase(phase) for phase in study_phase]
            phase_filter = " OR ".join([f"AREA[Phase]{phase}" for phase in mapped_phases])
            if len(mapped_phases) > 1:
                phase_filter = f"({phase_filter})"
            advanced_filters.append(phase_filter)
        
        if study_type and study_type.lower() != "interventional":  # Interventional is default
            # Map study type to API v2.0 enum value
            mapped_type = self._map_study_type(study_type)
            advanced_filters.append(f"AREA[StudyType]{mapped_type}")
        
        # Combine advanced filters
        if advanced_filters:
            params["filter.advanced"] = " AND ".join(advanced_filters)
        
        return params
    
    def _generate_cache_key(self, params: Dict[str, Any]) -> str:
        """Generate a unique cache key from search parameters."""
        # Sort parameters for consistent cache keys
        sorted_params = sorted(params.items())
        return "_".join([f"{k}={v}" for k, v in sorted_params])
    
    def _map_recruitment_status(self, status: str) -> str:
        """Map user-friendly recruitment status to API v2.0 enum values."""
        # Convert to lowercase for case-insensitive matching
        status_lower = status.lower().replace(" ", "_").replace(",", "")
        
        status_mapping = {
            "recruiting": "RECRUITING",
            "not_yet_recruiting": "NOT_YET_RECRUITING", 
            "active_not_recruiting": "ACTIVE_NOT_RECRUITING",
            "completed": "COMPLETED",
            "suspended": "SUSPENDED",
            "terminated": "TERMINATED",
            "withdrawn": "WITHDRAWN",
            "available": "AVAILABLE",
            "no_longer_available": "NO_LONGER_AVAILABLE",
            "temporarily_not_available": "TEMPORARILY_NOT_AVAILABLE",
            "approved_for_marketing": "APPROVED_FOR_MARKETING",
            "withheld": "WITHHELD",
            "unknown": "UNKNOWN"
        }
        
        return status_mapping.get(status_lower, status.upper())
    
    def _map_study_phase(self, phase: str) -> str:
        """Map user-friendly study phase to API v2.0 enum values."""
        # Convert to lowercase for case-insensitive matching
        phase_lower = phase.lower().replace(" ", "_").replace("-", "_")
        
        phase_mapping = {
            "early_phase_1": "EARLY_PHASE1",
            "early_phase1": "EARLY_PHASE1",
            "phase_1": "PHASE1", 
            "phase1": "PHASE1",
            "phase_2": "PHASE2",
            "phase2": "PHASE2", 
            "phase_3": "PHASE3",
            "phase3": "PHASE3",
            "phase_4": "PHASE4",
            "phase4": "PHASE4",
            "na": "NA",
            "not_applicable": "NA"
        }
        
        return phase_mapping.get(phase_lower, phase.upper())
    
    def _map_study_type(self, study_type: str) -> str:
        """Map user-friendly study type to API v2.0 enum values."""
        # Convert to lowercase for case-insensitive matching
        type_lower = study_type.lower().replace(" ", "_")
        
        type_mapping = {
            "interventional": "INTERVENTIONAL",
            "observational": "OBSERVATIONAL", 
            "expanded_access": "EXPANDED_ACCESS"
        }
        
        return type_mapping.get(type_lower, study_type.upper())
    
    async def _fetch_clinical_trials(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch clinical trials data from ClinicalTrials.gov API."""
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(self.BASE_URL, params=params) as response:
                if response.status == 429:
                    raise Exception("Rate limit exceeded. Please wait before making more requests.")
                elif response.status != 200:
                    response_text = await response.text()
                    raise Exception(f"ClinicalTrials.gov API returned status {response.status}: {response_text}")
                
                return await response.json()
    
    def _process_trial_results(self, trials_data: Dict[str, Any], search_params: Dict[str, Any]) -> Dict[str, Any]:
        """Process and structure the clinical trials results."""
        studies = trials_data.get("studies", [])
        total_count = trials_data.get("totalCount", len(studies))
        
        processed_studies = []
        for study in studies:
            try:
                processed_study = self._process_single_study(study)
                if processed_study:
                    processed_studies.append(processed_study)
            except Exception as e:
                logger.warning("study_processing_error", extra={
                    "nct_id": study.get("protocolSection", {}).get("identificationModule", {}).get("nctId", "unknown"),
                    "error": str(e)
                })
                continue
        
        return {
            "search_parameters": search_params,
            "total_results": total_count,
            "results_returned": len(processed_studies),
            "studies": processed_studies,
            "search_metadata": {
                "search_timestamp": datetime.utcnow().isoformat(),
                "api_version": "v2.0",
                "source": "clinicaltrials.gov"
            }
        }
    
    def _process_single_study(self, study: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process individual study data."""
        try:
            protocol = study.get("protocolSection", {})
            if not protocol:
                return None
                
            # Identification module
            identification = protocol.get("identificationModule", {})
            nct_id = identification.get("nctId", "")
            title = identification.get("briefTitle", "")
            
            if not nct_id:
                return None
            
            # Status module
            status_module = protocol.get("statusModule", {})
            overall_status = status_module.get("overallStatus", "Unknown")
            last_update = status_module.get("lastUpdatePostDateStruct", {}).get("date", "")
            
            # Design module
            design_module = protocol.get("designModule", {})
            study_type = design_module.get("studyType", "")
            phases = design_module.get("phases", [])
            
            # Conditions module
            conditions_module = protocol.get("conditionsModule", {})
            conditions = conditions_module.get("conditions", [])
            
            # Arms/Interventions module
            arms_module = protocol.get("armsInterventionsModule", {})
            interventions = []
            if arms_module.get("interventions"):
                interventions = [
                    {
                        "name": interv.get("name", ""),
                        "type": interv.get("type", ""),
                        "description": interv.get("description", "")[:200] + "..." if len(interv.get("description", "")) > 200 else interv.get("description", "")
                    }
                    for interv in arms_module.get("interventions", [])[:5]  # Limit to 5 interventions
                ]
            
            # Eligibility module
            eligibility_module = protocol.get("eligibilityModule", {})
            eligibility_criteria = eligibility_module.get("eligibilityCriteria", "")
            min_age = eligibility_module.get("minimumAge", "")
            max_age = eligibility_module.get("maximumAge", "")
            sex = eligibility_module.get("sex", "")
            
            # Contacts and locations module
            contacts_module = protocol.get("contactsLocationsModule", {})
            locations = []
            if contacts_module.get("locations"):
                locations = [
                    {
                        "facility": loc.get("facility", ""),
                        "city": loc.get("city", ""),
                        "state": loc.get("state", ""),
                        "country": loc.get("country", ""),
                        "status": loc.get("status", "")
                    }
                    for loc in contacts_module.get("locations", [])[:10]  # Limit to 10 locations
                ]
            
            # Sponsor collaborators module
            sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
            lead_sponsor = sponsor_module.get("leadSponsor", {}).get("name", "")
            
            return {
                "nct_id": nct_id,
                "title": title,
                "overall_status": overall_status,
                "study_type": study_type,
                "phases": phases,
                "conditions": conditions,
                "interventions": interventions,
                "lead_sponsor": lead_sponsor,
                "last_update": last_update,
                "eligibility": {
                    "criteria": eligibility_criteria[:500] + "..." if len(eligibility_criteria) > 500 else eligibility_criteria,
                    "min_age": min_age,
                    "max_age": max_age,
                    "sex": sex
                },
                "locations": locations,
                "study_url": f"https://clinicaltrials.gov/study/{nct_id}",
                "api_url": f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
            }
            
        except Exception as e:
            logger.warning("single_study_processing_error", extra={"error": str(e)})
            return None


