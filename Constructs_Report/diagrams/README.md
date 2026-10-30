# Diagram sources

Each figure in the report, its editable source and its rendered image.

Regenerate PlantUML diagrams with `java -jar plantuml.jar -tpng -o ../png src/*.puml` (PlantUML 1.2024.7, Smetana layout, shared style in `src/_style.iuml`). Regenerate the concept diagram with `python src/00_concept.py` (matplotlib).

| Figure | Caption | Source | Image |
| --- | --- | --- | --- |
| 1.1 | Design-to-execution mechanisms implemented in Constructs | `src/00_concept.py` | `png/00_concept.png` |
| 3.1 | System context of Constructs | `src/01_context.puml` | `png/01_context.png` |
| 3.2 | Use cases - project execution and collaboration | `src/02a_usecase_project.puml` | `png/02a_usecase_project.png` |
| 3.3 | Use cases - engineering information, AI assistance and administration | `src/02b_usecase_intelligence.puml` | `png/02b_usecase_intelligence.png` |
| 3.4 | Activity diagram - task execution and review | `src/03_activity_task_review.puml` | `png/03_activity_task_review.png` |
| 3.5 | State machine - task status | `src/09_state_task.puml` | `png/09_state_task.png` |
| 3.6 | State machine - IFC model version processing status | `src/10_state_ifc.puml` | `png/10_state_ifc.png` |
| 3.7 | State machine - ingested file status (PARTIAL is a usable outcome with reduced capability) | `src/11_state_ingestion.puml` | `png/11_state_ingestion.png` |
| 4.1 | High-level architecture | `src/13_architecture.puml` | `png/13_architecture.png` |
| 4.2 | Backend component diagram | `src/14_components.puml` | `png/14_components.png` |
| 4.3 | Deployment diagram (Docker Compose) | `src/15_deployment.puml` | `png/15_deployment.png` |
| 4.4 | ER diagram - identity, organisation and RBAC | `src/16a_er_identity.puml` | `png/16a_er_identity.png` |
| 4.5 | ER diagram - projects, parties, tasks and field records | `src/16b_er_projects.puml` | `png/16b_er_projects.png` |
| 4.6 | ER diagram - documents, ingestion, retrieval chunks and jobs | `src/16c_er_documents.puml` | `png/16c_er_documents.png` |
| 4.7 | ER diagram - IFC model groups, versions, elements and analysis results | `src/16d_er_ifc.puml` | `png/16d_er_ifc.png` |
| 4.8 | Activity diagram - effective permission resolution | `src/19_activity_authz.puml` | `png/19_activity_authz.png` |
| 4.9 | Sequence diagram - login, authorised request and token refresh | `src/05_seq_auth.puml` | `png/05_seq_auth.png` |
| 4.10 | Sequence diagram - durable background job processing | `src/08_seq_jobs.puml` | `png/08_seq_jobs.png` |
| 4.11 | Level-1 data flow diagram - file ingestion and document question answering | `src/18_dfd_ingestion.puml` | `png/18_dfd_ingestion.png` |
| 4.12 | Activity diagram - IFC upload, processing and coordination | `src/04_activity_ifc.puml` | `png/04_activity_ifc.png` |
| 4.13 | Activity diagram - revision comparison and impact suggestions | `src/21_revision_impact.puml` | `png/21_revision_impact.png` |
| 4.14 | Sequence diagram - retrieval-augmented document question answering | `src/06_seq_rag.puml` | `png/06_seq_rag.png` |
| 4.15 | Sequence diagram - voice command to confirmed action | `src/07_seq_voice.puml` | `png/07_seq_voice.png` |
| 4.16 | Sequence diagram - notification, realtime and push fan-out | `src/20_seq_notify.puml` | `png/20_seq_notify.png` |
| 5.1 | Class diagram - retrieval and answering services | `src/17_class_rag.puml` | `png/17_class_rag.png` |
