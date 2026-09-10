# ADDENDUM — LAN ARCHIVE INGESTION HINGGA 4 TB DAN COST CONTROL
## Pelengkap `MASTER_DEVELOPMENT_SPEC.md`

**Status:** Required Architecture Addendum
**Version:** 1.0
**Purpose:** Melengkapi spesifikasi utama agar sistem mampu menerima sumber pengetahuan berupa arsip folder-sharing Windows (LAN) berukuran hingga sekitar 4 TB, dengan proses inkremental, bertahap, dan biaya terkendali — tanpa mengorbankan evidence-first, tenant isolation, dan hak akses yang sudah menjadi prinsip inti (§3, §7 master spec).

Referensi arsitektur turunan: [ADR-020](adr/ADR-020-lan-archive-source-connector.md) (keputusan konektor). Rencana milestone konkret: `docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md`. Progress berjalan: `docs/LAN_ARCHIVE_PROGRESS.md`.

---

# 1. LATAR BELAKANG DAN BATASAN

Client memiliki arsip dokumen (PDF, DOCX, kemungkinan DOC lama) pada folder sharing Windows melalui LAN, dengan karakteristik:

- Total dapat mencapai ~4 TB dan terus bertambah.
- File individual dapat mencapai ~100 MB — batas ini **per file**, bukan batas total koleksi (`MAX_FILE_SIZE_MB` sudah demikian di `apps/api/app/core/config.py`, hanya perlu direvisi nilainya dan didokumentasikan ulang).
- Topologi fisik belum diketahui: satu SMB share, beberapa share, DFS namespace, atau folder gabungan berisi shortcut ke share lain.
- Sumber tidak selalu tersedia: komputer dapat mati, file dapat terkunci/sedang disalin, koneksi dapat putus, file dapat berpindah, izin dapat berubah.
- Client sangat sensitif terhadap biaya awal dan biaya berulang.

**Sistem tidak boleh menjanjikan seluruh isi 4 TB dapat dicari isinya** jika belum benar-benar diproses. Cakupan pencarian harus jujur terhadap apa yang benar-benar sudah diindeks.

---

# 2. PEMISAHAN JALUR INGESTION DAN JALUR PERCAKAPAN

```text
INGESTION:
Sumber LAN → discovery metadata → kebijakan cakupan → snapshot terpilih →
ekstraksi/struktur → review (workflow existing) → embedding/index staging →
aktivasi versi yang disetujui

PERCAKAPAN:
Pertanyaan → autentikasi & scope → hybrid retrieval pada indeks aktif →
evidence validation → generation → claim check → sitasi
```

Jalur percakapan **tidak pernah** mengakses SMB, menyalin file, menjalankan OCR, atau melakukan ingestion sinkron dalam satu request chat — semua promosi arsip tambahan adalah background job dengan status yang dapat dipantau. Ini konsisten dengan pemisahan yang sudah ada di repo ini antara `apps/api` (producer, HTTP) dan `workers/document_worker` (consumer, pekerjaan berat) per ADR-016.

## 2.1 Tiga tingkat cakupan

| Tingkat | Isi | Perlakuan |
| --- | --- | --- |
| **Catalog only** | Metadata file yang terdata dari scan | Tidak ada ekstraksi, embedding, atau snapshot penuh secara otomatis |
| **Candidate/processing** | Dokumen yang dipilih admin masuk cakupan ingestion | Diproses sesuai antrean, anggaran, dan approval — LAN-M2/M3 |
| **Active knowledge** | Versi yang disetujui dan indeksnya lengkap | Dapat menjadi bukti jawaban sesuai hak akses — memakai state machine `DocumentLifecycleStatus` yang sudah ada |

Inventaris metadata (nama folder, nama file, UNC path, statistik) diperlakukan sebagai data sensitif — akses ke daftar ini dibatasi peran yang sama dengan yang mengelola dokumen (`OrgRole.OWNER/ADMIN/EDITOR`), bukan seluruh anggota organisasi.

## 2.2 Reuse eksplisit

