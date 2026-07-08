from pyvis.network import Network


def build_demo_graph() -> Network:
    net = Network(height="820px", width="100%", bgcolor="#ffffff", font_color="#222222", directed=True)
    net.barnes_hut()

    # Core student profile nodes
    net.add_node("student", label="Sinh vien", color="#ef5da8", size=45, title="Nguoi dung chatbot")
    net.add_node("goal_backend", label="Muc tieu: Backend Developer", color="#4c78ff", size=32)
    net.add_node("goal_data", label="Muc tieu: Data Engineer", color="#1fa971", size=28)

    # Skills
    skills = {
        "python": ("Python", "#6cc24a"),
        "sql": ("SQL", "#6cc24a"),
        "api": ("REST API", "#6cc24a"),
        "docker": ("Docker", "#6cc24a"),
        "git": ("Git", "#6cc24a"),
        "dsa": ("DSA", "#6cc24a"),
        "etl": ("ETL", "#6cc24a"),
        "spark": ("Spark", "#6cc24a"),
    }
    for key, (label, color) in skills.items():
        net.add_node(key, label=label, color=color, size=18)

    # Roadmaps and resources
    net.add_node("roadmap_backend", label="Roadmap Backend 6 thang", color="#f39c3d", size=24)
    net.add_node("roadmap_data", label="Roadmap Data 6 thang", color="#f39c3d", size=24)

    resources = {
        "fastapi_docs": "FastAPI Docs",
        "sql_practice": "SQL Practice",
        "docker_course": "Docker Course",
        "system_design": "System Design Basics",
        "airflow_intro": "Airflow Intro",
        "spark_guide": "Spark Guide",
    }
    for key, label in resources.items():
        net.add_node(key, label=label, color="#8f63d8", size=15)

    # Vector docs (Qdrant chunks)
    vector_docs = [
        "doc_chunk_1",
        "doc_chunk_2",
        "doc_chunk_3",
        "doc_chunk_4",
        "doc_chunk_5",
    ]
    for idx, key in enumerate(vector_docs, start=1):
        net.add_node(key, label=f"Chunk {idx}", color="#7f8c8d", size=12)

    # Edges - student to goals
    net.add_edge("student", "goal_backend", label="muon theo")
    net.add_edge("student", "goal_data", label="co the theo")

    # Role -> required skills
    for s in ["python", "sql", "api", "docker", "git", "dsa"]:
        net.add_edge("goal_backend", s, label="REQUIRES")
    for s in ["python", "sql", "etl", "spark", "git"]:
        net.add_edge("goal_data", s, label="REQUIRES")

    # Role -> roadmap
    net.add_edge("goal_backend", "roadmap_backend", label="HAS_ROADMAP")
    net.add_edge("goal_data", "roadmap_data", label="HAS_ROADMAP")

    # Roadmap -> resource
    net.add_edge("roadmap_backend", "fastapi_docs", label="USES")
    net.add_edge("roadmap_backend", "sql_practice", label="USES")
    net.add_edge("roadmap_backend", "docker_course", label="USES")
    net.add_edge("roadmap_backend", "system_design", label="USES")

    net.add_edge("roadmap_data", "sql_practice", label="USES")
    net.add_edge("roadmap_data", "airflow_intro", label="USES")
    net.add_edge("roadmap_data", "spark_guide", label="USES")

    # Qdrant-like semantic links
    net.add_edge("student", "doc_chunk_1", label="query_similar")
    net.add_edge("student", "doc_chunk_2", label="query_similar")
    net.add_edge("student", "doc_chunk_3", label="query_similar")
    net.add_edge("doc_chunk_1", "roadmap_backend", label="supports")
    net.add_edge("doc_chunk_2", "roadmap_data", label="supports")
    net.add_edge("doc_chunk_3", "python", label="mentions")
    net.add_edge("doc_chunk_4", "sql", label="mentions")
    net.add_edge("doc_chunk_5", "docker", label="mentions")

    return net


def main() -> None:
    net = build_demo_graph()
    net.show("graph_rag_network.html", notebook=False)
    print("Generated: graph_rag_network.html")


if __name__ == "__main__":
    main()
