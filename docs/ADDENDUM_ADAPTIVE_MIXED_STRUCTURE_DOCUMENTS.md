# ADDENDUM — ADAPTIVE MIXED-STRUCTURE REGULATORY DOCUMENT HANDLING
## Pelengkap `MASTER_DEVELOPMENT_SPEC.md`

**Status:** Required Architecture Addendum  
**Version:** 1.0  
**Purpose:** Melengkapi spesifikasi utama agar sistem mampu menangani kumpulan dokumen regulasi, petunjuk teknis, keputusan, lampiran, diagram, naskah akademik, SOP, dan dokumen lain dengan pola struktur yang berbeda-beda, termasuk beberapa pola struktur berbeda dalam satu PDF.

# 1. LATAR BELAKANG PERUBAHAN

Sistem tidak boleh berasumsi bahwa semua dokumen regulasi memiliki pola:

```text
BAB
→ Pasal
→ Ayat
→ Huruf
```

Dalam praktik, satu collection dapat berisi:

```text
Dokumen A
BAB
→ Angka/Butir bernomor
→ Huruf
→ Subangka

Dokumen B
BAB
→ Pasal
→ Ayat
→ Huruf

Dokumen C
Keputusan
→ Menimbang
→ Mengingat
→ Memutuskan
→ KESATU/KEDUA/KETIGA

Dokumen D
Petunjuk Teknis
→ BAB
→ Nomor Pokok
→ Subpokok
→ Daftar bertingkat

Dokumen E
SOP
→ Tujuan
→ Ruang Lingkup
→ Prosedur
→ Tahapan

Dokumen F
Lampiran
→ Tabel
→ Diagram
→ Bagan Organisasi
→ Flowchart

Dokumen G
Template/Naskah Akademik
→ BAB
→ Angka bernomor
→ sub-item
```

Lebih penting lagi, satu file PDF dapat mengandung beberapa pola tersebut sekaligus.

Karena itu arsitektur harus menghindari `Pasal-centric parsing`.

# 2. PRINCIPLE OVERRIDE

Tambahkan aturan berikut sebagai prinsip wajib:

> `Pasal`, `Ayat`, dan `Huruf` adalah specialized node types, bukan struktur wajib.

Sistem harus selalu mampu membangun struktur generik terlebih dahulu.

Urutan:

```text
LAYOUT
↓
GENERIC STRUCTURE
↓
STRUCTURAL REGION CLASSIFICATION
↓
SPECIALIZED INTERPRETATION
↓
CANONICAL HIERARCHICAL TREE
```

Jangan:

```text
PDF
↓
cari BAB
↓
cari Pasal
↓
gagal jika Pasal tidak ada
```

# 3. NEW CORE CONCEPT: STRUCTURAL REGION

Satu dokumen harus dapat dibagi menjadi beberapa `StructuralRegion`.

Contoh:

```text
PDF
│
├── Region 1: Cover
├── Region 2: Table of Contents
├── Region 3: Legal Decision Preamble
│   ├── Menimbang
│   ├── Mengingat
│   └── Memutuskan
├── Region 4: Technical Manual
│   ├── BAB
│   ├── Numbered Section
│   ├── Letter
│   └── Nested Item
├── Region 5: Appendix
│   ├── Diagram
│   └── Table
└── Region 6: Embedded Template
    ├── BAB
    └── Numbered Section
```

Setiap region dapat memiliki grammar yang berbeda.

# 4. STRUCTURAL REGION TYPES

Minimal support:

```text
COVER
TABLE_OF_CONTENTS
LEGAL_PREAMBLE
LEGAL_BODY
LEGAL_DECISION
TECHNICAL_GUIDELINE
PROCEDURAL_GUIDELINE
NUMBERED_MANUAL
SOP
APPENDIX
TABLE_REGION
DIAGRAM_REGION
ORGANIZATION_CHART
FLOWCHART
EMBEDDED_TEMPLATE
ACADEMIC_TEMPLATE
FREEFORM_SECTION
UNKNOWN
```

# 5. UNIVERSAL CANONICAL DOCUMENT TREE

Gunakan canonical tree generik:

```text
Document
│
├── StructuralRegion
│   ├── Heading
│   ├── Section
│   ├── NumberedSection
│   ├── LegalArticle
│   ├── Clause
│   ├── LetterItem
│   ├── NumberedItem
│   ├── NestedItem
│   ├── Paragraph
│   ├── List
│   ├── Table
│   ├── Diagram
│   ├── Figure
│   └── Appendix
└── StructuralRegion
```