Fitur baru **mereuse** — bukan menduplikasi — infrastruktur berikut:
- PostgreSQL, Qdrant, Redis, Celery, MinIO/S3 (`apps/api/app/core/storage.py`) yang sudah ada.
- State machine `DocumentLifecycleStatus` (UPLOADED→...→ACTIVE) — LAN discovery tidak membuat state machine baru, hanya menambah *asal* dokumen (source vs upload langsung).
- Pola retry per-task (`retry_backoff=True, retry_kwargs={"max_retries": 5}`) yang sudah dipakai kelima task pipeline di `workers/document_worker/app/tasks.py`.
- Pola cross-process Core-Table-mirroring (ADR-016) untuk tabel yang perlu ditulis oleh worker.
- Pola "payload Qdrant sebagai prefilter murah + verifikasi live terhadap Postgres" yang sudah terbukti di `apps/api/app/retrieval/service.py` — pola ini yang diperluas untuk konsep staged/active index generation (LAN-M4), bukan dibangun ulang dari nol.

Tidak menambah Kubernetes, cluster, Elasticsearch, atau layanan berlangganan hanya karena ukuran arsip 4 TB.

---

# 3. KONEKTOR SUMBER WINDOWS

Lihat [ADR-020](adr/ADR-020-lan-archive-source-connector.md) untuk keputusan lengkap. Ringkasan kontrak:

```text
SourceAdapter (Protocol):
  paged_scan(subtree, cursor) -> (entries, next_cursor)
  stat(path) -> EntryMetadata
  open_stream(path) -> ByteStream   # dipakai mulai LAN-M2
  check_health() -> HealthStatus
```

Implementasi awal: `LocalFakeAdapter` (uji/dry-run) dan `WindowsUNCAdapter` (produksi, native Windows process membaca UNC langsung — **belum divalidasi terhadap SMB share nyata**, lihat runbook operasi).

Ketentuan wajib:
- Akun sumber read-only; credential tidak pernah masuk repository, frontend, URL, log, atau payload job — hanya *reference* ke secret yang disimpan operator.
- Tidak bergantung pada mapped drive (`Z:`) — hanya UNC (`\\host\share\...`).
- Akses root hanya melalui `SourceRoot` yang didaftarkan admin (allowlist host/share eksplisit), bukan path arbitrer dari pengguna.
- Normalisasi path, penanganan case-insensitivity, deteksi symlink/reparse-point/loop, dan DFS referral didokumentasikan sebagai keterbatasan `os.scandir` (tidak diam-diam disalahtangani).
- Jangan otomatis mengikuti `.lnk`/shortcut ke luar allowlist — share gabungan harus didaftarkan eksplisit satu per satu.
- Error jaringan, akses ditolak, dan file tidak ditemukan adalah **tiga status berbeda**, tidak digabung menjadi satu "gagal."

## 3.1 Discovery

- Enumerasi metadata streaming/paged — tidak pernah memuat seluruh daftar file dalam RAM.
- Checkpoint per root/subtree disimpan di `ScanRun.cursor` (JSONB), memungkinkan resume setelah interupsi.
- Subtree yang gagal dicatat terpisah; scan parsial pada satu subtree **tidak** menyimpulkan penghapusan file di subtree itu.
- mtime/size adalah petunjuk awal, bukan bukti isi tidak berubah — hash isi hanya dihitung untuk file yang benar-benar dipromosikan/kandidat berubah (LAN-M2), bukan seluruh 4 TB setiap malam.
- Watcher (jika ada di masa depan) hanya akselerator; scan/recovery penuh tetap diperlukan setelah overflow atau reconnect.
- Interval scan, jadwal per root, dan concurrency harus configurable (lihat §9).

---

# 4. MODEL DATA DAN STATUS

Tabel baru (LAN-M1), tenant-scoped, additive migration — lihat `apps/api/app/sources/models.py`:

| Tabel | Isi |
| --- | --- |
| `source_roots` | tenant, jenis sumber, root/host+share, credential reference, scope policy, health |
| `source_entries` | identitas sumber, normalized path, size, mtime, last_seen_scan, discovery/access status |
| `scan_runs` | cakupan root/subtree, cursor/checkpoint, status, error, statistik |

