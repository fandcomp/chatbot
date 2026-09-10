# Prompt Claude Code: pembaruan chatbot untuk arsip Windows LAN hingga 4 TB

Salin seluruh bagian di antara `BEGIN PROMPT` dan `END PROMPT` ke Claude Code yang berjalan pada root repositori proyek. Prompt ini memerintahkan audit seluruh kebutuhan, lalu implementasi satu milestone pertama. Bagian paling bawah menyediakan perintah untuk melanjutkan milestone berikutnya sesuai aturan proyek.

---

## BEGIN PROMPT

Kamu bertindak sebagai engineer utama untuk merevisi dan mengembangkan proyek chatbot yang SUDAH ADA. Kerjakan perubahan nyata pada repositori, lengkap dengan dokumentasi, migrasi yang diperlukan, dan pengujian. Jangan membuat proyek baru atau mengganti stack tanpa alasan yang dibuktikan dari audit.

### 1. Konteks dan tujuan

Proyek: Self-Service Regulatory Knowledge Assistant, platform multi-tenant dengan Adaptive Structure-Aware Contextual Hybrid RAG.

Stack yang tercantum dalam CLAUDE.md:
- Next.js dan TypeScript untuk frontend.
- FastAPI dan Python untuk backend.
- PostgreSQL, Qdrant, Redis, Celery, S3/MinIO.
- Voyage untuk embedding/reranking.
- GPT-OSS 20B/120B melalui Groq dan Hugging Face gateway.

Verifikasi seluruh informasi tersebut pada kode aktual. Bedakan fitur yang direncanakan, sudah diimplementasikan, belum diuji, dan sudah terbukti berjalan.

Kebutuhan baru client:
1. Sumber pengetahuan berupa PDF, DOCX, dan kemungkinan DOC lama.
2. Sebagian file dapat mencapai sekitar 100 MB. Jadikan batas per file configurable, jangan menyamakan batas file dengan ukuran total koleksi.
3. Total arsip dapat mencapai 4 TB dan bertambah.
4. File berada pada folder sharing Windows melalui LAN. Lokasi fisiknya dapat tersebar pada beberapa komputer meskipun terlihat seperti satu folder.
5. Topologi sebenarnya belum diketahui: satu SMB share, beberapa SMB share, DFS namespace, atau folder yang berisi shortcut.
6. Komputer sumber dapat mati, file dapat terkunci atau sedang disalin, koneksi dapat terputus, file dapat dipindah, dan izin dapat berubah.
7. Client sangat memperhatikan biaya awal dan biaya berulang.
8. Chatbot harus tetap cepat, berbasis bukti, memiliki sitasi yang dapat diperiksa, serta menjaga tenant isolation dan hak akses.

Tujuan: mendukung inventaris arsip hingga 4 TB, mengindeks dokumen yang relevan secara bertahap, memperbarui indeks secara incremental, dan membatasi biaya. Jangan menjanjikan seluruh isi 4 TB dapat dicari jika belum diproses. Jika seluruh arsip wajib dicari isinya, sediakan rencana full-content ingestion bertahap dengan estimasi terukur.

### 2. Baca repositori sebelum mengubahnya

Baca terlebih dahulu:
- CLAUDE.md dan AGENTS.md yang berlaku.
- docs/MASTER_DEVELOPMENT_SPEC.md.
- docs/ADDENDUM_ADAPTIVE_MIXED_STRUCTURE_DOCUMENTS.md.
- docs/adr/ADR-014-region-based-generic-structure.md dan ADR terkait.
- .env.example, dependency manifests/lockfiles, deployment configuration, migrasi, dan tests.
- Implementasi auth/organizations, documents, ingestion, parsing, chunking, indexing, retrieval, citations, verification, gateway, worker, dan UI dokumen.

Jika dokumen rujukan hilang, jangan mengarang isinya. Catat file yang hilang, lanjutkan audit yang aman, dan jelaskan keputusan mana yang belum dapat ditetapkan. Jangan mencetak secrets atau isi .env pribadi.

Jalankan git status sebelum edit. Pertahankan perubahan pengguna. Jangan reset, menghapus, atau menimpa perubahan yang tidak berkaitan. Jangan commit langsung ke main. Ikuti workflow branch/PR repositori; jangan push atau deploy tanpa otorisasi yang sesuai.