Specialized legal nodes tetap didukung. Generic nodes selalu tersedia.

# 6. NODE MODEL

Jangan desain database node hanya dengan:

```text
chapter
article
clause
letter
```

Gunakan node generik:

```text
DocumentNode

id
document_id
document_version_id
region_id

parent_id
previous_id
next_id

node_type
semantic_role

label
title

number_raw
number_normalized
numbering_style

text
normalized_text

depth
sequence_number

page_start
page_end
bounding_box

confidence
source_provenance
```

Optional specialized fields:

```text
chapter_number
article_number
clause_number
letter_number
appendix_number
```

Specialized fields boleh NULL.

# 7. NODE TYPES

Minimal:

```text
DOCUMENT
REGION
TITLE
SUBTITLE
CHAPTER
PART
SECTION
SUBSECTION
NUMBERED_SECTION
NUMBERED_ITEM
LETTER_ITEM
ROMAN_ITEM
NESTED_ITEM
ARTICLE
CLAUSE
DECISION_ITEM
PARAGRAPH
LIST
LIST_ITEM
TABLE
TABLE_ROW
TABLE_CELL
APPENDIX
FIGURE
DIAGRAM
FLOWCHART
ORGANIZATION_CHART
FOOTNOTE
SIGNATURE_BLOCK
UNKNOWN_BLOCK
```

# 8. SEMANTIC ROLE

`node_type` menjelaskan bentuk. `semantic_role` menjelaskan fungsi.

Possible semantic roles:

```text
GENERAL
PURPOSE
OBJECTIVE
SCOPE
LEGAL_BASIS
DEFINITION
POSITION
PRINCIPLE
PLANNING
PREPARATION
EXECUTION
TERMINATION
PROCEDURE
REQUIREMENT
RESPONSIBILITY
AUTHORITY
DUTY
PROHIBITION
COMMAND
CONTROL
DECISION
VALIDITY
ORGANIZATION_STRUCTURE
PROCESS_FLOW
CONCLUSION
RECOMMENDATION
UNKNOWN
```

# 9. NUMBERING STYLE DETECTION

Kenali:

```text
1.
1)
(1)
a.
a)
(a)
I.
II.
A.
B.
KESATU
KEDUA
KETIGA
```

Simpan:

```text
number_raw
number_normalized
numbering_style
```

Contoh:

```text
number_raw = "11."
number_normalized = "11"
numbering_style = DECIMAL_DOT
```

# 10. HIERARCHY MUST BE INFERRED, NOT HARD-CODED

Contoh:

```text
BAB III
TAHAP PERENCANAAN

10. Umum
11. Urut-urutan Kegiatan
    a. ...
    b. ...
12. Dukungan
    a. ...
```

Harus menjadi:

```text
CHAPTER BAB III
├── NUMBERED_SECTION 10
├── NUMBERED_SECTION 11
│   ├── LETTER_ITEM a
│   └── LETTER_ITEM b
└── NUMBERED_SECTION 12
    └── LETTER_ITEM ...
```

Jangan ubah angka 10/11/12 menjadi Pasal.

# 11. MIXED STRUCTURE WITHIN ONE DOCUMENT

Critical rule:

> Structural grammar harus dideteksi per region, bukan hanya per file.

Satu PDF dapat berisi legal preamble, article-based body, numbered manual, appendix visual, dan embedded template sekaligus.

# 12. EMBEDDED DOCUMENT / TEMPLATE SUPPORT

Lampiran dapat mempunyai hierarchy sendiri.

```text
APPENDIX
└── EMBEDDED_DOCUMENT
    ├── CHAPTER
    ├── NUMBERED_SECTION
    └── NUMBERED_ITEM
```

Tetap pertahankan provenance ke PDF induk.

# 13. VISUAL APPENDIX SUPPORT

Lampiran dapat berupa:

- bagan organisasi,
- flowchart,
- diagram proses,
- struktur komando,
- form,
- template.

Pipeline:

```text
Visual Page
↓
Layout Detection
↓
OCR / image-aware extraction
↓
VLM fallback jika diperlukan
↓
Visual Object Classification
↓
Structured Representation
```

Visual structured representation hanya retrieval enrichment. Original visual tetap source of truth.

# 14. OCR / VLM ESCALATION

Jika embedded text kosong atau tidak usable:

