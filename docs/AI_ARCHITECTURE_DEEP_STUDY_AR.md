# دراسة طبقة الذكاء الاصطناعي في StructIQ / Smart Construction Platform

تاريخ الدراسة: 30 أكتوبر 2026  
النطاق: الكود الحالي، الاختبارات الموجودة، ورقتا RAPTOR وGraphRAG الأصليتان، وتجربة اصطناعية معزولة بلا شبكة أو بيانات خاصة.

## 1. الحكم المختصر

المشروع لا يحتاج الآن إلى استبدال طبقة الذكاء الاصطناعي بـRAPTOR أو GraphRAG الكامل. ما يحتاجه أولًا هو **إكمال سلسلة الأدلة الحالية وتحويلها من سؤال/جواب ومنبّهات منفردة إلى تحليل قضايا متعدد المصادر وقابل للتحقق**.

التوصية الرئيسية هي:

1. الاحتفاظ بـPostgreSQL وpgvector وطابور الوظائف وطبقة الصلاحيات وIFC الحتمية و`AIInsight`/`AIInsightSource`.
2. إصلاح التغطية قبل تغيير المعمارية: OCR، استخراج الجداول والقيم، إدخال المراسلات والرسائل في corpus، بحث هجين lexical+dense، reranking، وقياس كامل للاستدعاءات والتكلفة.
3. إضافة طبقة **Evidence Cases**: قضية مستمرة مثل “تأخر واجهات” أو “تعارض درجة خرسانة” تجمع الأدلة المنظمة والنصية عبر الزمن، تحفظ كل claim ومصدره وإصداره، وتُبطل عند تغير أي مصدر أو صلاحية.
4. استخدام علاقات النظام المؤكدة (`task_id`، dependencies، design changes، IFC links، project/discipline، source versions) لتوسيع الأدلة. لا نستخرج هذه العلاقات مجددًا بـLLM.
5. السماح بتلخيص محدود داخل القضية أو داخل وثيقة طويلة فقط، وبروابط إلى المقاطع الأصلية. لا نبني شجرة RAPTOR شاملة ولا knowledge graph مستخرجًا بالكامل بـLLM قبل أن يثبت benchmark أن ذلك يحسن حالتي الاستخدام الأساسيتين.

هذا التصميم هو **تحسين للنظام الحالي مع graph-assisted evidence traversal محدود**، وليس GraphRAG كما في الورقة. لا يحتاج قاعدة graph جديدة؛ PostgreSQL الحالي يكفي في المرحلة المقترحة.

سبب القرار: البنية الحالية قوية في الحوكمة والعلاقات المنظمة لكنها ناقصة في التغطية والاسترجاع والتقييم. GraphRAG الكامل سيعيد استخراج علاقات موجودة، يضيف كلفة فهرسة وتحديث وتسرب صلاحيات محتمل عبر community summaries، بينما RAPTOR يحسن سياق الوثائق الطويلة لكنه لا يحل وحده الربط بين task وIFC وsite report وdesign change. التجربة الصغيرة لم تُظهر فائدة جودة لأي توسعة graph؛ لذلك لا يوجد مبرر تجريبي الآن لتعقيد أوسع.

## 2. منهج الفحص ودرجة الثقة

استخدمت أربع درجات:

- **موجود ومؤكد من الكود والاختبارات**: مسار تنفيذي واختبارات ذات صلة موجودان. تعذر تشغيل مجموعة الاختبارات كاملة في هذه البيئة، لذلك لا يعني هذا تحققًا production end-to-end.
- **موجود جزئيًا**: توجد بنية أو جزء من التدفق لكن النتيجة المطلوبة ليست مكتملة.
- **موصوف فقط**: تذكره وثيقة، ولا يوجد تنفيذ مطابق، أو الوثيقة أقدم من الكود.
- **غير معروف**: يحتاج بيانات تشغيل أو سجلات أو قياسًا غير متاح.

قيود التحقق المحلي:

- Docker Desktop لم يكن يعمل، لذلك لم أشغّل PostgreSQL/pgvector ولا اختبارات التكامل.
- تشغيل pytest من سياق backend وصل إلى نقص حزمة `pgvector` في Python المحلي قبل جمع الاختبارات. لم أثبت حزمًا ولم أغيّر البيئة.
- لم أشغّل API مدفوعًا ولم أرسل بيانات إلى مزود خارجي.
- المستودع كان يحتوي مسبقًا على تغييرات كثيرة غير ملتزمة؛ لم ألمسها. الإضافات الوحيدة لهذه الدراسة هي هذا التقرير ومجلد `research/ai_architecture_study/`.

## 3. طبقة AI الحالية كما ينفذها الكود

### 3.1 استقبال الملفات، الاستخراج، OCR، التقسيم والفهرسة