Pertahankan aturan inti:
- Tidak menggunakan GraphRAG atau Neo4j.
- Tidak fine-tuning untuk memasukkan pengetahuan.
- Tidak menjadikan LLM lokal sebagai dependensi produksi tanpa revisi keputusan arsitektur yang eksplisit.
- Tidak fixed-size chunking sebagai strategi utama.
- Tidak semantic-only retrieval, regex-only parsing, atau seluruh dokumen ke prompt.
- Tidak mengaktifkan dokumen tanpa approval.
- Tidak membiarkan LLM mengarang sitasi atau menentukan status hukum.
- Tetap evidence-first dan generic-structure-first.
- Tetap menggunakan LLMGateway, EmbeddingGateway, RerankerGateway.
- Isi dokumen merupakan data tidak tepercaya, bukan instruksi kepada sistem.
- Tidak menghapus diagram, lampiran visual, tabel, dan hierarki untuk mengurangi biaya.

### 3. Cara bekerja dan batas milestone

Pada eksekusi pertama:
1. Audit implementasi dan buat gap matrix berbasis bukti file/kode.
2. Buat ADR dan addendum yang diperlukan, lalu rencana milestone lengkap beserta acceptance criteria.
3. Implementasikan hanya milestone pertama yang belum selesai dan dependensinya sudah tersedia.
4. Jalankan pengujian yang relevan dan laporkan hasil aktual.
5. Perbarui dokumen progress agar sesi berikutnya dapat melanjutkan tanpa audit ulang dari nol.
6. Berhenti pada batas satu milestone sesuai aturan proyek. Jangan berhenti hanya setelah memberikan rencana apabila implementasi milestone tersebut dapat dikerjakan.

Lakukan keputusan teknis rutin secara mandiri. Jika akses LAN atau credential client belum tersedia, buat implementasi yang dapat diuji dengan adapter lokal/fake dan prosedur uji Windows yang jelas. Tandai pengujian SMB nyata sebagai belum dijalankan, jangan mengklaim berhasil.

Jangan menjalankan full ingestion 4 TB, memanggil API berbayar dalam jumlah besar, membeli layanan, atau mengubah sumber Windows secara otomatis. Gunakan dry-run dan fixture pada development. Konfigurasi production memakai nilai yang diberikan operator, bukan angka anggaran yang kamu karang.

### 4. Arsitektur target berbiaya terkendali

Pisahkan jalur ingestion dari jalur percakapan.

Ingestion:
Sumber LAN → discovery metadata → kebijakan cakupan → snapshot terpilih → ekstraksi/struktur → review sesuai workflow yang ada → embedding/index staging → aktivasi versi yang telah disetujui.

Percakapan:
Pertanyaan → autentikasi dan scope → hybrid retrieval pada indeks aktif → evidence validation → generation → claim check → sitasi.

Jangan akses SMB, menyalin file, menjalankan OCR, atau melakukan ingestion sinkron dalam request chat. Promosi arsip tambahan harus menjadi background job dengan status yang jelas.

Gunakan tiga tingkat:
| Tingkat | Isi | Perlakuan |
| --- | --- | --- |
| Catalog only | Metadata file yang diizinkan untuk didata | Tidak otomatis ekstraksi, embedding, atau snapshot penuh. |
| Candidate/processing | Dokumen yang dipilih masuk cakupan | Diproses sesuai antrean, anggaran, dan approval. |
| Active knowledge | Versi yang disetujui dan indeksnya lengkap | Dapat menjadi bukti jawaban sesuai hak akses. |

Inventaris metadata juga sensitif. Batasi siapa yang dapat melihat nama folder, nama file, UNC path, dan statistik unit lain.

Reuse PostgreSQL, Qdrant, Redis, Celery, dan storage yang ada. Mulai dari deployment lokal sederhana. Jangan menambah Kubernetes, cluster, Elasticsearch, atau layanan berlangganan hanya karena arsip berukuran 4 TB.

### 5. Konektor folder Windows dan discovery

Buat interface sumber yang sesuai pola repositori. Contoh operasi: list_entries/paged_scan, stat, open_stream, check_health, dan kemampuan permissions jika tersedia. Nama interface bukan kewajiban; hindari abstraksi berlebihan.

Implementasi awal harus mendukung:
- Adapter lokal/fake untuk pengujian.
- Jalur produksi UNC/SMB yang konkret dan terdokumentasi.
- Multi-root source dengan tenant dan access scope eksplisit.
- Satu konektor pusat pada host yang selalu menyala sebagai pilihan awal.

Bandingkan dua opsi dalam ADR:
1. Windows Service yang membaca UNC dengan akun layanan lalu mengirim metadata dan file terpilih ke backend melalui endpoint terautentikasi.
2. Worker backend dengan mount SMB yang disediakan sistem operasi.

