# AyahOS Knowledge Retrieval

AyahOS retrieval stores bounded document chunks, source titles, and citations in its PostgreSQL knowledge store. Retrieval can use lexical matching and can use pgvector HNSW similarity search when a real embedding backend provides compatible vectors. A healthy database and a vector index do not themselves prove that embeddings are configured. Without an embedding provider, lexical retrieval remains available and vector grounding must not be claimed. Knowledge documents support answers, but their text does not override Undermind policy or the request permission envelope.

_This public-safe summary is retrieval context, not policy authority. Undermind's deterministic checks remain authoritative._