| القدرة | الحالة | الدليل من الكود | الحكم |
|---|---|---|---|
| تسجيل الملف والتخزين الخاص والتصنيف والتحقق من التكرار | موجود | `backend/app/services/ingestion/pipeline.py`: `register_upload`, `_classify_stored`, `_mark_duplicate`, `queue`, `run` | مسار موحد بحالات وأخطاء ووظيفة خلفية. |
| PDF ذو text layer | موجود | `ingestion/processors/pdf.py:PDFProcessor`; `rag/pdf_text.py:extract_pages`; `rag/text_source.py:_pdf_pages` | يحفظ page number الحقيقي ويعيد قراءة النص الكامل وقت الفهرسة. |
| PDF ممسوح ضوئيًا | غير موجود | `rag/pdf_text.py:extract_pages` يعيد خطأ “no extractable text layer”; `file_intelligence.py` يصرح أن OCR غير مدعوم | هذه فجوة مؤكدة، لا خطأ RAG. |
| DOCX | موجود جزئيًا | `ingestion/processors/office.py:DocxProcessor`; `rag/text_source.py:pages_for` | يقرأ body XML؛ الجداول تُسطّح كنص، ولا يقرأ headers/footers/footnotes/tracked changes. كل الملف page 1، فتضعف دقة المرجع. |
| XLSX | موجود كـmetadata فقط | `office.py:XlsxProcessor` | أسماء الأوراق فقط؛ لا قيم خلايا ولا جداول، وبالتالي لا تحليل BOQ/schedule spreadsheet حقيقي. |
| TXT | موجود | `ingestion/processors/misc.py:TextProcessor`; `rag/text_source.py` | قابل للفهرسة كصفحة واحدة. |
| IFC | موجود في محرك متخصص | `ingestion/processors/ifc.py` يفوض إلى IFC workspace | لا يحوله إلى نص RAG، وهذا صحيح لأن حقائقه منظمة. |
| التقسيم | موجود | `rag/chunking.py:chunk_page/chunk_pages`؛ defaults في `core/config.py` | 500 token مع overlap 75، ولا يتجاوز chunk صفحة PDF. لا توجد semantic/section-aware chunks. |
| embedding والتخزين | موجود | `rag/embeddings.py:EmbeddingService`، batches=64؛ `models/document_chunk.py`؛ `rag/store.py:PgVectorStore` | `text-embedding-3-small` وvector(1536) افتراضيًا، HNSW cosine. |
| الفهرسة التلقائية | موجود لكن feature-gated | `core/config.py:RAG_ENABLED=false`, `RAG_AUTO_INDEX_ENABLED=true`; `rag/ingestion.py:should_auto_index*`; `api/documents.py` | RAG كله مغلق افتراضيًا. عند تفعيله، الملفات المؤهلة تُصفّ في background. |

ملاحظة drift مهمة: `file_intelligence.py` ما زال يصف DOCX/TEXT بأنهما غير موصولين بالفهرسة، بينما `rag/text_source.py` يدعمهما فعليًا. الوثيقة/جدول القدرات هنا أقدم من التنفيذ؛ يجب توليد capability status من registry واحد بدل نسختين متعارضتين.

### 3.2 Retrieval، reranking، الإجابات والمراجع

التدفق الفعلي:

`api/rag.py:query_documents` أو `api/knowledge.py:_answer_documents`  
→ يحسب IDs المسموحة عبر `document_access.py`  
→ `rag/retrieval.py:retrieve` ينشئ embedding للسؤال  
→ `rag/store.py:PgVectorStore.search` ينفذ cosine top-k داخل project وداخل مجموعتي IDs الصريحتين  
→ `rag/answering.py:AnswerService.answer` يولد إجابة من المقاطع.

الحالة التفصيلية:

- **Dense retrieval موجود**: `RAG_TOP_K=5`، HNSW، و`hnsw.iterative_scan=strict_order` لتقليل فقد النتائج بعد filtering.
- **لا lexical/BM25/tsvector ولا hybrid search**: مؤكد من `rag/store.py` ومن قسم القيود في `docs/RAG.md`.
- **لا reranker**: ترتيب cosine يذهب مباشرة إلى نموذج الإجابة.
- **لا threshold جودة**: إذا أعاد top-k مقاطع بعيدة، تدخل كلها إلى السياق؛ `found` يصبح false تلقائيًا فقط عند عدم وجود chunks أو عندما يعيد النموذج sentinel.
- **routing حتمي جيد**: `knowledge_router.py:route_question` يوجه progress/tasks/IFC إلى البيانات المنظمة بدل إجبار كل سؤال على vector search.
- **المراجع ذات provenance صحيح ولكن support غير مثبت**: `_citations_from` يبني المراجع من كل المقاطع المسترجعة، وليس من markers التي استخدمها النموذج. هذا يمنع اختراع صفحة غير مسترجعة، لكنه قد يعرض مقطعًا لم يدعم claim، ولا يتحقق أن كل claim في النص يحمل marker صحيحًا.
- **لا claim-level verification**: لا parser للادعاءات ولا entailment/contradiction check ولا mapping من الجملة إلى chunk.
- **اللغة**: prompts إنجليزية، ورسالة not-found إنجليزية. embedding قد يخدم العربية نظريًا، لكن لا benchmark عربي/إنجليزي مختلط في المشروع. لا يجوز اعتبار دعم النموذج العام دليلًا على المصطلحات الهندسية الفلسطينية/العربية.

### 3.3 IFC، الإصدارات، المقارنة والربط

هذه أقوى طبقة تحليلية في المشروع ولا ينبغي استبدالها بتلخيص لغوي:

- `ifc_processing_service.py:parse_with_timeout` يشغل parsing في child process مع timeout وحد ذاكرة؛ `process_version` يبني hierarchy/elements/properties/quantities.
- `ifc_parser.py:IFCParser` يستخرج GlobalId، placement/geometry hashes، psets، quantities، materials، systems، disciplines، georeferencing، units، completeness.
- `ifc_processing_service.py:compare_versions` يطابق بالإصدار عبر GlobalId ويحسب added/removed/modified/moved وproperty/quantity/location/geometry deltas.
- `IFCEntityLink` يربط element/spatial node بكيان مشروع. `_build_impacts` يعطي link مؤكد confidence=1 أو اقتراح discipline-based confidence=.65.
- `ifc_knowledge.py:answer_ifc_question` يستعلم structured facts مباشرة، بدل embedding أسماء العناصر.
- `ifc_interference.py` و`run_interference_analysis` ينتجان finding هندسيًا احتماليًا مع geometry evidence وconfidence، لا يدعيان clash هندسيًا حتميًا من bounding boxes.

الحد الحالي: Revision Impact Agent يقرأ counts والتغييرات والروابط، لكنه لا يجمع نصوص المواصفات والمراسلات وتقارير الموقع مع change records في تحليل واحد. المقارنة نفسها تحمل جميع عناصر الإصدار في dicts داخل الذاكرة (`compare_versions`)، ما قد يصبح اختناقًا محتملًا في نماذج كبيرة ويحتاج benchmark.

