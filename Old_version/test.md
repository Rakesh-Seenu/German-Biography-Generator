```mermaid
sequenceDiagram
    actor User
    participant StreamlitApp
    participant FileProcessor
    participant VectorStore
    participant OpenAIModel

    User ->> StreamlitApp: Upload PDF Files & Enter API Key
    StreamlitApp ->> FileProcessor: Process Uploaded PDFs
    FileProcessor -->> StreamlitApp: Extracted Documents
    StreamlitApp ->> VectorStore: Create Vector Store with Embeddings
    VectorStore -->> StreamlitApp: Vector Store Created

    User ->> StreamlitApp: Ask Question Based on PDF Content
    StreamlitApp ->> VectorStore: Retrieve Relevant Documents
    VectorStore -->> StreamlitApp: Retrieved Documents
    StreamlitApp ->> OpenAIModel: Query LLM with Context
    OpenAIModel -->> StreamlitApp: LLM Response
    StreamlitApp -->> User: Display Answer
