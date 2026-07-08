# Graph-RAG System Diagrams

Tai lieu nay tong hop diagram cho he thong Graph-RAG theo huong:
- LLM dieu phoi (Intent Router + Planner)
- Truy van ket hop Neo4j + Qdrant + Local FT Model + Prediction Agent
- Frontier model tong hop ket qua va tra loi grounded

## 1) Architecture Diagram (Component View)

```mermaid
flowchart LR
    U[User]
    UI[Frontend UI]
    API[FastAPI Gateway]
    ORCH[Orchestrator Layer<br/>Intent Router + Query Planner + Policy]

    GR[Graph Retriever]
    VR[Vector Retriever]
    LM[Local Fine-tuned Model Agent]
    PA[Prediction Agent]

    N4[(Neo4j Graph Store)]
    QD[(Qdrant Vector Store)]

    FUSE[Fusion + Guardrails<br/>Grounding Check + Conflict Resolver]
    RESP[Frontier Response Composer]
    MEM[(Session Memory + Logs)]

    U --> UI --> API --> ORCH
    ORCH --> GR --> N4
    ORCH --> VR --> QD
    ORCH --> LM
    ORCH --> PA

    GR --> FUSE
    VR --> FUSE
    LM --> FUSE
    PA --> FUSE

    FUSE --> RESP --> API --> UI --> U
    API <--> MEM
    ORCH <--> MEM
```

## 2) Activity Diagram (Operational Flow)

```mermaid
flowchart TD
    A([Start]) --> B[User gui cau hoi]
    B --> C[Preprocess + NER + Context load]
    C --> D[Intent Router phan loai intent]
    D --> E{Chon che do thuc thi}

    E -->|Graph only| F1[Query Neo4j]
    E -->|Graph + Vector| F2[Query Neo4j + Qdrant]
    E -->|Graph + FT| F3[Query Neo4j + Local FT]
    E -->|All parallel| F4[Neo4j + Qdrant + Local FT + Prediction]

    F1 --> G[Fusion ket qua]
    F2 --> G
    F3 --> G
    F4 --> G

    G --> H[Grounding check + Score confidence]
    H --> I{Dat nguong tin cay?}
    I -->|Co| J[Compose final answer + evidence]
    I -->|Khong| K[Fallback: tra loi an toan + goi y hoi tiep]
    J --> L{User hoi tiep?}
    K --> L
    L -->|Co| C
    L -->|Khong| M([End])
```

## 3) Sequence Diagram (Runtime Interaction)

```mermaid
sequenceDiagram
    actor User
    participant UI as Frontend
    participant API as FastAPI
    participant Orch as Orchestrator
    participant Neo4j as Graph Retriever/Neo4j
    participant Qdrant as Vector Retriever/Qdrant
    participant FT as Local FT Model
    participant Pred as Prediction Agent
    participant Fuse as Fusion/Guardrails

    User->>UI: Nhap cau hoi
    UI->>API: POST /advise
    API->>Orch: route(question, session)

    Orch->>Orch: intent + query plan + policy
    par Graph branch
        Orch->>Neo4j: Cypher query
        Neo4j-->>Orch: graph evidence
    and Vector branch
        Orch->>Qdrant: semantic search top-k
        Qdrant-->>Orch: vector docs
    and Local model branch
        Orch->>FT: domain generation
        FT-->>Orch: local answer draft
    and Prediction branch
        Orch->>Pred: scoring request
        Pred-->>Orch: prediction result
    end

    Orch->>Fuse: aggregate(all candidates)
    Fuse->>Fuse: grounding + conflict resolve + confidence
    Fuse-->>API: final answer + evidence + confidence
    API-->>UI: JSON response
    UI-->>User: Hien thi ket qua
```

## 4) Use Case Diagram (UC)

```mermaid
flowchart LR
    User[Actor: Nguoi dung]
    Admin[Actor: Quan tri/Chuyen gia]
    Sys[Graph-RAG Career Advisor]

    UC1([Dat cau hoi nghe nghiep])
    UC2([Nhan lo trinh hoc tap ca nhan hoa])
    UC3([So sanh 2 vai tro nghe nghiep])
    UC4([Xem bang chung evidence tu graph/vector])
    UC5([Hoi tiep theo ngu canh cu])

    UC6([Nhap du lieu tu Excel vao Graph/Vector])
    UC7([Quan ly tri thuc Career-Competency-Course])
    UC8([Fine-tune local model])
    UC9([Theo doi log va danh gia chat luong])

    User --> UC1
    User --> UC2
    User --> UC3
    User --> UC4
    User --> UC5

    Admin --> UC6
    Admin --> UC7
    Admin --> UC8
    Admin --> UC9

    Sys --- UC1
    Sys --- UC2
    Sys --- UC3
    Sys --- UC4
    Sys --- UC5
    Sys --- UC6
    Sys --- UC7
    Sys --- UC8
    Sys --- UC9
```

## 5) UC Text Specification (ngan gon)

- UC1 - Dat cau hoi nghe nghiep: User nhap muc tieu, he thong phan tich intent va tra loi.
- UC2 - Nhan lo trinh ca nhan hoa: He thong tong hop roadmap dua tren profile + retrieval.
- UC3 - So sanh vai tro: He thong trich xuat skill-gap giua hai role.
- UC4 - Xem evidence: He thong hien nguon (path graph, tai lieu vector).
- UC5 - Hoi tiep: He thong giu nho context va tiep tuc dong hoi dap.
- UC6 - Nhap du lieu Excel: Admin ETL vao Neo4j + Qdrant.
- UC7 - Quan ly tri thuc: Admin cap nhat quan he Career/Competency/Course.
- UC8 - Fine-tune model: Admin huan luyen local model theo du lieu domain.
- UC9 - Giam sat chat luong: Admin xem log, confidence, ti le fallback.

## 6) PNG Exports (xem truc tiep hinh)

Da render sanh anh PNG tu Mermaid:

- `design/diagrams/architecture.png`
- `design/diagrams/activity.png`
- `design/diagrams/sequence.png`
- `design/diagrams/usecase.png`
