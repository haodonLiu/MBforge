"""Agent tool definitions for the LangGraph ReAct agent.

Each tool wraps an MBForge capability as a callable function. Tools receive the
active ``library_root`` through LangGraph's ``configurable`` mechanism
(``config["configurable"]["library_root"]``), so they operate on the user's
actual library instead of an empty default.
"""

from __future__ import annotations

import asyncio
import json

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from ..utils.logger import get_logger

logger = get_logger(__name__)


def _get_library_root(config: RunnableConfig | None) -> str:
    """Extract ``library_root`` from the LangGraph ``configurable`` block."""
    if not config:
        return ""
    configurable = config.get("configurable") or {}
    root = configurable.get("library_root", "")
    return str(root) if root else ""


@tool
async def kb_search(query: str, config: RunnableConfig, top_k: int = 5) -> str:
    """Search the knowledge base for relevant document chunks.

    Args:
        query: Search query (natural language or keywords)
        top_k: Number of results to return (default 5)

    Returns:
        JSON string with search results including text snippets and metadata.
    """
    from ..core.knowledge_base import search

    library_root = _get_library_root(config)
    if not library_root:
        return json.dumps({"error": "library_root not configured"}, ensure_ascii=False)

    try:
        result = await asyncio.to_thread(
            search, query, library_root, top_k=top_k, use_cache=False
        )
        results = result.get("results", [])
        return json.dumps(results[:top_k], ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("kb_search failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
async def molecule_search(query: str, config: RunnableConfig) -> str:
    """Search for molecules by name, SMILES, or text description.

    Args:
        query: Search query

    Returns:
        JSON string with matching molecules.
    """
    from ..models.molecule import MoleculeSearchRequest
    from ..routers.molecule import mol_search

    library_root = _get_library_root(config)
    if not library_root:
        return json.dumps({"error": "library_root not configured"}, ensure_ascii=False)

    try:
        request = MoleculeSearchRequest(library_root=library_root, query=query, top_k=10)
        result = await mol_search(request)
        return json.dumps(result.get("results", []), ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("molecule_search failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
async def get_document_content(
    doc_id: str, config: RunnableConfig, pages: str = ""
) -> str:
    """Get the text content of a document's pages.

    Args:
        doc_id: Document identifier
        pages: Comma-separated page numbers (empty = all pages)

    Returns:
        JSON string with page text content.
    """
    from ..core.knowledge_base import get_document_pages

    library_root = _get_library_root(config)
    if not library_root:
        return json.dumps({"error": "library_root not configured"}, ensure_ascii=False)

    try:
        page_list = (
            [int(p.strip()) for p in pages.split(",") if p.strip()] if pages else None
        )
        result = await asyncio.to_thread(
            get_document_pages, library_root, doc_id, page_list
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("get_document_content failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _compute_molecule_properties_sync(smiles: str) -> str:
    """Compute molecular properties from a SMILES string (sync)."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return json.dumps({"error": f"Invalid SMILES: {smiles}"}, ensure_ascii=False)
        return json.dumps(
            {
                "molecular_weight": round(Descriptors.MolWt(mol), 2),
                "logp": round(Descriptors.MolLogP(mol), 2),
                "hbd": rdMolDescriptors.CalcNumHBD(mol),
                "hba": rdMolDescriptors.CalcNumHBA(mol),
                "tpsa": round(Descriptors.TPSA(mol), 2),
                "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol),
                "formula": rdMolDescriptors.CalcMolFormula(mol),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
async def compute_molecule_properties(smiles: str) -> str:
    """Compute molecular properties from a SMILES string.

    Args:
        smiles: SMILES notation of the molecule

    Returns:
        JSON string with computed properties (MW, LogP, HBD, HBA, TPSA, etc.).
    """
    return await asyncio.to_thread(_compute_molecule_properties_sync, smiles)


@tool
async def list_project_documents(config: RunnableConfig) -> str:
    """List all documents in the current project.

    Returns:
        JSON string with document list.
    """
    from ..core.library import LibraryStore

    library_root = _get_library_root(config)
    if not library_root:
        return json.dumps({"error": "library_root not configured"}, ensure_ascii=False)

    try:
        store = LibraryStore.get(library_root)
        docs = await asyncio.to_thread(store.list_documents)
        payload = [
            {"doc_id": d.doc_id, "title": d.title, "status": d.status} for d in docs
        ]
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("list_project_documents failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def get_all_tools() -> list:
    """Return all available tools for the agent."""
    return [
        kb_search,
        molecule_search,
        get_document_content,
        compute_molecule_properties,
        list_project_documents,
    ]
