import sys
import os
from pathlib import Path

# Configuração de PATH para enxergar o código da pasta src do projeto mãe
# Sem isso, não conseguiríamos importar 'rag_project' daqui de dentro.
src_path = Path(__file__).resolve().parent.parent / "src"
sys.path.append(str(src_path))

# Agora podemos importar do sistema que já está robusto
from rag_project.config import build_config
from rag_project.db.connection import Database
from rag_project.db.repositories import RagRepository
from rag_project.embeddings.factory import build_embedder
from rag_project.retrieval.hybrid import HybridRetriever

# Importações do LlamaIndex
from llama_index.core import Document
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.llms.ollama import Ollama


class HierarchicalRagRetriever(BaseRetriever):
    """
    Um Retriever Personalizado (Custom Retriever) do LlamaIndex que atua como
    uma ponte (wrapper) para a sua estrutura robusta de busca híbrida.
    Dessa forma, o LlamaIndex usa o seu banco PGVector + Hierarquia de forma transparente!
    """
    def __init__(self, hybrid_retriever: HybridRetriever, collection: str):
        self.hybrid_retriever = hybrid_retriever
        self.collection = collection
        super().__init__()

    def _retrieve(self, query_bundle):
        # 1. Fazemos a busca através da sua implementação com Reciprocal Rank Fusion
        trace = self.hybrid_retriever.search(self.collection, query_bundle.query_str)
        
        nodes = []
        # 2. Iteramos nos hits fundidos e convertemos para Nodes do LlamaIndex
        # (O LlamaIndex usa esse formato NodeWithScore para compor o contexto)
        for hit in trace.fused_hits:
            doc = Document(
                text=hit.text,
                metadata={
                    "canonical_url": hit.canonical_url,
                    "section_id": hit.section_id,
                    **hit.metadata
                }
            )
            # O LlamaIndex usa pontuações ou 1.0 por padrão caso seja indefinido
            node = NodeWithScore(node=doc, score=hit.score or 1.0)
            nodes.append(node)
            
        return nodes


def main():
    print("=======================================================")
    print("Iniciando Chatbot RAG no Terminal (LlamaIndex + Ollama)")
    print("=======================================================")
    print("\nConectando ao banco de dados e embedder original...")
    
    # 1. Inicializa dependências globais do seu projeto original RAG
    # Usamos collection default como ansys-fluent (altere conforme a coleção no pgvector)
    TARGET_COLLECTION = os.getenv("RAG_COLLECTION", "ansys-fluent")
    
    # Preenchemos a URL temporária só pra o build_config gerar um config local
    config = build_config(root_url="http://localhost")
    
    try:
        database = Database(config.database_dsn)
        repository = RagRepository(database)
        # O embedder original vai usar os pesos do huggingface ou o que estiver no RAG
        embedder = build_embedder(config.embeddings)
    except Exception as e:
        print(f"\n[ERRO] Falha ao inicializar o banco original ou embedder: {e}")
        return

    # Instanciamos o Hybrid Retriever original do seu sistema
    hybrid_retriever = HybridRetriever(repository, embedder, config.retrieval)
    
    # Criamos a ponte com LlamaIndex
    llama_retriever = HierarchicalRagRetriever(hybrid_retriever, collection=TARGET_COLLECTION)
    
    # 2. Inicializar Ollama
    print("Inicializando modelo de linguagem (Ollama) local...")
    # O timeout de 120 é generoso caso seja a primeira vez q o modelo roda local e engasgue
    llm = Ollama(model="gemma:7b", request_timeout=120.0)
    
    # 3. Criar Query Engine com LlamaIndex 
    query_engine = RetrieverQueryEngine.from_args(
        retriever=llama_retriever,
        llm=llm,
    )
    
    # Usamos o CondenseQuestion que lembra do histórico da conversa 
    from llama_index.core.chat_engine import CondenseQuestionChatEngine
    
    chat_engine = CondenseQuestionChatEngine.from_defaults(
        query_engine=query_engine, 
        llm=llm,
        verbose=True
    )
    
    print("\n[SUCESSO] Memória carregada com seu sistema original!")
    print("Digite sua pergunta. Digite 'exit', 'quit' ou 'sair' para encerrar.\n")
    
    # Abre o REPL (Terminal Loop) nativo e bonito do LlamaIndex
    chat_engine.chat_repl()


if __name__ == "__main__":
    main()