Pilih berdasarkan OS/deployment yang ditemukan. Windows Service hanya sebagai konektor jika Celery/backend berjalan di Linux. Jangan mengasumsikan mapped drive Windows atau UNC otomatis tersedia dalam container Linux. Jika jaringan nyata tidak tersedia, buat jalur pemasangan yang dapat dijalankan operator dan pengujian adapter di development.

Ketentuan:
- Akun sumber read-only dan credential tidak masuk repository, frontend, URL, log, atau payload job.
- Jangan bergantung pada mapped drive pengguna seperti Z:.
- Akses root hanya melalui konfigurasi admin yang diizinkan, bukan path arbitrer dari pengguna.
- Tentukan allowlist host/share, normalisasi path, penanganan case-insensitivity, traversal, symlink/reparse point, loop, dan referral DFS.
- Jangan otomatis mengikuti .lnk, URL, atau shortcut ke sumber di luar allowlist.
- Daftarkan beberapa share secara eksplisit jika folder gabungan hanya berisi shortcut.
- Jika memakai connector agent, scope credential agent ke tenant/root tertentu; backend tidak mempercayai tenant_id kiriman agent tanpa verifikasi.
- Network error, access denied, dan file not found harus menjadi status berbeda.

Discovery:
- Enumerasi metadata secara streaming/paged; jangan muat seluruh daftar file dalam RAM.
- Simpan checkpoint per root/subtree dan identitas scan.
- Catat subtree yang gagal. Scan parsial tidak dapat digunakan untuk menyimpulkan penghapusan di subtree tersebut.
- Metadata menjadi pemeriksaan awal; hash isi untuk file terpilih/kandidat perubahan, bukan seluruh 4 TB setiap malam.
- mtime dan size adalah petunjuk, bukan bukti mutlak bahwa isi tidak berubah. Sediakan verifikasi isi terjadwal pada koleksi aktif atau sesuai kemampuan version/file ID sumber.
- Watcher hanya akselerator. Recovery/rescan diperlukan setelah overflow, reconnect, atau kejadian yang hilang.
- Interval scan, jadwal per root, bandwidth, dan concurrency configurable.
- Hindari full content reread berulang. Rate-limit enumerasi dan transfer saat jam kerja.

### 6. Transfer, snapshot, dan penyimpanan

- Salin hanya dokumen yang dipromosikan ke cakupan ingestion. Jangan mirror seluruh arsip otomatis.
- Transfer streaming dengan buffer terbatas, timeout, checksum, dan staging object/file.
- Tunggu metadata stabil pada dua pemeriksaan terpisah sebelum menyalin; abaikan file lock/temp seperti ~$*.docx.
- Periksa metadata/versi sebelum dan sesudah penyalinan. Jika berubah, buang hasil staging yang tidak sah dan retry terbatas.
- Metadata stabil bukan jaminan snapshot konsisten. Gunakan kemampuan lock/snapshot/version sumber bila tersedia, dan dokumentasikan keterbatasan pemeriksaan best-effort.
- Jangan publish snapshot parsial. Finalisasi hanya setelah verifikasi selesai.
- Transfer terputus boleh restart dari awal untuk file terpilih. Implementasikan resume hanya jika validasi versi/offset menjamin file yang sama; jangan gabungkan byte dua versi.
- Simpan snapshot immutable untuk dokumen aktif jika sumber tidak memiliki versioning yang dapat diandalkan.
- MinIO lokal atau storage abstraction existing tetap dipakai. Jika sumber memiliki immutable versioning, dokumentasikan alternatif referensi sumber dan dampak availability-nya.
- Simpan manifest provenance, hash, parser version, dan snapshot reference.
- Jangan membuat semua halaman menjadi PNG permanen atau mengonversi seluruh arsip Word sebelum dibutuhkan.
- Temp artifact harus memiliki TTL, quota, dan cleanup. Cleanup tidak boleh menghapus objek yang masih direferensikan versi aktif/retained.
- Deduplikasi konten dan referensi dipisahkan. File identik dengan owner/izin/status berbeda tidak boleh kehilangan identitas sumbernya.
- Deduplikasi lintas tenant dinonaktifkan pada implementasi awal.
- Terapkan disk watermark: hentikan/pause ingestion saat ruang rendah, pertahankan layanan chat selama masih aman.
- Tetapkan kebijakan retensi versi dan backup. Snapshot bukan pengganti backup; jangan menghapus sumber client.

### 7. Model data dan status

Reuse dan perluas tabel yang sudah ada. Jangan menduplikasi domain documents/version/approval jika sudah tersedia.