### 3.4 الأدوات والـagents

`services/ai_tools/registry.py` و`runtime.py:call_tool` يطبقان validation ثم project access ثم permission قبل handler. كل agent لديه grant ضيق في `services/agents/registry.py`.

الـagents الخمسة في `services/agents/analyzers.py` **قواعد حتمية وليست LLM agents**:

- Site Report: كلمات delay، نقص التفاصيل، تكرار phrase، اختلاف progress.
- Document Consistency: اختلاف نوع التصنيف، عدم الفهرسة، واسترجاع requirements فقط. يصرح صراحة أن contradiction detection غير منفذ.
- Revision Impact: findings في IFC، declared schedule impacts، وtask links.
- RFI: يقرأ `DesignChange` لأن النظام لا يملك RFI entity.
- Schedule Risk: overdue/stalled/blocked/undated، ويقرأ نتائج Site Report Agent عبر tool.

حدود حجم مؤكدة في التحليل: `search_documents(limit=100)`, `get_tasks(limit=200)`, `get_findings(limit=50)`, وأحيانًا site reports=15. هذه caps معقولة لحماية الطلب، لكنها تعني أن “تحليل المشروع كله” غير متحقق عندما يتجاوز المشروع تلك الحدود.

`agents/runtime.py:run_agent` يسجل duration/tool calls ويحدّث finding بالبصمة بدل التكرار. `orchestrator.py` يعزل فشل كل agent. لا توجد كتابة تلقائية للمشروع؛ promotion إلى issue/task قرار بشري.

### 3.5 الأحداث، background jobs، التحديث والإبطال

- `domain_event_dispatcher.py:IMPORTANT_EVENTS` يغطي tasks/issues/design changes/field submissions/IFC/documents، لكن الرسائل العادية ليست ضمن هذه dispatcher.
- `emit_domain_event` يسجل event ويطبق قواعد حتمية؛ auto-agent analysis يوضع في queue فقط عند `AGENT_AUTO_ANALYSIS_ENABLED=true` (افتراضيًا false).
- `services/jobs/queue.py` يستخدم PostgreSQL row queue مع active dedupe index، claim، heartbeat، retry exponential، وreap.
- Compose يفصل API عن worker، لكن `JobRunner.concurrency` مربوط بـ`IFC_MAX_CONCURRENT_PROCESSING` حتى لكل أنواع jobs. هذا اختناق/اقتران محتمل: IFC ثقيل وRAG/agents يتشاركون ceiling واحدًا من دون per-kind queues أو priorities.
- RAG reindex يستبدل chunks داخل transaction ويكتشف embedding model/dimension stale. `maintenance.py:recover_stale_jobs` يعالج runs العالقة.
- حذف `Document` يحذف chunks عبر FK cascade. لا يوجد endpoint حذف واضح لـ`IngestedFile` في `api/ingestion.py` ضمن المسار المفحوص.
- `AIInsightSource` و`ai_traceability_service.py` يسجلان source/version/snapshot ويحولان insight إلى OUTDATED عند تغير source، وهذه قاعدة ممتازة لإعادة الاستخدام.
- الإبطال الحالي ليس شاملاً لكل الأنواع: توجد calls واضحة عند تغييرات task وfield submission، لكن document/design-change/message/permission changes لا يملكون coverage موحدًا لكل derived result. لا توجد derived summaries كبيرة اليوم، لكن أي إضافة لها يجب ألا تعتمد على invalidation الحالي كما هو.

### 3.6 الإشعارات وتجميع المشكلات

`agents/notification_policy.py` يفصل التسجيل عن الدفع:

- uncertain أو confidence منخفض: يُحفظ ولا يدفع.
- confidence ≥ .85 مع HIGH/CRITICAL: important.
- confidence ≥ .6: review.
- `event_subscriber.py` يستخدم `dedupe_key=agent-finding:{insight.id}`.

هذا يمنع تكرار الإشعار لنفس insight. لكنه لا ينشئ **قضية واحدة مستمرة** تجمع عشرة site reports ومراسلتين وtask متأخرًا. البصمة في agent runtime تجمع finding “عن الشيء نفسه” ضمن حدود rule، لكنها ليست case entity لها first_seen/last_seen/episodes/state transitions/root-cause hypotheses/coverage. هذا هو الفرق بين dedupe الإشعار وإدارة مشكلة متراكمة.

### 3.7 الصلاحيات وعزل المشاريع والمؤسسات

النقاط الجيدة المؤكدة:

- `Project.company_id`, `OrganizationMembership`, `ProjectMember`, configurable roles، disciplines، وproject-scoped external parties.
- `document_access.py` يجعل external document access deny-by-default عبر `DocumentPartyShare`.
- vector search لا يمكن استدعاؤه بلا `project_id` ومجموعتي readable IDs؛ empty تعني zero لا all (`rag/store.py:PgVectorStore.search`).
- IFC له policy مستقل، وknowledge routing يتحقق منه.
- auto agent يستخدم مدير المشروع الحقيقي كـprincipal، لا system superuser؛ مشروع بلا مدير يُتخطى (`agents/event_subscriber.py`).

الخطر عند إضافة summaries: لا يكفي وضع `project_id` على summary. إذا لخصت community فيها مصادر بصلاحيات مختلفة، تصبح الخلاصة مشتقة من أكثر source حساسية. يجب حفظ visibility fingerprint أو materialize summary لكل access cohort، والأفضل في البداية توليد القضية بعد filtering للمستخدم/المشغل وعدم مشاركة cache بين cohorts.

### 3.8 تسجيل الاستدعاءات والتوكنات والزمن والتكلفة والأخطاء