```text
Render Page
↓
OCR
↓
Layout Reconstruction
↓
VLM fallback jika hierarchy masih ambigu
```

Jangan menandai dokumen gagal hanya karena text layer tidak ada.

# 15. DOCUMENT STRUCTURE PROFILE

Generate metadata seperti:

```json
{
  "contains_articles": false,
  "contains_numbered_sections": true,
  "contains_chapters": true,
  "contains_decision_preamble": true,
  "contains_appendices": true,
  "contains_tables": false,
  "contains_diagrams": false,
  "contains_embedded_document": false
}
```

Profile digunakan untuk routing dan QA.

# 16. ADAPTIVE CITATION PATH

Jangan wajibkan:

```text
Document
→ BAB
→ Pasal
→ Ayat
→ Huruf
→ Page
```

Gunakan generic `structural_path`.

Contoh:

```json
[
  {"type":"CHAPTER","label":"BAB III","title":"TAHAP PERENCANAAN"},
  {"type":"NUMBERED_SECTION","label":"11","title":"Urut-urutan Kegiatan"},
  {"type":"LETTER_ITEM","label":"a"}
]
```

Render:

```text
BAB III, angka 11 huruf a, halaman 7
```

Untuk article-based source:

```text
BAB III, Pasal 20, halaman 9
```

Untuk visual:

```text
Lampiran II, Mekanisme Pembentukan dan Likuidasi Korps/Kejuruan Baru, halaman 13
```

# 17. CITATION TERMINOLOGY

Gunakan terminology sumber.

Jika sumber memakai `Pasal`, tampilkan `Pasal`.

Jika sumber hanya memakai `11. Urut-urutan Kegiatan`, jangan menyebutnya `Pasal 11`.

# 18. GENERIC STRUCTURAL PATH STORAGE

Tambahkan:

```text
structural_path_json
structural_path_text
```

Contoh text:

```text
BAB III > 11 Urut-urutan Kegiatan > a
```

# 19. CHUNKING MUST FOLLOW GENERIC TREE

Possible chunk roots:

```text
ARTICLE
NUMBERED_SECTION
DECISION_ITEM
PROCEDURE_SECTION
TABLE
APPENDIX_SECTION
```

`ARTICLE` hanya salah satu opsi.

# 20. DEEP NESTED LIST SUPPORT

Support struktur seperti:

```text
18.
└── a.
    └── 2)
        └── b)
            └── (1)
```

Full parent path harus dipertahankan.

Gunakan configurable maximum structural depth, bukan Article→Clause→Letter yang hard-coded.

# 21. RETRIEVAL INDEX CHANGES

Tambahkan Qdrant payload:

```text
region_type
node_type
semantic_role
structural_depth
number_raw
number_normalized
numbering_style
structural_path_text
structural_path_json
appendix_label
visual_source_type
```

Tetap pertahankan `article`, `clause`, `letter` sebagai optional acceleration fields.

# 22. QUERY PARSER EXTENSION

Support:

```text
Pasal 17 ayat 2
BAB III angka 11
bagian 11
butir 11
poin 11
angka 18 huruf a
Lampiran II
KESATU
Tahap Perencanaan
Urut-urutan Kegiatan
Hasil Konsep
Mekanisme Pembentukan
Struktur Organisasi
```

Jika user salah menyebut `Pasal 11`, sementara source hanya punya angka 11, jangan fabricate Pasal. Jika mapping jelas, koreksi terminology secara eksplisit.

# 23. STRUCTURAL RETRIEVAL STRATEGY

Priority:

```text
1. Exact specialized match
2. Exact generic node match
3. Structural path lexical search
4. Sparse search
5. Dense semantic search
```

Structural retrieval harus mendukung ARTICLE, NUMBERED_SECTION, DECISION_ITEM, APPENDIX, TABLE, DIAGRAM, dan node lain.

# 24. DOCUMENT ROUTING BY STRUCTURE PROFILE

Contoh:

```text
query contains "Pasal"
→ prioritize regions with articles

query contains "angka/butir"
→ prioritize numbered-section structures

query asks "struktur organisasi"
→ prioritize organization chart / visual region

query asks "mekanisme"
→ prioritize procedure / flowchart region
```

Jangan hard-exclude struktur lain kecuali exact reference benar-benar membutuhkan itu.

# 25. VISUAL RETRIEVAL

Visual source metadata:

```text
visual_summary
visual_entities
visual_relationships
ocr_text
caption
page
bounding_box
```