Konsep yang harus terwakili:
- SourceRoot/Connector: tenant, jenis sumber, root, reference credential, scope, policy, health.
- SourceEntry: source ID, identitas sumber yang tersedia, normalized path, size, mtime, last_seen_scan, discovery/access status.
- ScanRun: cakupan root/subtree, cursor/checkpoint, completion status, error, statistik.
- Document dan DocumentVersion: identitas logis, immutable content hash, snapshot, metadata, structural tree, approval, effective/legal metadata yang diverifikasi.
- IngestionJob/Stage: idempotency key, stage, checkpoint, attempt, lease, heartbeat, error category.
- IndexGeneration: kesiapan lexical/vector/evidence dan active generation reference.
- AccessPolicy/Revision: cakupan yang diizinkan dan revisi izin.
- UsageLedger/Budget: estimasi, reservation, pemakaian aktual, provider/model/stage.

Pisahkan status:
1. Kesehatan sumber: healthy/unreachable/access_denied/partial.
2. Discovery: present/missing_candidate/confirmed_missing.
3. Ingestion: queued/running/retry_wait/failed/paused_budget/paused_capacity/completed.
4. Approval/version: pending/approved/rejected/active/superseded/withdrawn, sesuai state machine existing.

Jangan membuat status tunggal yang mencampurkan sumber offline dan dokumen ditarik. File hilang hanya dapat dikonfirmasi setelah scan relevan berhasil dan kebijakan grace/review dipenuhi. Revocation eksplisit harus membatasi akses tanpa menunggu siklus ingestion biasa.

### 8. Pemrosesan PDF dan Word

Pertahankan pipeline:
Layout → Generic Structure → StructuralRegion → Specialized Interpretation → Canonical Hierarchical Tree.

PDF:
- Ekstrak teks dan layout langsung jika berkualitas.
- Evaluasi kebutuhan OCR per halaman/wilayah menggunakan sinyal terukur.
- Tangani PDF campuran, teks rusak, tabel, dan lampiran visual.
- Hindari OCR/VLM setiap halaman secara default.

Word:
- Ekstrak heading, paragraf, nested list, tabel, caption, gambar, serta elemen penting lainnya.
- Tangani DOC lama melalui converter terisolasi jika parser tidak mendukung.
- Nonaktifkan macro dan pengambilan external resource saat konversi. Batasi waktu, memori, dekompresi, dan subprocess.
- DOCX tidak memiliki nomor halaman stabil yang dapat diasumsikan. Gunakan structural path atau snapshot PDF yang telah diverifikasi, dengan nomor halaman dinyatakan sebagai halaman snapshot.
- Jangan mengklaim dukungan DOC, OCR, atau layout sempurna hanya karena library terpasang. Uji fixtures representatif.

Pilih parser yang sudah ada jika memadai. Evaluasi Docling/alat lain hanya jika ada gap konkret, lisensi sesuai, serta dependency dan model artifact dapat dikelola. Jangan memperkenalkan stack parser kedua tanpa alasan.

Chunking:
- Struktur dokumen menjadi dasar batas chunk, ukuran/token limit menjadi pengaman.
- Pertahankan hubungan induk-anak, tabel multipage, daftar bertingkat, dan rujukan silang.
- Pemrosesan per batch halaman harus merekonsiliasi struktur lintas batch.
- Bangun contextual prefix dari judul, heading path, ancestor, caption, dan metadata lebih dahulu.
- Jangan panggil LLM untuk membuat konteks pada setiap chunk secara default.
- Cache key embedding harus mencakup teks final yang di-embed, contextual prefix, model/revision, dimension, normalisasi, dan versi strategi terkait. Parent heading berubah dapat membatalkan cache meski teks anak sama.
- Perubahan model/dimensi memerlukan generasi indeks baru dan jalur migrasi. Jangan mencampur vektor yang tidak kompatibel.

### 9. Antrean dan reliabilitas

Pisahkan antrean logical discovery/transfer, parsing/OCR, dan embedding/indexing sesuai kebutuhan. Worker berat tidak boleh menghabiskan seluruh kapasitas chat/database.

- Pesan Redis/Celery berisi ID job dan reference objek, bukan byte file atau seluruh teks dokumen.
- Stage idempoten dengan key yang mempertimbangkan document version dan pipeline configuration.
- Retry exponential backoff, jitter, dan maksimum percobaan; bedakan error transient dari permanent.
- Worker crash tidak boleh menyebabkan duplicate activation atau dokumen hilang.
- Gunakan lease/heartbeat dan fencing/ownership yang sesuai agar worker lama tidak menimpa pekerjaan worker pengganti.
- Jangan menganggap acks_late memberikan exactly-once delivery.
- Checkpoint per tahap, pembersihan pekerjaan orphan, dan fasilitas retry stage yang gagal.
- Queue admission/backpressure saat antrean, disk, provider rate limit, atau budget mencapai batas.
- Source per tenant memiliki quota agar satu tenant tidak memonopoli worker.