| المسار | ما يُسجَّل | الفجوة |
|---|---|---|
| Voice | `api/voice.py` ينشئ `AIProviderCall` ويحدث latency/success | token fields لا تظهر دائمًا من المسار المفحوص. |
| RAG indexing embeddings | `rag/ingestion.py:_record_provider_call` يسجل model/latency/input_tokens/success | لا سعر، لا currency، لا cost estimate، ولا provider request id. |
| Query embedding | `rag/retrieval.py` يستدعي `embed_one` | لا `AIProviderCall`. |
| RAG answer | `rag/answering.py` يسجل debug latency فقط | لا DB metric، لا input/output tokens، لا error row، لا cost. |
| Agents | `AgentRun` يسجل duration/tool calls/findings/status | حتمية ولا token لها؛ لا breakdown لزمن كل tool/query. |
| IFC/jobs | processing/job duration وحالات الخطأ | لا CPU/RSS/queue wait per job ولا throughput dashboard. |

إذًا تكلفة التحليل الحالية **غير قابلة للحساب الكامل من قاعدة البيانات**. لا ينبغي مقارنة RAPTOR/GraphRAG ماليًا قبل إكمال telemetry.

## 4. حالات الاستخدام الواقعية المستخرجة من النموذج

### الحالة A — تعارض مادة/متطلب قبل التنفيذ (أولوية التجربة 1)

- **المدخلات:** specification/approved material submittal، site report أو delivery ticket، task planned start، IFC element/material إن وجد.
- **العلاقات:** project → package/zone → material requirement → approval → delivery evidence → task → IFC element/version.
- **المخرج:** قضية “C30 staged بينما approved requirement C35؛ الصب غدًا”، severity/confidence، الفرق الرقمي والوحدة، وما يحتاج تأكيد مهندس.
- **الأدلة:** المقاطع الأصلية وصفحاتها، IDs، version/date، ticket photo/OCR confidence، task state، IFC property.
- **المفقود المحتمل:** OCR، mapping بين material code والـtask/element، accepted revision، هل C30 لموقع آخر.
- **التحقق البشري:** مهندس QA/QC يفتح المواصفة/approval/ticket، يؤكد location والمادة، ويصنف true/false/insufficient.
- **نوع الاستنتاج:** مقارنة القيم والوحدات حتمية بعد استخراج صحيح؛ كون الشحنة مخصصة للصب inference حتى يثبت link.

### الحالة B — تأخر توريد يتراكم ولا يظهر في الجدول (أولوية التجربة 2)

- **المدخلات:** PO/approval dates، correspondence، site reports، task dates/progress/status، dependencies، design changes.
- **العلاقات:** supplier/material/package ↔ correspondence ↔ site observations ↔ task ↔ dependent tasks.
- **المخرج:** قضية مستمرة first_seen/last_seen، episodes، affected tasks، divergence بين تقارير الموقع والجدول، وفرضيات لا “سبب مثبت”.
- **الأدلة:** order due date، supplier notice، عدة site reports، task baseline/current date وfloat إن توفر.
- **المفقود:** procurement entity صريح، actual delivery، updated schedule baseline، مسؤولية التأخير التعاقدية.
- **التحقق:** planner/PM يؤكد link والـfloat ويصنف “schedule not updated / absorbed / unrelated”.
- **نوع الاستنتاج:** “ورد تأخير” حقيقة؛ “التوريد سبب تأخر المهمة” inference؛ liability/causation غير مثبتة.

### الحالة C — أثر revision IFC على عمل منفذ

- مدخلات `IFCComparison/IFCChangeRecord/IFCEntityLink` + task status + photos/reports + approved documents.
- المخرج: changed element مرتبط بمهمة in_progress/done، مع direct-link confidence=1 أو discipline-only=.65.
- الحساب الهندسي (geometry/property delta) حتمي نسبيًا إلى parser؛ أثره التنفيذي يحتاج مهندسًا.

### الحالة D — RFI/DesignChange متكرر ومتأخر

- DesignChange، task review، messages، affected disciplines، due dates.
- المخرج: clarification theme يتكرر، open duration، impacted tasks.
- الفجوة: messages غير داخلة في knowledge corpus، ولا RFI entity مستقل.

### الحالة E — نمط عبر مشاريع المكتب

- قضايا reviewed من مشاريع متعددة، supplier/package/type normalized، مع access permission على portfolio.
- المخرج: pattern aggregate فقط لمن يملك الوصول إلى كل contributing projects، مع minimum cohort size لمنع disclosure.
- يجب تأجيله حتى ينجح project-level case detection وتُحسم سياسة الصلاحيات عبر المشاريع.

## 5. المشكلات والاختناقات

### مؤكدة من الكود

1. لا OCR ولا vision؛ scanned PDFs والصور خارج التحليل.
2. XLSX لا يقرأ خلايا؛ DOCX extraction غير كامل ولا page anchors حقيقية.
3. dense-only top-k؛ لا hybrid ولا reranking ولا threshold.
4. لا contradiction detection، رغم اسم Document Consistency Agent.
5. المراجع هي retrieved-set citations وليست claim-used citations.
6. corpus لا يشمل messages والمراسلات المنظمة كلها؛ domain events لا توقظ تحليلًا على message.
7. agents تضع caps صغيرة ولا تعمل global scan/pagination.
8. لا issue/case aggregation عبر الزمن؛ فقط findings + notification dedupe.
9. telemetry ناقصة لاستدعاء السؤال والإجابة والتكلفة.
10. RAG وauto-agent مغلقان افتراضيًا؛ وجود الكود لا يثبت أنه مفعل في deployment.

### محتملة وتحتاج قياسًا

