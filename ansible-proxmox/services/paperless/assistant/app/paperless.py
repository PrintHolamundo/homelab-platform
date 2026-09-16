import logging
from typing import Any, Optional
import httpx
from app.config import settings

logger = logging.getLogger("paperless_client")

class PaperlessClient:
    def __init__(self):
        self.base_url = settings.paperless_api_url
        self.headers = {
            "Authorization": f"Token {settings.paperless_api_token}",
            "Accept": "application/json",
        }
        self._tag_cache: dict[int, str] = {}
        self._type_cache: dict[int, str] = {}
        self._corr_cache: dict[int, str] = {}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    async def check_health(self) -> bool:
        try:
            async with self._client() as client:
                res = await client.get("/")
                return res.status_code in (200, 401, 403)
        except Exception as e:
            logger.error(f"Paperless healthcheck failed: {e}")
            return False

    async def get_metadata_mappings(self) -> None:
        """Fetch tags, document types and correspondents for human-readable resolution."""
        try:
            async with self._client() as client:
                # Tags
                tags_res = await client.get("/tags/?page_size=100")
                if tags_res.status_code == 200:
                    for t in tags_res.json().get("results", []):
                        self._tag_cache[t["id"]] = t.get("name", "")

                # Document Types
                types_res = await client.get("/document_types/?page_size=100")
                if types_res.status_code == 200:
                    for dt in types_res.json().get("results", []):
                        self._type_cache[dt["id"]] = dt.get("name", "")

                # Correspondents
                corr_res = await client.get("/correspondents/?page_size=100")
                if corr_res.status_code == 200:
                    for c in corr_res.json().get("results", []):
                        self._corr_cache[c["id"]] = c.get("name", "")
        except Exception as e:
            logger.warning(f"Could not load metadata mappings: {e}")

    def resolve_tag_names(self, tag_ids: list[int]) -> list[str]:
        return [self._tag_cache.get(tid, str(tid)) for tid in tag_ids]

    def resolve_type_name(self, type_id: Optional[int]) -> Optional[str]:
        if type_id is None:
            return None
        return self._type_cache.get(type_id, str(type_id))

    def resolve_correspondent_name(self, corr_id: Optional[int]) -> Optional[str]:
        if corr_id is None:
            return None
        return self._corr_cache.get(corr_id, str(corr_id))

    async def search_documents(
        self,
        query: str,
        page_size: int = 5,
        page: int = 1,
        ordering: str = "-created",
    ) -> dict[str, Any]:
        """Search documents using Paperless-ngx full-text search."""
        if not self._tag_cache:
            await self.get_metadata_mappings()

        params = {
            "query": query,
            "page_size": page_size,
            "page": page,
            "ordering": ordering,
            "truncate_content": "true",
        }

        async with self._client() as client:
            res = await client.get("/documents/", params=params)
            res.raise_for_status()
            data = res.json()

            results = []
            for doc in data.get("results", []):
                doc_id = doc["id"]
                results.append({
                    "id": doc_id,
                    "title": doc.get("title"),
                    "created": doc.get("created"),
                    "modified": doc.get("modified"),
                    "document_type": self.resolve_type_name(doc.get("document_type")),
                    "correspondent": self.resolve_correspondent_name(doc.get("correspondent")),
                    "tags": self.resolve_tag_names(doc.get("tags", [])),
                    "snippet": (doc.get("content") or "")[:400].strip(),
                    "web_url": f"{settings.base_paperless_url}/documents/{doc_id}/details",
                })

            return {
                "count": data.get("count", 0),
                "results": results,
            }

    async def get_document_content(self, document_id: int) -> dict[str, Any]:
        """Fetch complete OCR content and metadata for a specific document."""
        if not self._tag_cache:
            await self.get_metadata_mappings()

        async with self._client() as client:
            res = await client.get(f"/documents/{document_id}/")
            res.raise_for_status()
            doc = res.json()

            return {
                "id": doc["id"],
                "title": doc.get("title"),
                "created": doc.get("created"),
                "modified": doc.get("modified"),
                "document_type": self.resolve_type_name(doc.get("document_type")),
                "correspondent": self.resolve_correspondent_name(doc.get("correspondent")),
                "tags": self.resolve_tag_names(doc.get("tags", [])),
                "content": doc.get("content", ""),
                "web_url": f"{settings.base_paperless_url}/documents/{document_id}/details",
                "download_url": f"{settings.base_paperless_url}/api/documents/{document_id}/download/",
            }

    async def list_recent_documents(
        self,
        limit: int = 10,
        query: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List recent documents, optionally filtered by keyword."""
        if not self._tag_cache:
            await self.get_metadata_mappings()

        params = {"page_size": limit, "ordering": "-created"}
        if query:
            params["query"] = query

        async with self._client() as client:
            res = await client.get("/documents/", params=params)
            res.raise_for_status()
            docs = res.json().get("results", [])

            return [
                {
                    "id": d["id"],
                    "title": d.get("title"),
                    "created": d.get("created"),
                    "document_type": self.resolve_type_name(d.get("document_type")),
                    "correspondent": self.resolve_correspondent_name(d.get("correspondent")),
                    "tags": self.resolve_tag_names(d.get("tags", [])),
                    "web_url": f"{settings.base_paperless_url}/documents/{d['id']}/details",
                }
                for d in docs
            ]

paperless = PaperlessClient()
