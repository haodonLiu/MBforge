"""Agent tool definitions for the LangGraph ReAct agent.

Each tool wraps an MBForge capability as a callable function.
"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from ..utils.logger import get_logger

logger = get_logger("mbforge.agent.tools")


@tool
def kb_search(query: str, top_k: int = 5) -> str:
    """Search the knowledge base for relevant document chunks.

    Args:
        query: Search query (natural language or keywords)
        top_k: Number of results to return (default 5)

    Returns:
        JSON string with search results including text snippets and metadata.
    """
    try:
        from ..core.knowledge_base import search

        result = search(query, library_root="", top_k=top_k, use_cache=False)
        results = result.get("results", [])
        return json.dumps(results[:top_k], ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def molecule_search(query: str) -> str:
    """Search for molecules by name, SMILES, or text description.

    Args:
        query: Search query

    Returns:
        JSON string with matching molecules.
    """
    try:
        # Synchronous wrapper
        import asyncio

        from ..routers.molecule import mol_search

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(mol_search({"query": query, "library_root": "", "top_k": 10}))
        loop.close()
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_document_content(doc_id: str, pages: str = "") -> str:
    """Get the text content of a document's pages.

    Args:
        doc_id: Document identifier
        pages: Comma-separated page numbers (empty = all pages)

    Returns:
        JSON string with page text content.
    """
    try:
        page_list = [int(p.strip()) for p in pages.split(",") if p.strip()] if pages else None
        from ..core.knowledge_base import get_document_pages

        result = get_document_pages(library_root="", doc_id=doc_id, pages=page_list)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def compute_molecule_properties(smiles: str) -> str:
    """Compute molecular properties from a SMILES string.

    Args:
        smiles: SMILES notation of the molecule

    Returns:
        JSON string with computed properties (MW, LogP, HBD, HBA, TPSA, etc.).
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return json.dumps({"error": f"Invalid SMILES: {smiles}"})
        return json.dumps({
            "molecular_weight": round(Descriptors.MolWt(mol), 2),
            "logp": round(Descriptors.MolLogP(mol), 2),
            "hbd": rdMolDescriptors.CalcNumHBD(mol),
            "hba": rdMolDescriptors.CalcNumHBA(mol),
            "tpsa": round(Descriptors.TPSA(mol), 2),
            "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol),
            "formula": rdMolDescriptors.CalcMolFormula(mol),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def list_project_documents() -> str:
    """List all documents in the current project.

    Returns:
        JSON string with document list.
    """
    try:

        # This needs library_root from session — will be injected
        return json.dumps({"message": "Use the session's library_root to list documents"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_all_tools() -> list:
    """Return all available tools for the agent."""
    return [
        kb_search,
        molecule_search,
        get_document_content,
        compute_molecule_properties,
        list_project_documents,
    ]