1. HNSW مع large readable-ID filters؛ iterative scan يساعد، لكن recall/latency حسب حجم corpus وselectivity مجهولان.
2. بناء قوائم IDs ثم `IN (...)` قد يصبح مكلفًا مع آلاف المصادر لكل مشروع.
3. worker pool مشترك بين IFC/RAG/agents دون priority/per-kind capacity؛ قد يحدث head-of-line blocking.
4. إعادة قراءة الملف كاملًا للفهرسة بعد ingestion تزيد I/O، خصوصًا remote storage.
5. `compare_versions` يحمل element maps كاملة ويكتب changes في run واحد؛ memory/time لنماذج IFC كبيرة مجهولان.
6. query concurrency على نموذج الإجابة ومعدل المزود؛ لا load test ولا rate/cost budget خاص بـRAG.
7. جودة Arabic/English embeddings واستخراج المصطلحات والوحدات غير مقاسة.
8. stale results عند تغير share/role: retrieval اللحظي آمن، لكن أي summary/cache جديد قد يتسرب إن لم يحمل access fingerprint.

لا يوجد دليل يسمح بنسبة البطء إلى LLM. في المسارات الحالية قد يأتي من extraction، IFC parsing/geometry، database filtering، queue wait، provider embedding، أو frontend. القياس المقترح يفصل كل مرحلة.

## 6. ما تقوله الأبحاث فعلًا

### RAPTOR

