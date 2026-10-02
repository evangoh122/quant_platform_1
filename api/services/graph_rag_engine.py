# Reviewed by DeepSeek: LGTM
from pydantic import BaseModel, Field
from typing import TypedDict, List, Dict
from loguru import logger
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI

from api.db.database import db_manager
from api.config import Config

class GraphRAGState(TypedDict):
    query: str
    ticker: str
    search_entities: List[str]
    extracted_triples: List[Dict[str, str]]
    final_answer: str

def _get_llm() -> ChatOpenAI:
    provider_config = Config.get_provider_config()
    return ChatOpenAI(
        model=provider_config["model"],
        api_key=provider_config["api_key"],
        base_url=provider_config.get("base_url")
    )

class EntitiesOutput(BaseModel):
    entities: List[str] = Field(
        description="1-3 key entity strings to search for in a knowledge graph based on the user query."
    )

def extract_entities(state: GraphRAGState) -> dict:
    """Uses an LLM to identify 1-3 key entity strings from the query."""
    llm = _get_llm()
    query = state["query"]
    
    structured_llm = llm.with_structured_output(EntitiesOutput)
    prompt = f"Given the user query, identify 1-3 key entity strings to search for in a knowledge graph.\nQuery: {query}"
    
    try:
        response = structured_llm.invoke(prompt)
        entities = response.entities[:3] if response.entities else []
    except Exception as e:
        logger.error(f"Failed to parse entities: {e}")
        entities = []
        
    return {"search_entities": entities}

def query_graph(state: GraphRAGState) -> dict:
    """Queries the DuckDB database for graph triples matching the entities."""
    ticker = state["ticker"]
    entities = state.get("search_entities", [])
    extracted_triples = []
    
    if not entities:
        return {"extracted_triples": extracted_triples}
        
    # Build ILIKE conditions dynamically
    conditions = []
    params = [ticker]
    for ent in entities:
        conditions.append("(subject ILIKE ? OR object ILIKE ?)")
        params.extend([f"%{ent}%", f"%{ent}%"])
        
    conditions_sql = " OR ".join(conditions)
    # Phase C: carry the source refs (chunk_id/source_file/source_loc) and node
    # types so the Evidence Graph can show *where in the filing* each edge came
    # from. COALESCE keeps legacy rows (pre-Phase-B, untyped/no chunk_id) valid.
    # LIMIT prevents runaway queries when LLM extracts broad entities like "%".
    sql = f"""
        SELECT ticker, subject, predicate, object,
               COALESCE(subject_type, '') AS subject_type,
               COALESCE(object_type, '')  AS object_type,
               COALESCE(chunk_id, '')     AS chunk_id,
               COALESCE(source_file, '')  AS source_file,
               COALESCE(source_loc, '')   AS source_loc,
               COALESCE(confidence, 1.0)  AS confidence
        FROM graph_triples
        WHERE ticker = ? AND ({conditions_sql})
        ORDER BY confidence DESC NULLS LAST
        LIMIT 500
    """

    try:
        cursor = db_manager.execute(sql, params)
        rows = cursor.fetchall()
        for row in rows:
            extracted_triples.append({
                "subject": row[1],
                "predicate": row[2],
                "object": row[3],
                "subject_type": row[4],
                "object_type": row[5],
                "chunk_id": row[6],
                "source_file": row[7],
                "source_loc": row[8],
                "confidence": row[9],
            })
    except Exception as e:
        logger.error(f"Error querying graph DB: {e}")
        
    return {"extracted_triples": extracted_triples}

def generate_answer(state: GraphRAGState) -> dict:
    """Uses an LLM to synthesize the final answer based on the extracted triples."""
    llm = _get_llm()
    query = state["query"]
    ticker = state["ticker"]
    triples = state.get("extracted_triples", [])
    
    if not triples:
        triples_str = "No relevant knowledge graph data found."
    else:
        triples_str = "\n".join([f"- {t['subject']} -> {t['predicate']} -> {t['object']}" for t in triples])
    
    prompt = f"""
    Answer the user's question based on the extracted knowledge graph triples for the company ticker {ticker}.
    If the extracted triples do not contain the answer, state that you don't have enough information.
    
    Query: {query}
    
    Extracted Triples:
    {triples_str}
    
    Final Answer:
    """
    
    response = llm.invoke(prompt)
    return {"final_answer": response.content}

def run_graph_rag(query: str, ticker: str) -> dict:
    """Compiles and invokes the GraphRAG workflow, returning the final state."""
    workflow = StateGraph(GraphRAGState)
    
    workflow.add_node("extract_entities", extract_entities)
    workflow.add_node("query_graph", query_graph)
    workflow.add_node("generate_answer", generate_answer)
    
    workflow.add_edge(START, "extract_entities")
    workflow.add_edge("extract_entities", "query_graph")
    workflow.add_edge("query_graph", "generate_answer")
    workflow.add_edge("generate_answer", END)
    
    app = workflow.compile()
    
    initial_state = {
        "query": query,
        "ticker": ticker,
        "search_entities": [],
        "extracted_triples": [],
        "final_answer": ""
    }
    
    # Invoke the graph
    result = app.invoke(initial_state)
    return result