Milestone berikutnya menambah (bukan LAN-M1, dicatat di sini agar skema akhir konsisten):
- `IngestionJob`/stage tambahan untuk promosi (LAN-M2) — mereuse `ProcessingJob` yang sudah ada sejauh mungkin, hanya menambah field yang benar-benar baru (idempotency key lintas scan).
- `IndexGeneration` (LAN-M4) — kesiapan lexical/vector/evidence dan referensi generation aktif, dibangun di atas pola prefilter+verifikasi `retrieval/service.py` yang sudah ada.
- `AccessPolicy`/revisinya (LAN-M4) — jika mode ACL Windows diperlukan.
- `UsageLedger`/`Budget` (LAN-M5) — estimasi, reservation, pemakaian aktual per tenant/source/job/stage/provider.

## 4.1 Pemisahan status

1. **Kesehatan sumber**: `healthy` / `unreachable` / `access_denied` / `partial` — pada `SourceRoot`/`ScanRun`.
2. **Discovery**: `present` / `missing_candidate` / `confirmed_missing` — pada `SourceEntry`. File hanya dapat dikonfirmasi hilang setelah scan relevan berhasil dan grace period terpenuhi.
3. **Ingestion**: `queued` / `running` / `retry_wait` / `failed` / `paused_budget` / `paused_capacity` / `completed` — LAN-M2+, mereuse `ProcessingJobStatus` yang ada sejauh cocok.
4. **Approval/version**: `pending` / `approved` / `rejected` / `active` / `superseded` / `withdrawn` — **tidak diubah**, tetap `DocumentLifecycleStatus` yang sudah ada.

Status sumber offline dan status dokumen ditarik **tidak boleh dicampur** — sebuah source yang unreachable tidak berarti dokumennya ditarik dari knowledge base aktif; revocation eksplisit (LAN-M4) membatasi akses tanpa menunggu siklus ingestion.

---

# 5. PEMROSESAN PDF DAN WORD (LAN-M3)

Pipeline yang sudah ada **dipertahankan penuh**: Layout → Generic Structure → StructuralRegion → Specialized Interpretation → Canonical Hierarchical Tree (ADR-014). Tidak ada perubahan pada pipeline ini di LAN-M1.

Temuan audit yang relevan untuk LAN-M3 nanti:
- Docling saat ini **hanya dikonfigurasi untuk PDF** (`format_options={InputFormat.PDF: ...}` di `docling_adapter.py`) — dukungan DOCX/DOC adalah pekerjaan baru sepenuhnya, bukan mengaktifkan opsi yang sudah ada.
- Eskalasi OCR bertingkat per halaman **sudah ada** (Level 1 native → Level 2 layout/table → Level 3 full OCR, `docling_adapter.py`/`pipeline.py`) — tidak perlu dibangun ulang untuk PDF.
- Contextual prefix chunk **sudah deterministik** (concat title/structural_path/ancestor, `contextual_text.py`) — TIDAK memanggil LLM per chunk. Ini sudah memenuhi larangan §8 prompt tanpa perubahan.
- DOCX tidak memiliki nomor halaman stabil — evidence untuk DOCX harus memakai structural path, bukan nomor halaman asli, kecuali ada snapshot PDF terverifikasi.
- DOC lama memerlukan converter terisolasi (macro dan external resource dinonaktifkan, batas waktu/memori/subprocess) — dievaluasi di LAN-M3, bukan dipilih sekarang.

---

# 6. ANTREAN, RELIABILITAS, DAN AKTIVASI VERSI (LAN-M2/M3)

Temuan audit: task Celery yang sudah ada punya `retry_backoff`+`max_retries` dan `ProcessingJob.attempts`, tetapi **belum ada lease/heartbeat/fencing** — worker yang crash di tengah stage tidak punya mekanisme ownership yang mencegah duplikasi/pekerjaan hilang. Ini dicatat sebagai gap yang harus ditutup sebelum promosi/snapshot (LAN-M2) berjalan produksi, bukan hanya untuk discovery (LAN-M1, yang idempoten by design — re-scan tanpa perubahan tidak menulis baris baru).

Prinsip yang mengikat milestone berikutnya (dicatat di sini agar tidak lupa saat LAN-M2+ dikerjakan):
- Pesan Redis/Celery berisi ID job dan reference objek, bukan byte file.
- Aktivasi versi baru hanya setelah lexical index, vector index, evidence, dan citation references lengkap — memakai pola commit tunggal yang sudah ada di `_index_document_async` (`tasks.py`), diperluas dengan reconciler/outbox untuk memulihkan partial failure Qdrant/MinIO (Postgres tidak mencakup keduanya dalam satu transaksi — gap yang sudah ada hari ini, bukan regresi baru).