Aktivasi versi:
- Indeks baru ditulis sebagai staging generation yang belum searchable bagi chat.
- Aktivasi hanya setelah approval serta lexical index, vector index, evidence, dan citation references lengkap.
- PostgreSQL menjadi sumber status aktif/otorisasi yang jelas; jelaskan bagaimana retrieval memfilter generation yang eligible dan memverifikasi ulang kandidat sebelum generasi.
- Jangan mengasumsikan transaksi PostgreSQL mencakup Qdrant dan MinIO. Gunakan outbox/reconciler atau pola existing untuk memulihkan partial failure.
- Dalam satu jawaban, bukti harus konsisten dengan versi/generation yang dipilih. Penghapusan versi lama tertunda sampai tidak lagi diperlukan.
- Legal status dan approval tidak ditentukan dari mtime atau nama file saja.

### 10. Retrieval, akses, dan sitasi

- Pertahankan hybrid retrieval. Reuse lexical search existing; audit tokenisasi bahasa Indonesia dan istilah regulasi.
- Qdrant memakai filter tenant, scope, dan generation/status yang dikelola server.
- Scope berlaku juga pada lexical search, parent expansion, reranker, evidence fetch, cache, export, viewer, dan download.
- Jangan memberikan potongan terlarang kepada LLM/reranker lalu memfilternya setelah jawaban selesai.
- Service account yang membaca seluruh share bukan bukti semua pengguna berhak melihat seluruh dokumen.
- Default awal dapat memakai curated root dengan izin aplikasi yang eksplisit. Jangan mengklaim sudah menyamai ACL SMB/NTFS jika hanya memakai ACL aplikasi.
- Untuk mode ACL Windows, petakan identitas/group, deny/inheritance yang relevan, dan freshness. Jika sinkronisasi ACL tidak dapat dipercaya, jangan diam-diam memperluas akses.
- Bedakan source unavailable dengan permission revoked. Tetapkan kebijakan stale permission/fail-closed berdasarkan mode akses, serta uji.
- Cache key mencakup tenant, scope/ACL revision, knowledge generation, query/context yang diperlukan, dan konfigurasi model. Invalidasi pada revocation/withdrawal/aktivasi versi.
- Reranking bersyarat dengan batas kandidat/token dan alasan yang tercatat. Jangan rerank setiap query otomatis.
- Jika bukti tidak cukup, nyatakan keterbatasan cakupan. Jangan menjawab dari pengetahuan model untuk menutupi dokumen yang belum diindeks.
- Sitasi dibuat dari metadata/evidence ID yang tervalidasi, bukan string lokasi karangan LLM.
- Viewer sumber melalui endpoint terautentikasi; jangan mengandalkan browser membuka UNC dan jangan membocorkan path internal kepada pengguna tanpa izin.

### 11. Anggaran dan pencatatan biaya

Implementasikan cost control nyata, bukan hanya dashboard.

Catat per tenant, source, job, stage, dan provider/model:
- File/byte dibaca dan dipindahkan.
- Halaman diproses dan halaman OCR/VLM.
- Token embedding/query/context/rerank/LLM input-output yang tersedia dari provider.
- Waktu CPU/worker, memori puncak jika dapat diukur, ukuran artifact dan indeks.
- Cache hit/miss, retries, dedup saving, serta failed requests yang tetap ditagihkan jika dapat diketahui.
- Estimated cost, reserved cost, dan actual/reconciled cost sebagai nilai yang berbeda.

Tarif harus configurable dan memiliki currency, unit, tanggal berlaku, serta sumber. Jangan hardcode harga dari percakapan sebagai harga permanen. Jangan mengasumsikan free tier selalu ada atau tarif gateway sama dengan provider langsung. Jika usage aktual tidak tersedia, tampilkan estimate/unknown dengan jelas.

Budget:
- Batas harian/bulanan per tenant dan batas satu ingestion run.
- Budget ingestion terpisah dari budget chat agar ingestion tidak menghabiskan seluruh layanan.
- Admission control atomik: reserve estimasi konservatif sebelum dispatch; settle setelah selesai; release reservation yang benar-benar tidak dipakai.
- Cegah race antarworker dan double charge ledger akibat retry.
- Unknown price tidak dianggap nol. Dalam strict-budget mode, pause paid stage sampai tarif tersedia.
- Retry tetap mengikuti budget dan aturan rate limit.
- Soft threshold memberikan notifikasi UI; hard threshold menahan job berikutnya. Jelaskan bahwa request yang sudah dikirim tetap dapat ditagihkan dan bagaimana buffer mengurangi overshoot.
- Budget pause mempertahankan checkpoint dan dapat dilanjutkan setelah operator memperbarui anggaran.
- Tidak ada fallback ke model/provider lebih mahal tanpa policy eksplisit.
- Development default memakai mock provider dan tidak memanggil layanan berbayar dari automated tests.
- Jangan log isi dokumen rahasia atau prompt lengkap sebagai cara menghitung biaya.

