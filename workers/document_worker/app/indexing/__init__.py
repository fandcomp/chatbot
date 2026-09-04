"""M6: Voyage contextual embedding, sparse vectors, and Qdrant population.

Never re-chunks — reads M5's already-persisted `document_chunks` (plus their
anchor `document_nodes`/`document_regions` rows) and produces Qdrant points.
Query-time embedding/hybrid retrieval/reranking are M7/M8, not here.
"""