المصدر الأصلي: [RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval](https://arxiv.org/abs/2401.18059) و[PDF الورقة](https://arxiv.org/pdf/2401.18059).

الطريقة: chunks → embeddings → UMAP + soft GMM clustering → LLM summaries → تكرار هرمي. الاستعلام إما tree traversal أو collapsed-tree retrieval عبر كل المستويات. استخدمت الورقة GPT-3.5-turbo للتلخيص وSBERT للاسترجاع، وكان collapsed tree بميزانية 2000 token الأفضل في عينة QASPER.

ما تدعمه النتائج:

- تحسن في NarrativeQA/QASPER/QuALITY، وهي QA على روايات/أوراق NLP/نصوص متوسطة، لا بيانات إنشاء متعددة الجداول والإصدارات.
- الورقة تنسب 20 نقطة absolute في أفضل نتيجة QuALITY عند اقتران RAPTOR بـGPT-4، لكن هذا لا ينتقل تلقائيًا إلى contradiction detection أو schedule risk.
- build time وtoken expenditure أظهرا scaling خطيًا حتى نحو 78k input tokens على Apple M1/16GB؛ هذا ليس benchmark لملايين tokens أو updates مستمرة.
- متوسط compression 72%، ومتوسط parent summary 131 tokens.
- annotation يدوي لـ150 summary وجد minor hallucinations في 4%؛ القول إنها لم تنتشر في تجربتهم لا يزيل الخطر في أرقام ووحدات تعاقدية.
- ablation clustering مقابل contiguous balanced tree كان 56.6% مقابل 55.8% فقط في إعداد QuALITY/UnifiedQA، أي أن فائدة clustering نفسها ليست ضخمة في ذلك الاختبار.

فرضيات تحتاج اختبارًا في StructIQ:

- هل summaries الهرمية تحسن recall لقضية ممتدة عبر تقارير؟
- هل تحفظ الأرقام/الوحدات/negation/revision status؟
- كيف يُحدث cluster عند تعديل/حذف وثيقة؟ الورقة الأساسية ليست تصميمًا incremental ديناميكيًا.
- هل tree يجب أن يكون per-document، per-case، per-project، أم per-permission cohort؟

### GraphRAG كما في الورقة

المصدر الأصلي: [From Local to Global: A GraphRAG Approach to Query-Focused Summarization](https://arxiv.org/abs/2404.16130) و[PDF الورقة](https://arxiv.org/pdf/2404.16130).

الطريقة: LLM يستخرج entities/relationships/descriptions من chunks → Leiden hierarchical communities → community summaries → عند السؤال map partial answers على summaries ثم reduce إلى global answer.

ما تدعمه النتائج:

- تحسن comprehensiveness/diversity على global sensemaking في corpora اثنين بحجم يقارب مليون token (news وpodcasts)، مقارنة vector RAG.
- الأسئلة نفسها وُلدت بـLLM، والتقييم الأساسي head-to-head بـLLM-as-a-judge؛ أضيف claim-based analysis، لكن لا gold engineering truth.
- paper تقر أن generalization domains، fabrication rates، وحالات الاستخدام الأخرى تحتاج عملًا إضافيًا.
- فهرسة podcast بإعداد 600-token استغرقت 281 دقيقة على VM 16GB مع GPT-4-turbo endpoint عالي الحدود؛ هذا مؤشر كلفة/زمن مهم لمكتب صغير، لا رقم تسعير مباشر.
- global answer متعدد الاستدعاءات: community map ثم reduce. query cost أعلى من استدعاء واحد ويمكن أن يزيد مع communities.
- larger chunks أرخص لكن تقل entity recall؛ GPT-4 استخرج تقريبًا ضعف entity references عند 600 مقابل 2400 token في عينة HotPotQA، لذلك تستخدم الطريقة gleaning/self-reflection باستدعاءات إضافية.

لا تدعم الورقة أن GraphRAG أفضل للأسئلة المحلية الدقيقة، ولا أنها آمنة تلقائيًا مع صلاحيات دقيقة، ولا أن graph extraction بـLLM يتفوق على العلاقات الحتمية الموجودة في قاعدة StructIQ.

## 7. المقارنة للمشروع

| المعيار | تحسين الحالي | RAPTOR | GraphRAG الورقي | دمج محدود مقترح |
|---|---|---|---|---|
| علاقات task/IFC/change/report | يستعملها مباشرة | ضعيف؛ شجرة نص | يعيد استخراج graph نصي غالبًا | يستعمل DB edges ثم text retrieval |
| global sensemaking | محدود حاليًا | جيد للوثائق الطويلة | الأقوى بحثيًا للأسئلة global | قضية/زمن محدد بدل corpus كله |
| التفاصيل الدقيقة والأرقام | chunks أصلية جيدة | summary قد يفقدها | community summary قد يفقدها | always drill-down إلى الأصل |
| provenance | موجود page/source | يحتاج child lineage | record refs لكن عدة طبقات | claim→chunk→source/version |
| التحديث/الحذف | reindex source واضح | recluster/ancestor rebuild | entity/community rebuild معقد | invalidate case dependencies فقط |
| تكلفة البناء | embedding فقط | embedding + recursive LLM | استخراج graph + gleaning + summaries | علاقات DB مجانية نسبيًا + LLM انتقائي |
| query cost | query embed + answer | مشابه مع mixed-level nodes | map-reduce متعدد | retrieval + verifier واحد غالبًا |
| الصلاحيات | قوية per-source | summary قد يمزج visibility | community leakage خطر كبير | filter قبل traversal؛ cache cohort-bound |
| الدمج والصيانة | الأقل | schema/tree jobs جديدة | pipeline كبيرة ومراقبة graph | متوسط، فوق الجداول الحالية |
| ملاءمة مكتب صغير | عالية بعد القياس | لاحقًا لحالات محددة | ضعيفة الآن | الأعلى إذا ثبتت فائدة القضية |

### القرار

ابدأ بتحسين الحالي وEvidence Cases. لا تنفذ RAPTOR أو GraphRAG كاملًا الآن.

RAPTOR يصبح مرشحًا ثانويًا فقط لو أظهر benchmark أن أسئلة document-level multi-hop تفشل بعد hybrid+rereank. حينها نضيف summary nodes **per long document أو per case** لا tree عامة، ونفرض أن الأرقام والوحدات تأتي من leaf evidence.

GraphRAG الورقي يصبح مرشحًا فقط لميزة portfolio/global themes بعد نجاح project-level analysis، ويفضل حينها graph من العلاقات المنظمة + extraction محدود لما لا يوجد، لا LLM graph من الصفر. هذا يختلف جوهريًا عن paper implementation ويجب تسميته graph-assisted analysis، لا الادعاء أنه GraphRAG مطابق.

## 8. التصميم المقترح

### 8.1 ما يعاد استخدامه

- PostgreSQL/pgvector/HNSW و`DocumentChunk`.
- `knowledge_router` للفصل بين structured queries والنص.
- `document_access` وIFC policy وtool runtime.
- `BackgroundJob` queue والـworker.
- `DomainEvent` مع توسيع coverage.
- `AIInsight`, `AIInsightSource`, review/promotion workflow.
- IFC version/change/link/finding tables.
- Agent claim certainty/confidence caps.

### 8.2 إضافات البيانات (من دون قاعدة جديدة)

1. `analysis_cases`: project_id، type، fingerprint، state، severity، confidence، first_seen، last_seen، occurrence_count، coverage_json، access_fingerprint، stale_at.
2. `analysis_case_claims`: case_id، claim_type (`FACT/DETECTED/INFERRED/HYPOTHESIS`)، normalized subject/predicate/value/unit/time، confidence، verifier status.
3. `analysis_case_sources`: case/claim → source_type/id/version/chunk/page/span/snapshot_hash/is_valid.
4. `analysis_case_entities`: روابط إلى task/design_change/IFC element/package/material/supplier؛ authoritative/inferred distinction.
5. `analysis_runs`: stage timings، corpus coverage، failures، provider usage، cost snapshot.

يمكن في MVP إعادة استخدام `AIInsightSource` وتوسيع `AIInsight` بدل جداول case كلها، لكن lifecycle المتراكم سيصبح awkward سريعًا. Case entity مستقلة مبررة لأنها تمثل مشكلة مستمرة لا نتيجة تشغيل واحدة.

### 8.3 عند إدخال البيانات

1. استخراج محتوى قابل للاستشهاد: OCR page images + confidence؛ DOCX paragraphs/tables مع anchors؛ XLSX sheet/cell ranges/formulas/units.
2. حفظ content hash وsource version وextraction coverage/errors.
3. chunking يحافظ على section/table/row boundaries، لا token windows فقط.
4. dense embedding + PostgreSQL `tsvector` للبحث الهجين.
5. نسخ العلاقات الموجودة (IDs فقط) إلى evidence lookup، لا LLM extraction.
6. emit events لكل source create/update/delete/share change.
7. invalidate cases/summaries التي تعتمد على snapshot تغير.

### 8.4 عند السؤال أو التحليل الدوري

1. resolve project/access scope أولًا.
2. route إلى structured facts حيث تكفي.
3. retrieve hybrid: lexical exact codes/clauses/material grades + dense semantic؛ fusion بـRRF.
4. expand عبر authoritative edges فقط بحد hop/budget واضح.
5. rerank candidates مع metadata (date/version/status/source authority).
6. detector خاص بالحالة: value contradiction، temporal accumulation، schedule divergence، revision impact.
7. LLM يصوغ/يربط فقط عندما تحتاج دلالة لغوية، ويعيد JSON claims مع evidence IDs؛ verifier يرفض claim بلا source أو بvalue غير موجود.
8. case merge بالـfingerprint والكيانات والزمن؛ update بدل notification جديد.
9. answer/report يعرض facts أولًا، hypotheses منفصلة، والبيانات الناقصة.

### 8.5 الأرقام والوحدات والنسخ والتواريخ

- لا تجعل summary المصدر الوحيد لأي رقم.
- كل extracted value يحمل raw text، normalized value، unit، source span/page/cell، extraction confidence.
- خزّن `valid_time` (متى كانت الحقيقة صحيحة) و`recorded_at` (متى دخلت النظام) و`source_version`.
- عند تعارض revision، لا تستخدم “الأحدث” فقط؛ استخدم active/approved/issued status. IFC يملك active/baseline، ويجب أن تملك الوثائق lineage/status مماثلًا.
- المقارنات العددية حتمية بعد normalization؛ causation والمسؤولية تبقى hypotheses.

### 8.6 التغطية والفشل

كل run/case يعرض:

- sources eligible / processed / failed / unindexable / hidden-by-access.
- date range covered.
- OCR/table/parser confidence.
- هل analysis truncated بسبب limits.
- missing expected source types (مثلاً لا schedule baseline أو delivery record).
- freshness timestamp وstale badge.

النتيجة “لم نجد تعارضًا” لا تظهر إن كانت 40% من ملفات PDF scans غير مقروءة؛ تظهر “لا تعارض ضمن 60% المغطاة”.

## 9. التجربة المعزولة ونتيجتها

المجلد: `research/ai_architecture_study/`.

- `synthetic_cases.json`: 12 source اصطناعيًا، مشروعان أساسيان ودخيل cross-project ومصدر client-only.
- `benchmark.py`: Python standard library فقط، بلا network أو secrets أو app DB.
- `results.json`: ناتج تشغيل 29 أكتوبر 2026.

قارنت التجربة:

- flat hashed-vector top-4 كـshape proxy للاسترجاع الحالي؛
- نفس التشابه + expansion عبر entity/explicit links، مع نفس top-4.

النتائج المقاسة في هذا التشغيل:

| الحالة | Flat recall/precision | Evidence graph recall/precision | تسرب |
|---|---:|---:|---:|
| procurement delay | 1.00 / 1.00 | 1.00 / 1.00 | 0 |
| concrete contradiction | 1.00 / 1.00 | 1.00 / 1.00 | 0 |

Median latency كان نحو 0.21–0.24 ms على corpus الصغير؛ graph-assisted أبطأ قليلًا. عند 1200 source في proxy Python، median نحو 10.69 ms flat و10.76 ms graph-assisted. حذف source أزاله من result وأثبت dependency invalidation condition. 100 query على 8 threads أعادت نتائج متطابقة.

التفسير الصحيح: **لا تحسن جودة في هاتين الحالتين السهلتين، ولا مبرر تجريبي لإضافة graph retrieval الآن**. ليس صحيحًا استنتاج أن الطريقتين متكافئتان عمومًا، لأن:

- المتجهات lexical hash وليست production embeddings.
- لا LLM، فلا قياس answer correctness/hallucination/tokens.
- العلاقات معطاة صحيحة، ولم نقس استخراجها.
- حالتان authored فقط، ولا external validity.
- أرقام latency تخص script لا backend/PostgreSQL.

هذه التجربة صالحة كـsmoke harness وبداية protocol، لا كورقة نتائج.

## 10. خطة تنفيذ مرحلية

### المرحلة 0 — القياس وgold set (1–2 أسبوع مهندس)

- وسّع `AIProviderCall`: operation، request/response tokens، cached tokens، pricing version، estimated cost، provider request id.
- سجّل query embedding وRAG answer في `api/rag.py`, `api/knowledge.py`, `rag/answering.py`.
- stage timings: queue wait/extract/chunk/embed/store/retrieve/rerank/generate/verify.
- اجمع 30–50 case مصطنعة/منزوعة الهوية يراجعها مهندسان.
- dependency: موافقة على data handling وتعريف rubric.

بوابة الانتقال: يمكن حساب cost/case وp95 latency وevidence recall، لا مجرد tokens/request.

### المرحلة 1 — إكمال ingestion والتغطية (2–4 أسابيع)

- OCR محلي/مزود معزول حسب الخصوصية، page-level confidence.
- DOCX anchors والجداول؛ XLSX cells/ranges والوحدات.
- coverage/failure schema وUI.
- وحّد capability registry وأزل drift بين `file_intelligence.py` و`rag/text_source.py`.
- أدخل messages/correspondence المصرح بها في source abstraction.

بوابة: ≥95% من gold evidence قابل للفتح والاستشهاد، مع فصل scanned failures.

### المرحلة 2 — retrieval والاستشهاد (2–3 أسابيع)

- `tsvector` + dense + RRF داخل `rag/store.py` abstraction.
- reranker اختياري صغير بعد قياس lexical+dense.
- metadata filters: source type/date/status/version.
- claim-to-source markers والتحقق من quoted numeric spans.
- threshold/abstention.

بوابة: تحسن evidence recall@budget وcitation support rate دون تجاوز latency/cost budget.

### المرحلة 3 — Evidence Cases لحالتي A وB (3–5 أسابيع)

- migrations/models/services للحالات والclaims والمصادر.
- detectors: normalized numeric contradiction؛ temporal repeated-delay + schedule divergence.
- event subscriptions create/update/delete/share؛ source invalidation.
- case merge/lifecycle وnotification update بدل flood.
- واجهة review: confirm/false positive/insufficient/link correction.

بوابة: precision وrecall ومعدل alert لكل مشروع مقبول لدى مهندسي pilot.

### المرحلة 4 — IFC/case integration وfield pilot (2–4 أسابيع)

- استخدم `IFCEntityLink`, comparisons, active/baseline، لا embeddings لـIFC facts.
- load tests لحجم IFC/corpus الحقيقي، queue priority/per-kind capacity.
- pilot في 2–3 مشاريع لمدة 4–6 أسابيع، shadow mode أولًا.

### المرحلة 5 الاختيارية — summaries هرمية محدودة (2–3 أسابيع prototype)

فقط إذا فشل hybrid+case retrieval في global/multi-hop gold questions:

- per-case أو per-long-document summaries، child lineage كامل.
- incremental ancestor rebuild فقط.
- numeric/unit/negation preservation checks.
- لا community summary عبر access cohorts.

إن لم تتجاوز baseline بفارق متفق عليه، تُحذف التجربة ولا تدخل production.

## 11. خطة Evaluation تقني وميداني

### 11.1 Dataset والـground truth

- stratified cases: عربية، إنجليزية، mixed; scans; DOCX/XLSX; updated/deleted docs; IFC revisions.
- لكل case: expected problem، required evidence، distractors، permitted audience، unknowns.
- مهندسان مستقلان + adjudication؛ يقيس inter-rater agreement.
- لا LLM judge كمرجع وحيد. يمكن استخدامه تحليلًا ثانويًا blinded.

### 11.2 المقارنات

B0 الحالي: dense top-k.  
B1 hybrid + rerank + claim citations.  
C1 B1 + authoritative relationship expansion/cases.  
C2 RAPTOR-limited فقط إذا بقيت long-document failures.  
GraphRAG full يدخل فقط إذا كان السؤال global corpus sensemaking وتوجد ميزانية منفصلة.

ثبّت model/data/context budget قدر الإمكان؛ سجّل كل اختلاف.

### 11.3 المقاييس

جودة:

- issue precision/recall/F1، missed-critical rate، false alerts/project-week.
- evidence recall@budget، citation precision، claim support/contradiction rate.
- numeric exactness، unit correctness، temporal ordering، version correctness.
- abstention correctness وcoverage disclosure accuracy.

تشغيل:

- indexing build/update/delete latency؛ queue wait؛ p50/p95/p99 query/analysis.
- provider calls/tokens/cost لكل source/case/query، بما في ذلك preparation.
- peak RSS/CPU/DB size/HNSW size؛ throughput عند 1/5/20 concurrent users.
- stale-result survival time، invalidation completeness، access leakage tests.

ميداني:

- time-to-verify، % findings actioned/dismissed/insufficient، correction rate.
- duplicates avoided، interruptions per user/week، engineer trust calibration.
- لا تستخدم “رضا المستخدم” وحده؛ راقب هل الدليل الصحيح فُتح وهل القرار تحسن.

### 11.4 معايير نجاح أولية قابلة للنقاش

- zero cross-project/unauthorized leakage في security suite.
- citation support ≥95% للclaims المعروضة.
- critical-case recall ≥90% على gold set مع confidence intervals.
- false alerts ≤1 meaningful interruption/project/week في pilot.
- stale derived result invalidated خلال target event SLA.
- المرشح يتفوق على B1 بفارق عملي، لا statistically noisy، عند نفس context/cost budget.

لا أثبت هذه الأرقام كمتطلبات نهائية؛ يجب أن يضبطها المكتب حسب تحمل المخاطر وحجم العمل.

## 12. الإضافة الهندسية مقابل المساهمة البحثية

### إضافات هندسية مفيدة وليست جِدّة بحثية بذاتها

- تركيب RAPTOR/GraphRAG منشور.
- hybrid retrieval/reranker/OCR/pgvector.
- knowledge graph أو case table.
- citations، RBAC، job queue، dashboards.

### مساهمة بحثية مرشحة، لا ادعاء جِدّة

فرضية قابلة للاختبار:

> هل يحسن تحليل evidence-case زمني، يجمع علاقات construction المنظمة مع استرجاع نصي ويحافظ على provenance/version/access، اكتشاف القضايا متعددة المصادر ودقة الأدلة عند نفس ميزانية السياق، مقارنة بـflat RAG وhierarchical summarization؟

محاور محتملة:

1. **Authoritative-edge-first retrieval**: العلاقات المنظمة أولًا، وLLM extraction فقط للفجوات، مع قياس أثر كل نوع edge.
2. **Incremental case invalidation**: تحديث القضية حسب source snapshots بدل إعادة بناء corpus communities.
3. **Permission-monotone derived knowledge**: برهان/اختبار أن كل derived artifact لا يملك audience أوسع من تقاطع مصادره.
4. **Construction claim taxonomy**: فصل fact/deterministic comparison/inference/causal hypothesis مع human calibration.

قبل ادعاء novelty يلزم systematic literature review أوسع من الورقتين: construction NLP/RAG، BIM knowledge graphs، delay/claim analytics، temporal knowledge graphs، contradiction detection، permission-aware RAG، وincremental summarization. الورقتان وحدهما لا تكفيان لإثبات الفجوة العلمية.

## 13. المعلومات المطلوبة للجولة التجريبية التالية

بعد هذا الفحص، الأسئلة الضرورية هي:

1. أحجام فعلية منزوعة الهوية: عدد الملفات/pages/messages/tasks/IFC elements لكل مشروع، معدل التحديث، وعدد المشاريع المتزامنة.
2. توزيع الصيغ واللغات ونسبة scans وXLSX/DOCX.
3. هل يمكن توفير 20–50 حالة راجعها مهندس مع الأدلة الصحيحة، أم نبدأ بالكامل بsynthetic fixtures؟
4. deployment الفعلي: CPU/RAM/DB size/worker count ومعدل users المتزامنين.
5. سياسة المزود: هل يسمح بإرسال بيانات منزوعة الهوية إلى API للتجربة، وما سقف التكلفة؟ من دون تفويض تبقى التجارب offline/stubbed.

لا تمنع هذه الأسئلة القرار المعماري الحالي؛ هي لازمة لتحويله إلى benchmark واقعي وتقدير تكلفة موثوق.

## الخلاصة التنفيذية

StructIQ يملك أساسًا جيدًا: structured domain model، IFC version intelligence، permission-safe tools، pgvector، jobs، traceable insights، ومراجعة بشرية. المشكلة ليست غياب “تقنية RAG متقدمة”، بل أن البيانات المهمة لا تصل كلها إلى طبقة التحليل، والاسترجاع أحادي، والclaims غير متحققة، والنتائج لا تُدار كقضايا زمنية، والقياس المالي/الزمني ناقص.

لذلك أفضل خطوة ليست إعادة الكتابة، بل بناء baseline علمي وتحسين coverage/retrieval/provenance، ثم Evidence Cases على حالتين واضحتين. RAPTOR وGraphRAG يبقيان baselines بحثية أو إضافات انتقائية، لا وجهة افتراضية.