Source drawer harus mampu membuka page visual aslinya.

# 26. SOURCE DISPLAY UI

Dynamic rendering:

```text
BAB III
Angka 11
Huruf a
Halaman 7
```

atau:

```text
BAB III
Pasal 20
Halaman 9
```

atau:

```text
Lampiran II
Mekanisme Pembentukan...
Halaman 13
```

Jangan tampilkan field kosong `Pasal: -`.

# 27. ADMIN STRUCTURE REVIEW

Admin melihat actual detected tree, misalnya:

```text
▼ BAB III TAHAP PERENCANAAN
   ├─ 10. Umum
   ├─ 11. Urut-urutan Kegiatan
   │   ├─ a.
   │   └─ b.
   └─ 12. Dukungan
```

atau:

```text
▼ BAB III
   ├─ Pasal 20
   ├─ Pasal 21
   └─ Pasal 22
```

Admin dapat memperbaiki node type, parent, label, title, dan region type tanpa mengubah original source text.

# 28. STRUCTURAL CONFIDENCE

Confidence mempertimbangkan:

```text
numbering consistency
heading typography
spatial relationship
sequence continuity
parent-child consistency
OCR confidence
lexical signal
layout signal
```

# 29. STRUCTURAL ANOMALY DETECTION

Detect kemungkinan:

```text
1 → 2 → 4
a → c
BAB III → BAB V
Pasal 18 → Pasal 20
unexpected nesting reset
```

Warning bukan otomatis error.

# 30. TABLE OF CONTENTS

TOC hanya hint.

Gunakan untuk membantu infer chapter/section, tetapi body harus memvalidasi keberadaan content.

# 31. PAGE NUMBER MODEL

Simpan terpisah:

```text
pdf_page_index
printed_page_number
```

PDF viewer memakai physical index. Citation menggunakan printed/document page jika tersedia dan stabil.

# 32. HEADER/FOOTER FILTER

Detect repeated headers, footer, page numbers, signature blocks. Jangan campur ke chunk isi kecuali relevan.

# 33. ANSWER GENERATION UPDATE

Evidence harus memakai:

```text
Structural Path:
BAB III > 11. Urut-urutan Kegiatan > a
```

Prompt policy:

> Cite the source using the exact Structural Path. Never rename a numbered section as a Pasal.

# 34. CLAIM/CITATION VERIFICATION UPDATE

Jika answer menyebut `Pasal 11` tetapi source node adalah `NUMBERED_SECTION 11`, tandai citation formatting invalid.

# 35. REQUIRED ACCEPTANCE TESTS

Wajib:

1. BAB + numbered sections tanpa Pasal.
2. BAB + Pasal + Ayat.
3. scanned PDF tanpa embedded text.
4. satu PDF dengan beberapa structural grammars.
5. deep nested numbering.
6. adaptive citation tanpa Pasal palsu.
7. organization chart.
8. flowchart appendix.
9. embedded structured template dalam appendix.
10. query dengan kata angka/butir/poin.
11. correction ketika user menyebut Pasal tetapi source menggunakan numbered section.
12. citation dynamic untuk visual source.

# 36. DATABASE ADDITIONS

Tambahkan/extend:

```text
document_regions

id
document_version_id
region_type
page_start
page_end
sequence_number
confidence
```

`document_nodes`:

```text
region_id
semantic_role
number_raw
number_normalized
numbering_style
structural_path_json
structural_depth
visual_source_type
```

# 37. NEW DOMAIN SERVICES

```text
StructuralRegionService
StructurePatternDetector
GenericHierarchyBuilder
SpecializedStructureInterpreter
StructuralPathService
AdaptiveCitationService
VisualDocumentService
```

# 38. FINAL PROCESSING PIPELINE

```text
UPLOAD
↓
FILE INSPECTION
↓
PAGE ANALYSIS
↓
ADAPTIVE PARSING
↓
REGION SEGMENTATION
↓
GENERIC DOCUMENT TREE
↓
STRUCTURE PATTERN DETECTION PER REGION
↓
SPECIALIZED INTERPRETATION
↓
CANONICAL HIERARCHY
↓
STRUCTURE QA
↓
ADMIN REVIEW IF NEEDED
↓
STRUCTURE-AWARE CHUNKING
↓
CONTEXTUAL EMBEDDING
↓
SPARSE INDEX
↓
STRUCTURAL INDEX
↓
PUBLISH
```