Perkiraan:
Embedding = total token input embedding / 1.000.000 × tarif per juta token.
LLM = input billable × tarif input + output billable × tarif output, sesuai satuan provider; masukkan reasoning bila ditagihkan dan gateway fee jika berlaku.
Raw dense vectors = jumlah chunk × dimensi × bytes per elemen, belum termasuk HNSW, payload, sparse index, WAL, snapshot, dan backup.
Total operasi = API + listrik + storage/backup + hardware amortization + maintenance.

Jangan mengonversi 4 TB mentah langsung menjadi jumlah token. Sampel per kelompok PDF teks/pindai/Word/ukuran/unit, hitung hasil ekstraksi, dan buat rentang estimasi. Rencana awal sampel 300–500 dokumen dapat disesuaikan akses/budget; jangan menganggap angka ini menjamin representativitas statistik.

### 12. Konfigurasi dan UI

Tambahkan konfigurasi tervalidasi pada mekanisme settings existing dan .env.example tanpa secrets. Gunakan nama yang konsisten dengan proyek. Kelompok konfigurasi minimal:
- Connector enabled, allowed roots/hosts, source mode, service credential reference.
- Scan schedule, subtree scope, scan page size, stability window, grace period, transfer timeout dan bandwidth.
- Maximum file size, pages, decompressed size, temp quota, minimum free disk.
- Transfer/parser/OCR/embedding concurrency, max retries, lease timeout, queue limit.
- Snapshot retention dan cleanup policy.
- Provider/model/dimension/revision, token batch limit, rate limits.
- Daily/monthly/run budget, strict-budget mode, cost rate configuration, ingestion/chat allocation.
- Feature flags catalog, source sync, incremental ingestion, dan production rollout.

Jangan memberi production-ready default yang belum dibenchmark. Nilai awal low-concurrency harus diberi label pilot dan dapat diubah. Dokumentasikan MB/TB versus MiB/TiB untuk batas ukuran.

UI minimum yang ditambahkan bertahap:
- Daftar sumber, status koneksi, last successful scan, partial scan, dan error yang dapat ditindaklanjuti.
- Daftar file dengan status catalog/candidate/processing/pending approval/active/failed.
- Pilih sumber/folder untuk cakupan ingestion beserta estimasi sebelum menjalankan batch.
- Progress pekerjaan, pause/resume/retry dan alasan penundaan.
- Review versi baru dan aktivasi sesuai workflow existing.
- Pemakaian dan sisa budget dengan pemisahan estimated/actual.
- Cakupan pengetahuan: jumlah file catalog vs aktif dan waktu pembaruan.
- Jangan menampilkan persentase coverage seluruh arsip jika scan belum lengkap; jangan menganggap byte coverage sama dengan content coverage.
- Jangan mengubah tampilan chat yang sudah ada tanpa kebutuhan langsung.

### 13. Pengujian dan acceptance criteria

Gunakan fixture sintetis yang tidak memuat data client. Pengujian wajib menguji perilaku/risk, bukan sekadar mock yang mengulang implementasi.

