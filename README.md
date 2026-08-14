# Sokkafiber Helpdesk

Sistem tiket IT support (helpdesk) berbasis Django yang lengkap untuk perusahaan & klien korporat. Multi-company, kontrol akses berbasis role, SLA, laporan, analytics, knowledge base, dan audit trail.

---

## Fitur

### Manajemen Tiket
- Buat, lihat, cari, dan filter tiket berdasarkan status & prioritas
- Komentar pada tiket + notifikasi in-app & email
- Lampiran file (screenshot, log, dokumen) pada tiket & komentar
- Penugasan tiket ke staff
- SLA otomatis per prioritas (urgent 4 jam, high 24 jam, medium 72 jam, low 168 jam)
- Penanda **Overdue** pada tiket yang melewati SLA

### Kontrol Akses (Role-based)
| Role       | Akses                                                                 |
|------------|-----------------------------------------------------------------------|
| Admin      | Semua tiket, kelola user/company/kategori/artikel, laporan, analytics |
| Staff      | Tiket di company-nya, ubah status, assign, komentar, laporan          |
| Requester  | Tiket miliknya sendiri (company otomatis terkunci)                    |

- Detail tiket di luar scope user → **404** (tidak membocorkan keberadaan tiket)
- Halaman master (users/company/kategori/artikel) hanya untuk admin

### Dashboard Analytics
- KPI: total tiket, aktif, overdue, **kepatuhan SLA (%)**, rata-rata waktu penyelesaian
- Grafik tren tiket 14 hari (Chart.js)
- Distribusi status & prioritas
- Beban tiket per staff (admin)
- Kategori terbanyak

### Laporan
- Filter status / prioritas / company
- Export **Excel (XLSX)** dan **PDF** (ReportLab)

### Manajemen User
- Admin membuat user beserta role & company
- Edit user, aktif/nonaktif, hapus (dengan proteksi akun sendiri)
- Reset password oleh admin
- Ubah password sendiri

### Knowledge Base / FAQ
- Artikel solusi yang bisa dicari & difilter per kategori
- Hanya artikel terbit yang tampil ke pengguna
- CRUD artikel khusus admin

### Riwayat Aktivitas (Audit Trail)
- Semua aksi tiket tercatat: dibuat, perubahan status, penugasan, komentar
- Ditampilkan di halaman detail tiket

### Fondasi Produksi
- Konfigurasi via `.env` (secret key, debug, database, email, host)
- Logging berjenjang ke file & console
- Static files via WhiteNoise (siap `collectstatic`)
- **Docker & docker-compose** (web + PostgreSQL)
- Lampiran tiket dilindungi akses (hanya user terkait)
- 30 tes otomatis

---

## Persyaratan

- Python 3.12+ (dikembangkan di 3.14)
- pip

## Instalasi (Development)

```bash
# 1. Buat virtual environment
python -m venv venv

# 2. Aktifkan
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 3. Install dependensi
pip install -r requirements.txt

# 4. Konfigurasi environment
copy .env.example .env     # Windows
cp .env.example .env       # Linux/macOS
# lalu sesuaikan isi .env sesuai kebutuhan

# 5. Migrasi database & data awal
python manage.py migrate
python manage.py collectstatic --noinput

# 6. Buat superuser (pilih 'admin' sebagai role via Django admin)
python manage.py createsuperuser

# 7. Jalankan
python manage.py runserver
```

Buka `http://127.0.0.1:8000/`.

> **Catatan:** role (admin/staff/requester) diatur lewat `Profile`. User pertama
> yang dibuat via `createsuperuser` perlu di-set rolenya menjadi `Admin` melalui
> halaman Django admin (`/admin/`) atau halaman Manajemen User di aplikasi.
> Setiap user baru otomatis mendapat role `Requester`.

## Menjalankan dengan Docker (disarankan untuk produksi)

```bash
# 1. Salin konfigurasi (opsional; ada default bawaan)
copy .env.example .env

# 2. Bangun & jalankan (web + PostgreSQL)
docker compose up -d --build

# 3. Buat superuser di dalam container web
docker compose exec web python manage.py createsuperuser

# Buka http://localhost:8000
```

Variabel penting saat pakai Docker (diatur lewat `.env`):
`SECRET_KEY`, `DEBUG=false`, `ALLOWED_HOSTS`, `SITE_URL`, `DB_PASSWORD`.
Database otomatis memakai PostgreSQL dan migrasi + `collectstatic` dijalankan otomatis oleh `entrypoint.sh`.

Perintah berguna:
```bash
docker compose logs -f web      # lihat log
docker compose down             # hentikan (data tetap tersimpan)
docker compose down -v          # hentikan + hapus volume/data
```

## CI/CD (GitHub Actions)

Workflow `.github/workflows/ci.yml` berjalan otomatis pada setiap `push`/PR:

1. **Test (Django)** — install dependensi, `manage.py check`, dan seluruh tes otomatis (30).
2. **Build & Push image** (hanya saat push ke `main` atau tag `v*`) — build image Docker lalu push ke **GitHub Container Registry** (`ghcr.io/<owner>/<repo>`:latest / :sha / :tag).

Status terbaru bisa dilihat di tab **Actions** repo. Untuk deploy ke server, tinggal
`docker compose pull && docker compose up -d` dengan image dari registry.

## Akun Demo

| Username    | Password     | Role      |
|-------------|--------------|-----------|
| admin       | *(lihat .env / atur ulang)* | Admin |

## Menjalankan Tes

```bash
python manage.py test
```

## Produksi

```bash
python manage.py migrate
python manage.py collectstatic --noinput

# .env wajib di-set:
#   DEBUG=False
#   SECRET_KEY=<random panjang>
#   ALLOWED_HOSTS=domain.com
#   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
#   EMAIL_HOST=...  EMAIL_PORT=587  EMAIL_HOST_USER=...  EMAIL_HOST_PASSWORD=...
#   SITE_URL=https://domain.com
```

Gunicorn:

```bash
pip install gunicorn
gunicorn helpdesk.wsgi:application --bind 0.0.0.0:8000
```

## Struktur Project

```
helpdesk-tiket/
├── helpdesk/            # Project config (settings, urls, wsgi/asgi)
├── tickets/
│   ├── models.py        # Ticket, Comment, Notification, Activity, Article, Company, Category, Profile
│   ├── views.py         # Semua view (tiket, laporan, user, KB, dashboard)
│   ├── forms.py
│   ├── urls.py
│   ├── tests.py         # 30 tes otomatis
│   └── templates/tickets/
├── Dockerfile           # Image aplikasi (Python 3.12 + gunicorn)
├── docker-compose.yml   # Orchestrasi web + PostgreSQL
├── entrypoint.sh        # migrate + collectstatic otomatis saat start
├── .dockerignore
├── .env.example         # Template konfigurasi environment
├── requirements.txt
└── db.sqlite3           # Database development
```

## Roadmap

- [ ] Registrasi mandiri dengan persetujuan admin
- [ ] Knowledge base dengan markup (markdown)
- [ ] Webhook ke Slack/Teams
- [ ] Autentikasi LDAP/SSO
- [ ] Multi-tenancy penuh dengan database terpisah