# 39. FINAL RETRIEVAL PIPELINE

```text
QUERY
↓
SESSION CONTEXT RESOLUTION
↓
REFERENCE PARSER
↓
STRUCTURE HINT DETECTION
↓
DOCUMENT / REGION ROUTING
↓
PARALLEL:
- STRUCTURAL LOOKUP
- DENSE SEARCH
- SPARSE SEARCH
↓
FUSION
↓
CONDITIONAL RERANK
↓
STRUCTURAL EXPANSION
↓
EVIDENCE
↓
GENERATION
```

# 40. ADDITIONAL DO-NOT-DO RULES

Do not:

- assume every regulation has Pasal,
- convert numbered sections into Pasal,
- assume one PDF has one structural grammar,
- discard visual appendices,
- fail scanned PDFs because text extraction is empty,
- flatten deeply nested lists,
- force fixed hierarchy depth,
- show empty Pasal/Ayat fields,
- cite summary as original evidence,
- treat TOC as authoritative content,
- ignore embedded templates inside appendices.

# 41. CODING AGENT PROMPT ADDITION

Append the following to the main coding agent prompt:

```text
==================================================
ADAPTIVE MIXED-STRUCTURE DOCUMENT REQUIREMENT
==================================================

A critical requirement is that uploaded regulatory documents do NOT
share one fixed hierarchy.

DO NOT assume:

Document → BAB → Pasal → Ayat → Huruf.

Some documents use:

BAB → numbered section → letter → nested numbered item.

Some use:

Decision → Menimbang → Mengingat → Memutuskan.

Some include SOP sections, technical guidelines, tables, appendices,
organization charts, flowcharts, templates, or free-form sections.

One PDF may contain MULTIPLE structural grammars.

Implement structure detection PER STRUCTURAL REGION, not only per file.

Always build a GENERIC HIERARCHICAL TREE first.

Specialized legal nodes such as ARTICLE and CLAUSE are OPTIONAL.

Every structural node must support generic parent/child relationships,
sequence, label, title, numbering style, depth, page provenance, and
confidence.

Support numbering patterns including:
1.
1)
(1)
a.
a)
I.
A.
KESATU/KEDUA/KETIGA.

Preserve deep hierarchy such as:
18. → a. → 2) → b) → (1).

A PDF with no embedded text must fall back to OCR/layout/VLM processing,
not automatically fail.

Visual appendices such as organization charts and flowcharts must be
recognized as first-class source regions with page provenance.

Citation must be adaptive and based on structural_path.

Example numbered guideline:
BAB III > 11 Urut-urutan Kegiatan > a
→ "BAB III, angka 11 huruf a, halaman X"

Example article regulation:
BAB III > Pasal 20
→ "BAB III, Pasal 20, halaman X"

Example visual appendix:
Lampiran II > Mekanisme Pembentukan ...
→ "Lampiran II, Mekanisme Pembentukan ..., halaman X"

Never invent Pasal/Ayat terminology that does not exist in the source.

Query parser must support:
Pasal, Ayat, BAB, angka, butir, poin, huruf, Lampiran,
KESATU/KEDUA/KETIGA, named stages, named headings, diagrams, and
organization structures.

Retrieval priority:
1. exact specialized structural match,
2. exact generic node match,
3. structural path lexical search,
4. sparse search,
5. dense semantic search.

Chunking must use meaningful structural units such as ARTICLE,
NUMBERED_SECTION, DECISION_ITEM, PROCEDURE_SECTION, TABLE, or
APPENDIX_SECTION.

Add mandatory acceptance tests for:
- numbered guideline without Pasal,
- conventional article regulation,
- scanned PDF,
- mixed-structure PDF,
- deep nesting,
- adaptive citation,
- visual appendix,
- embedded template.
==================================================
```

# 42. FINAL ARCHITECTURAL INTERPRETATION

Sistem bukan lagi sekadar:

```text
Legal Article Parser
```

tetapi:

```text
Adaptive Regulatory Document Structure Engine
```

Tanggung jawabnya:

```text
Unknown Regulatory Document
↓
Discover Structure
↓
Segment Structural Regions
↓
Build Generic Tree
↓
Apply Specialized Interpretation
↓
Preserve Provenance
↓
Create Searchable Hierarchy
```

Tujuannya adalah memahami **hierarki dokumen**, bukan menghafal satu template regulasi.

---

**END OF ADDENDUM**