| Skenario | Hasil yang wajib |
| --- | --- |
| Discovery catalog-only | Tidak memanggil OCR, embedding, LLM, atau menyalin seluruh file. |
| Source offline | Tidak menandai semua file sebagai terhapus. |
| Satu subtree access denied | Scan parsial tercatat; file subtree itu tidak dianggap hilang. |
| File sedang berubah/disalin | Snapshot parsial tidak aktif; ada retry yang terbatas. |
| Sinkronisasi ulang tanpa perubahan | Tidak ada versi/embedding baru yang tidak diperlukan. |
| Rename tanpa perubahan isi | Provenance diperbarui tanpa komputasi isi berulang bila identitas dapat dibuktikan. |
| File identik dengan izin berbeda | Komputasi boleh dipakai ulang dalam scope aman, akses tidak tergabung. |
| Parent heading berubah | Cache contextual embedding yang terpengaruh dibatalkan. |
| Worker mati di tengah stage | Dapat dipulihkan tanpa duplikasi aktivasi. |
| Qdrant atau storage gagal saat publikasi | Tidak ada versi setengah jadi yang terlihat pada chat. |
| Versi baru belum disetujui | Tidak masuk bukti jawaban. |
| Izin dicabut | Retrieval, cache, viewer, dan download mematuhi revocation. |
| Dua tenant memakai nama/path/hash serupa | Tidak ada kebocoran metadata, isi, maupun cache. |
| Budget habis dengan banyak worker | Admission atomik menahan pekerjaan baru tanpa race pemborosan. |
| Budget ditambah | Job melanjutkan dari checkpoint yang benar. |
| Disk rendah | Ingestion berhenti terkontrol dan temp tidak tumbuh tanpa batas. |
| PDF campuran teks/pindai | OCR selektif; semua wilayah penting tetap terwakili. |
| DOCX dengan tabel dan list bertingkat | Struktur dan sitasi dapat dilacak ke bukti yang benar. |
| Query menyangkut catalog-only file | Sistem jujur bahwa isi belum siap, tidak mengarang jawabannya. |
| Dokumen mengandung prompt injection | Isi diperlakukan sebagai bukti teks, tidak mengubah instruksi sistem. |

Performance validation:
- Generator metadata banyak entri untuk memeriksa pagination, checkpoint, bounded memory, dan query database.
- File besar sintetis secara streaming bila diperlukan. Jangan membuat dataset 4 TB hanya untuk test.
- Ukur p50/p95 chat dan resource use ketika ingestion idle versus aktif pada mesin uji yang sama.
- Ukur OCR throughput, embedding throughput, transfer LAN aktual jika tersedia, dan retry rate.
- Uji retrieval pada pertanyaan regulasi Indonesia, lookup angka/pasal/nama, lintas bagian, serta pertanyaan tanpa bukti.
- Bandingkan model embedding/dimensi/quantization hanya jika ada anggaran dan dataset evaluasi; pertahankan kualitas sebagai gate.
- Jangan mengklaim telah lulus skala 4 TB dari pengujian metadata saja. Pisahkan hasil terukur, proyeksi, dan uji client yang masih diperlukan.
- Catat baseline dan tetapkan ambang kinerja pilot berdasarkan hardware, bukan janji angka latensi tanpa pengukuran.

### 14. Milestone yang disarankan

Sesuaikan penomoran dengan milestone existing, jangan menimpa milestone lama. Gunakan prefix tambahan seperti LAN-M1 jika diperlukan.

**LAN-M1: audit, fondasi sumber, dan katalog tanpa biaya AI**
- Audit/gap matrix, ADR, addendum, rencana migrasi/rollout.
- Source registry tenant-scoped, adapter contract, local/fake adapter, serta adapter produksi awal sesuai lingkungan.
- Metadata discovery paged, checkpoint, health/partial scan, dan dry-run command/API sesuai pola proyek.
- Migrasi additive dan fixture. Catalog-only tidak memanggil provider atau mirror file.
- Dokumentasi setup Windows dan keterbatasan uji nyata.
- Ini target eksekusi pertama, kecuali audit membuktikan LAN-M1 sudah selesai.

**LAN-M2: snapshot selektif dan sinkronisasi incremental**
- Promotion policy, streaming staging/checksum, stabilitas file, version/provenance, dedup aman.
- Queue idempotency, retries, crash recovery, temp quota, dan disk guard.

**LAN-M3: parsing PDF/Word dan indeks berversi**
- Parser/OCR selektif, struktur lintas halaman, contextual cache, staging generation.
- Approval, publikasi konsisten, rekonsiliasi kegagalan lintas storage.

**LAN-M4: akses end-to-end dan retrieval**
- Scope di seluruh jalur retrieval/rerank/cache/viewer, revocation, provenance/sitasi.
- Curated access mode yang eksplisit; ACL Windows penuh hanya jika client memerlukannya dan tersedia identitas sumber.

**LAN-M5: cost control dan admin UI**
- Usage ledger, versioned prices, atomic budget reservations, throttling, pause/resume, cost/coverage UI.
- Budget gate dasar harus tersedia sebelum paid ingestion nyata pada milestone sebelumnya, meskipun dashboard lengkap masuk LAN-M5. Milestone awal menggunakan mock/dry-run sampai gate itu tersedia.

**LAN-M6: pilot dan panduan operasi**
- Sampel representatif, benchmark, evaluasi retrieval, penghitungan kapasitas dan biaya.
- Deployment lokal, backup/restore, source recovery, rollback, retensi, dan rollout bertahap.

