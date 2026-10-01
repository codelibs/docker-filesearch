# File Search on Fess

[Fess](https://fess.codelibs.org/) is an Enterprise Search Server. This Docker
Compose environment runs Fess with OpenSearch, serves the **filesearch static
theme** from [fess-themes](https://github.com/codelibs/fess-themes), and crawls a
generated sample file tree (a sample company, "Codelibs, Inc."; every name, figure and text in it is generated), so that you can
try the theme and develop it against realistic file-system data.

* Fess: 15.9 (`ghcr.io/codelibs/fess:snapshot-noble`, the in-development build; pin a 15.9.x tag after its release)
* Search engine: OpenSearch (`fess-opensearch:3.8.0`)
* Works on amd64 and arm64

Everything in the sample tree is made up. No real people, companies or products.

## Requirements

* Docker with Compose v2 (Docker Desktop on macOS / Windows), about 4 GB of free memory
* `python3` (standard library only), `curl`, and `git` (only needed to fetch the theme)
* Linux: `vm.max_map_count` of at least `262144` for OpenSearch
  (`sudo sysctl -w vm.max_map_count=262144`); Docker Desktop handles this itself

## Quick Start

```
bash ./bin/setup.sh            # data directories, theme, system.properties, sample files
docker compose up -d           # Fess + OpenSearch
bash ./bin/configure.sh        # crawl config + crawl; prints the number of indexed documents
```

then open `http://localhost:8080/` (admin console: `http://localhost:8080/admin/`,
user `admin`, password `admin`).

If a port is already in use, copy `.env.example` to `.env` first and change it
(see [Ports and environment variables](#ports-and-environment-variables)).

### What each step does

* `bin/setup.sh` is idempotent. It creates the `data/` directories, copies
  `data/fess/opt/fess/system.properties.template` to `system.properties` on the
  first run (an existing file is never overwritten), syncs the theme into
  `data/fess/usr/share/fess/app/themes/<theme>`, and runs `bin/seed-sample.sh`.
  On Linux it also hands the Fess and OpenSearch data directories to the container
  users with `sudo chown`. The theme is cloned from fess-themes (`main` by default); if
  `themes/filesearch` is not in that ref (for example before it is merged), point
  `FESS_THEMES_DIR` at a local checkout or `FESS_THEMES_REF` at a branch that has it
  (see [Developing the theme](#developing-the-theme)).
* `bin/configure.sh` is idempotent and talks to Fess over HTTP only. It waits for
  `/api/v2/health`, signs in to the admin console, makes sure an access token with
  the `admin-api` permission exists, creates the file crawl config `Sample Files`
  for `file:///data/files/` through the Admin API, starts the Default Crawler job
  and waits until the documents are indexed (default timeout 600 s,
  `CRAWL_TIMEOUT=900 bash bin/configure.sh` to change it). It prints the token, which is only
  meant for this local environment.

### Stop, update, reset

```
docker compose down                 # stop (data is kept in ./data)
git pull && bash ./bin/setup.sh && docker compose up -d    # update
```

All state lives in bind mounts under `data/` (there are no named volumes, so
`docker compose down -v` removes nothing). To start over, stop the stack and delete
what you want to reset:

```
docker compose --profile smb down
rm -rf data/opensearch data/fess/var                        # index, crawl config, logs
rm -rf data/fess/opt/fess/system.properties                 # system settings back to the template
rm -rf data/fess/usr data/files                             # theme copy and sample files
bash ./bin/setup.sh && docker compose up -d && bash ./bin/configure.sh
```

## Ports and environment variables

`docker compose` and the scripts read a `.env` file in this directory
(`cp .env.example .env`; it is git-ignored). You can also set a variable on the command line.

| Variable | Default | Meaning |
|---|---|---|
| `FESS_HTTP_PORT` | `8080` | Fess on the host (container port 8080) |
| `SEARCH_HTTP_PORT` | `9200` | OpenSearch on the host; bound to `127.0.0.1` only because its security plugin is disabled |
| `FESS_IMAGE` | `ghcr.io/codelibs/fess:snapshot-noble` | Fess image (see [Thumbnails](#thumbnails)) |
| `THEME_NAME` | `filesearch` | Theme directory to sync and mount |
| `FESS_THEMES_DIR` | (unset) | Local fess-themes checkout to copy the theme from |
| `FESS_THEMES_REPO` / `FESS_THEMES_REF` | `https://github.com/codelibs/fess-themes.git` / `main` | Where `setup.sh` clones the theme from when `FESS_THEMES_DIR` is unset |
| `FESS_ADMIN_USER` / `FESS_ADMIN_PASSWORD` | `admin` / `admin` | Account `configure.sh` signs in with |
| `FESS_TOKEN_NAME` / `FESS_CRAWL_CONFIG_NAME` | `filesearch-dev` / `Sample Files` | Names of the access token and of the file crawl config that `configure.sh` creates, or reuses when one of that name exists. With `--smb`, the SMB crawl config is named `<FESS_CRAWL_CONFIG_NAME> (SMB)` |
| `CRAWL_TIMEOUT`, `HEALTH_TIMEOUT` | `600`, `300` | Seconds `configure.sh` waits for the crawl and for Fess |

## Developing the theme

`setup.sh` copies `themes/<THEME_NAME>` out of a fess-themes checkout. To work on a
local checkout:

```
FESS_THEMES_DIR=/path/to/fess-themes bash ./bin/setup.sh
```

(or put `FESS_THEMES_DIR=...` in `.env`). The copy replaces the contents of the
mounted directory in place, so the running container sees it at once: **reload the
browser, no restart needed** - re-run `setup.sh` after each change you want to
see. You can also edit the files under `data/fess/usr/share/fess/app/themes/<theme>/`
directly. Pin a branch or tag of the remote with `FESS_THEMES_REF=<ref>`.

To mount another theme, put `THEME_NAME=<theme>` in `.env`. The directory name
must equal `name:` in the theme's `theme.yml`, and `theme.default` in
`data/fess/opt/fess/system.properties` must name it (the first `setup.sh` run
writes it for you; later runs only warn, so delete that file or change the value
under Admin > General when you switch). Then apply the new mount:

```
rm data/fess/opt/fess/system.properties
bash ./bin/setup.sh && docker compose up -d
```

If Fess shows the stock Bootstrap UI instead of the theme, look in
`data/fess/var/log/fess/fess.log` for `ThemeRegistry` lines (see Troubleshooting).

## Sample files

`bin/seed-sample.sh` (run by `setup.sh`) writes `data/files` with
`bin/generate_sample.py`. The directory is git-ignored; only the generator is tracked.
The output is deterministic: the same seed and reference date give identical
files, contents and modification times.

* About 310 files in roughly 230 directories, up to six levels deep: `Sales`, `Engineering`,
  `HR`, `Finance`, `Legal`, `Marketing`, `Shared` and `総務部`, with year / quarter /
  project / customer sub-folders.
* English, Japanese and bilingual content in txt, md, html, csv, json, pdf, docx,
  xlsx, pptx and png (plus one `.log`). The Office, PDF and PNG files are written
  from scratch with the standard library and are extracted by Fess normally.
* Sizes from a few hundred bytes to about 1.7 MB, modification times spread over
  three years (a few within the last week), so date, size and sort options have
  something to show.
* Spaces and Japanese in folder names, one file path of 376 characters below `data/files` (the
  longest directory path is 241), and file names with `#`, `%`, `&`, `+`, `(`, `)` and `,`
  (in `Shared/Misc`) to exercise URL handling.

```
bash bin/seed-sample.sh --clean                         # empty data/files first, then regenerate
SAMPLE_REFERENCE_DATE=today bash bin/seed-sample.sh     # newest file = today instead of 2026-09-30
SAMPLE_SEED=1 bash bin/seed-sample.sh                   # a different tree
```

After changing the files, run `bash bin/configure.sh` again to re-crawl (unchanged
files are skipped, so a regenerated tree with new contents but the same modification
times is only picked up after you reset the index).

## The three configuration layers

Fess reads settings from three places; this environment uses all of them.

**1. JVM flags (`fess_config.properties` overrides)** - `-Dfess.config.<key>=<value>`
in `FESS_JAVA_OPTS` in `compose.yaml`. Read at startup, so `docker compose up -d`
after editing. Used here:

| Key | Value | Why |
|---|---|---|
| `adaptive.load.control` | `0` | Never pause the crawler because the host is busy (the default 50 can stall a crawl on a shared machine) |
| `query.additional.sort.fields` | `filetype,url` | Allows `sort=filetype.asc` and `sort=url.desc`; they are rejected (HTTP 400) by default |
| `crawler.document.cache.enabled` | `true` | Keep the extracted text for the cache view `/api/v2/cache/{docId}` |
| `crawler.document.cache.supported.mimetypes` | `text/html`, the text-like types (`text/plain`, `text/csv`, `text/x-web-markdown`, `text/x-log`, `application/json`, ...), `application/pdf` and the three Office (OOXML) types | The default is `text/html` only. With these, `has_cache` is true for every sample file except the PNG images. The cache holds the extracted text, which is the only content preview for PDF and Office files. Re-crawl after changing it: documents crawled earlier have no cache |

**2. System properties (`data/fess/opt/fess/system.properties`)** - the values behind
Admin > General, mounted at `/opt/fess/system.properties`. Created from the tracked
template on the first `setup.sh` run; the live file is git-ignored so Fess can
rewrite it and `git pull` never conflicts. Edits are picked up while Fess runs.
Delete it and re-run `setup.sh` to go back to the template.

| Key | Value | Why |
|---|---|---|
| `theme.default` | `filesearch` | The static theme served at `/` (written from `THEME_NAME` on first run) |
| `thumbnail.enabled` | `true` | Fess generates and serves `/thumbnail/` images (default is false) |
| `search.file.proxy` | `true` | `/go/?docId=...` streams `file:` / `smb:` documents over HTTP (default true) |
| `web.api.json` | `true` | Enables `/api/v2/*` (default true) |
| `login.required` | `false` | Anonymous search |
| `result.collapsed` | `false` | One result per file |
| `user.favorite` | `true` | Favourite stars on results (default false) |

**3. Admin settings (stored in OpenSearch)** - created by `bin/configure.sh` through
the Admin API: the access token `filesearch-dev` (permission `{role}admin-api`), the
file crawl config `Sample Files`, and with `--smb` the SMB crawl config and its file
authentication. Change them in the admin console (Crawler > File System) or delete them
there and re-run `configure.sh`; an existing config is reused as it is.

Admin API notes: send `Authorization: Bearer <token>`; the console session is not
accepted. Field names are snake_case (`num_of_thread`, `interval_time`, `sort_order`).

## Optional: the same files over SMB

```
docker compose --profile smb up -d
bash ./bin/configure.sh --smb
```

adds a Samba service (`dockurr/samba:4.23.10`, share `share`, user `filesearch`, password
`filesearch`, read-only view of `data/files`; not published on the host) and a second
crawl config for `smb://samba01/share/`. The documents then also appear with host
`samba01` and `\\samba01\share\...` paths, so the total doubles. In the file
authentication the port is `0` (the default port); `445` would not match.

## Thumbnails

Fess makes thumbnails of PDF, Office and image files with ImageMagick, poppler and
LibreOffice. Only the Ubuntu-based image has them, which is why `FESS_IMAGE` defaults to
`ghcr.io/codelibs/fess:snapshot-noble`. With the Alpine `ghcr.io/codelibs/fess:snapshot`
no thumbnail is generated at all (`/thumbnail/` stays 404).

* `/thumbnail/?docId=<id>&queryId=<query_id>` needs the `query_id` from a search response.
  A first request returns 404 and queues the document; the Thumbnail Generator job runs
  every minute, so the image is there a minute or two later.
* Thumbnails are PNGs that fit in a 100x100 box with the aspect ratio kept, so they are not all
  100x100 (71x100 for the A4 pages of the sample PDFs, 100x63 for most sample PNG images).
  Pages with no `<img>` (the sample HTML) never get one, and txt / md / csv / json / log files have no `thumbnail` field.
* Japanese text is not drawn in PDF / Office thumbnails because the image has no
  Japanese fonts; the text is still extracted and searchable.

## Notes on what Fess returns for files

Handy when writing a theme against this data (`q=*` matches every document):

* `url` of a `file:` document is percent-encoded (`file:/data/files/Sales/Customers/Silverline%20Foods/...`);
  `site` and `site_path` are the decoded path; `host` is `localhost`. `smb:` documents have a decoded
  `url`, `host` `samba01` and a `\\server\share\...` `site`. `url_link` of a `file:` document comes
  out as `file://data/files/...`, so build paths from `site_path`.
* A directory filter is `ex_q=url:file\:\/data\/files\/Sales\/*` over the encoded path, with a backslash before
  `:` and `/` (and before `-`, `(`, `)`, `&`, `+` and spaces). An unescaped colon is HTTP 400; a path written with
  raw spaces or Japanese matches nothing. A quoted form (`url:"file:/data/files/Sales/*"`) stops matching once the
  value is longer than about 255 characters.
* Markdown, CSV, JSON and log files have `filetype=others`.
* `facet.field=url&facet.size=1000` returns one bucket per file; `site` and `filename` are not facet fields.

## Troubleshooting

* **The crawl finds nothing and `fess-crawler.log` shows `index_create_block_exception` /
  `NullPointerException`**: OpenSearch refuses to create indices when the disk is more than
  90% full. `compose.yaml` disables the disk threshold for this development stack; if you removed
  that setting, free some disk space.
* **Fess shows the Bootstrap UI, not the theme**: check `docker compose logs fess01` / `data/fess/var/log/fess/fess.log`.
  `Theme dir 'x' name mismatch with manifest 'y'; skipping` means the directory name differs from `name:` in
  `theme.yml`; `The default theme 'x' is not installed` means `theme.default` does not match a mounted theme.
* **Port already in use** (`Bind for 0.0.0.0:8080 failed`): set `FESS_HTTP_PORT` / `SEARCH_HTTP_PORT` in `.env`
  and run `docker compose up -d` and `bash bin/configure.sh` again. Other ports are not enough for a second
  copy of this environment on the same Docker host: `compose.yaml` pins `container_name`
  (`filesearch-fess01`, `filesearch-search01`, `filesearch-samba01`), so the second copy cannot create its
  containers while the first one exists, unless you change those names in its `compose.yaml`.
* **No thumbnails**: see [Thumbnails](#thumbnails) (Alpine image, or the generator has not run yet).
* **`configure.sh` stops with "Admin login failed"**: set `FESS_ADMIN_USER` / `FESS_ADMIN_PASSWORD` if you changed the
  administrator password.
* **`configure.sh` says the Admin API rejected the token**: delete the `filesearch-dev` token under Admin > System >
  Access Token and run it again.
* **The SMB crawl logs `Could not access smb://samba01/share/`**: the file authentication needs port `0`, user
  `filesearch` and password `filesearch`; check Crawler > File Authentication.
* **A 400 from `/api/v2/search?ex_q=url:...`**: see the escaping rules above.
* **Linux permission errors in `data/`**: re-run `bash ./bin/setup.sh` (it uses `sudo chown`), or `sudo chown -R 1001`
  the `data/fess` subdirectories and `sudo chown -R 1000` the `data/opensearch` ones.

## Files

| Path | Purpose |
|---|---|
| `compose.yaml` | Fess, OpenSearch and the optional Samba service |
| `.env.example` | Port, image and theme overrides |
| `bin/setup.sh` | Directories, theme sync, system.properties seed, sample data |
| `bin/configure.sh` | Crawl config, access token, crawl |
| `bin/seed-sample.sh`, `bin/generate_sample.py` | The sample file tree |
| `data/fess/opt/fess/system.properties.template` | Tracked system settings |
