import logging
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("dochat.paperless")


class PaperlessClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Token {token}",
            "Accept": "application/json",
        }

    async def get_documents(
        self,
        query: Optional[str] = None,
        correspondent_id: Optional[int] = None,
        document_type_id: Optional[int] = None,
        year: Optional[int] = None,
        page_size: int = 50,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"page_size": page_size}
        if query:
            params["query"] = query
        if correspondent_id:
            params["correspondent__id"] = correspondent_id
        if document_type_id:
            params["document_type__id"] = document_type_id
        if year:
            params["created__year"] = year

        url = f"{self.base_url}/api/documents/"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(url, headers=self.headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                return data.get("results", [])
            except Exception as e:
                logger.error(f"Error fetching documents from Paperless: {e}")
                return []

    async def get_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/documents/{document_id}/"
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(url, headers=self.headers)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.error(f"Error fetching document {document_id}: {e}")
                return None

    async def get_document_content(self, document_id: int) -> str:
        doc = await self.get_document(document_id)
        if doc and "content" in doc:
            return doc["content"] or ""
        return ""

    async def list_correspondents(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/correspondents/"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, headers=self.headers, params={"page_size": 100})
                resp.raise_for_status()
                return resp.json().get("results", [])
            except Exception as e:
                logger.error(f"Error fetching correspondents: {e}")
                return []

    async def list_document_types(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/document_types/"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, headers=self.headers, params={"page_size": 100})
                resp.raise_for_status()
                return resp.json().get("results", [])
            except Exception as e:
                logger.error(f"Error fetching document types: {e}")
                return []

    async def search_full_text(self, term: str, max_results: int = 5) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/documents/"
        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                resp = await client.get(url, headers=self.headers, params={"query": term, "page_size": max_results})
                resp.raise_for_status()
                return resp.json().get("results", [])
            except Exception as e:
                logger.error(f"Error searching documents for '{term}': {e}")
                return []