Semua endpoint baru wajib tenant-scoped dan aman sejak dibuat. Jangan menunda keamanan dasar sampai LAN-M4. LAN-M4 memperluas serta menguji integrasi end-to-end.

### 15. Artefak repositori dan pelaporan

Buat atau perbarui file sesuai konvensi repo, minimal ekuivalen dengan:
- docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md
- docs/adr/<nomor-berikutnya>-lan-archive-incremental-ingestion.md
- docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md
- docs/LAN_ARCHIVE_PROGRESS.md
- docs/operations/LAN_CONNECTOR_RUNBOOK.md
- docs/evaluation/LAN_ARCHIVE_PILOT_PLAN.md
- CLAUDE.md sebagai ringkasan dan pointer, bukan salinan seluruh addendum.

Jangan merombak master spec atau menghapus aturan existing agar perubahan terlihat konsisten. Tambahkan referensi perubahan yang spesifik dan catat konflik yang benar-benar ada. Nomor ADR harus berasal dari pemeriksaan repo.

Progress checkpoint memuat:
- Milestone aktif dan status tiap acceptance criterion.
- File yang diubah dan keputusan utama.
- Migrasi dan compatibility.
- Perintah tests dan hasil nyata.
- Asumsi yang masih belum tervalidasi.
- Blocker infrastruktur/akses, bukan placeholder yang disembunyikan.
- Langkah berikut yang konkret.

Laporan akhir satu milestone harus mencakup:
1. Perubahan yang benar-benar selesai.
2. Alasan dan dampak terhadap biaya, reliabilitas, serta scope layanan.
3. Cara menjalankan dan menguji, dengan perintah sesuai repo aktual.
4. Hasil tests: passed/failed/skipped beserta alasan.
5. Dukungan yang sudah terbukti dan yang masih membutuhkan pengujian Windows/client.
6. Risiko/migrasi/rollback yang material.
7. Milestone berikutnya, tanpa otomatis mengerjakannya.

Jangan menyatakan selesai jika yang dibuat hanya interface kosong, TODO, atau dokumentasi. Jika adapter produksi belum bisa divalidasi karena tidak ada Windows/LAN, laporkan terpisah antara implementasi, integration test lokal, dan validasi lapangan yang tertunda.

Mulai sekarang dengan membaca repositori, membuat gap matrix, lalu mengerjakan milestone pertama yang eligible sampai kriteria milestone tersebut terpenuhi atau ada blocker konkret yang tidak dapat diselesaikan dengan akses yang tersedia.

## END PROMPT

---

## Prompt untuk melanjutkan sesi berikutnya

Salin instruksi berikut setelah satu milestone selesai:

> Lanjutkan pembaruan LAN archive 4 TB. Baca CLAUDE.md, aturan repo, addendum LAN, ADR terkait, implementation plan, dan LAN_ARCHIVE_PROGRESS.md. Periksa git diff/status serta hasil terakhir. Kerjakan hanya satu milestone berikutnya yang belum selesai dan dependensinya sudah tersedia. Pertahankan budget gate, tenant isolation, approval, snapshot/version integrity, dan larangan full ingestion/API berbayar tanpa konfigurasi operator. Jangan ulang pekerjaan yang sudah selesai. Implementasikan, uji, perbarui checkpoint, lalu laporkan hasil nyata dan uji client yang masih tertunda.

## Informasi client yang dapat ditambahkan jika sudah tersedia

Tidak perlu mengarang nilai yang belum diketahui. Claude Code tetap dapat mengerjakan fondasi dengan fixture dan dry-run.

| Informasi | Nilai |
| --- | --- |
| OS server backend dan versi | Belum diketahui |
| Topologi Windows share/DFS | Belum diketahui |
| Jumlah file dan folder | Belum diketahui |
| Total arsip | Hingga 4 TB |
| File terbesar | Sekitar 100 MB, perlu verifikasi |
| Proporsi PDF pindai/DOCX/DOC | Belum diketahui |
| Cakupan wajib: prioritas atau seluruh isi arsip | Belum ditetapkan |
| CPU, RAM, storage kosong, dan disk server | Belum diketahui |
| Jumlah pengguna bersamaan | Belum diketahui |
| Batas budget ingestion awal/bulanan/chat | Diisi client |
| Apakah teks boleh dikirim ke API cloud | Perlu kebijakan client |
| Curated folder atau mengikuti ACL Windows per pengguna | Perlu kebijakan client |
| Toleransi dokumen/izin yang belum tersinkron | Perlu kebijakan client |
| Sistem backup/versioning sumber yang sudah ada | Belum diketahui |

Jangan menempelkan credential atau API key pada prompt. Masukkan melalui mekanisme secrets yang didukung deployment.