---

# 7. RETRIEVAL, AKSES, DAN SITASI (LAN-M4)

Tidak ada perubahan pada `apps/api/app/retrieval/service.py` di LAN-M1. Prinsip yang mengikat LAN-M4:
- Scope tenant/knowledge-space yang sudah konsisten di retrieval, lexical search, parent expansion, reranker, evidence fetch, cache, viewer, download — perluasan harus tetap konsisten di semua jalur ini, bukan hanya retrieval utama.
- Service account yang membaca seluruh share **bukan bukti** semua pengguna aplikasi berhak melihat seluruh dokumen — default awal memakai curated root dengan izin aplikasi eksplisit (`OrgRole`), bukan mengklaim menyamai ACL SMB/NTFS.
- Jika mode ACL Windows penuh diperlukan client, itu adalah pekerjaan LAN-M4 tersendiri (pemetaan identitas/group, freshness sinkronisasi, kebijakan fail-closed saat sinkronisasi tidak dapat dipercaya).
- Viewer sumber melalui endpoint terautentikasi — tidak pernah mengandalkan browser membuka UNC path langsung.

---

# 8. ANGGARAN DAN BIAYA (LAN-M5)

Temuan audit: **tidak ada** budget/quota enforcement hari ini — hanya rate limiting berbasis jumlah request (slowapi, per IP/user) yang tidak terkait dollar. `QueryLog.estimated_cost_usd` hanya terisi dari jalur chat; tidak ada pelacakan biaya token embedding atau halaman OCR di sisi ingestion. Dua konstanta harga (`LLM_FAST_COST_PER_1K_TOKENS`, `LLM_STRONG_COST_PER_1K_TOKENS`) adalah float polos tanpa currency/tanggal berlaku/versi.

LAN-M5 harus membangun (tidak dikerjakan di LAN-M1, dicatat di sini sebagai target arsitektur):
- Usage ledger per tenant/source/job/stage/provider (bukan hanya per query chat).
- Tarif configurable dengan currency, unit, tanggal berlaku, sumber — bukan angka yang di-hardcode dari percakapan.
- Admission control atomik: reserve estimasi sebelum dispatch, settle setelah selesai, release yang tidak terpakai — mencegah race antarworker dan double charge saat retry.
- Budget ingestion terpisah dari budget chat.
- Unknown price tidak dianggap nol; strict-budget mode menahan paid stage sampai tarif tersedia.

Estimasi biaya awal (dipakai LAN-M6 untuk pilot) **tidak boleh** mengonversi 4 TB mentah langsung menjadi token — wajib sampling per kelompok dokumen (PDF teks/pindai/Word/ukuran) sebelum proyeksi biaya total dibuat.

---

# 9. KONFIGURASI DAN UI (bertahap per milestone)

Konfigurasi LAN-M1 (additive ke `Settings` yang sudah ada di `apps/api/app/core/config.py` dan `workers/document_worker/app/core/config.py`):

```text
CONNECTOR_ENABLED
CONNECTOR_ALLOWED_HOSTS / CONNECTOR_ALLOWED_SHARES
SCAN_PAGE_SIZE
SCAN_STABILITY_WINDOW_SECONDS   # didefinisikan sekarang, dipakai mulai LAN-M2
MAX_FILE_SIZE_MB                # nilai direvisi ke ~100, tetap per-file
```

Semua nilai awal berlabel **pilot**, bukan default production yang sudah dibenchmark — didokumentasikan di `.env.example` dengan komentar yang jelas. UI admin (daftar sumber, status scan, coverage) ditambahkan bertahap mulai LAN-M1 (daftar sumber + status scan minimal) hingga LAN-M5 (budget/coverage lengkap) — tidak mengubah tampilan chat yang sudah ada.

---

# 10. RUJUKAN MILESTONE DAN PENGUJIAN

Rincian milestone (LAN-M1..LAN-M6), acceptance criteria per milestone, dan skenario pengujian wajib: lihat `docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md`. Progress aktual: `docs/LAN_ARCHIVE_PROGRESS.md`. Panduan operasi Windows: `docs/operations/LAN_CONNECTOR_RUNBOOK.md`. Rencana pilot/evaluasi: `docs/evaluation/LAN_ARCHIVE_PILOT_PLAN.md`.
