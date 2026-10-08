# File Search on Fess

[Fess](https://fess.codelibs.org/) is an Enterprise Search Server. This Docker
Compose environment runs Fess with OpenSearch, serves the **filesearch static
theme** from [fess-themes](https://github.com/codelibs/fess-themes), and crawls a
generated sample file tree (a sample company, "Codelibs, Inc."; every name, figure and text in it is generated), so that you can
try the theme and develop it against realistic file-system data.

* Fess: 15.9 (`ghcr.io/codelibs/fess:snapshot-noble`, the in-development build; pin a 15.9.x tag after its release)
* Search engine: OpenSearch (`fess-opensearch:3.8.0`), which also hosts the embedding model
* Search: keyword and vector search over a multilingual embedding model, fused in one
  OpenSearch request (Fess 15.9 engine-side hybrid search; see [Hybrid search](#hybrid-search))
* Works on amd64 and arm64

Everything in the sample tree is made up. No real people, companies or products.

## Requirements

* Docker with Compose v2 (Docker Desktop on macOS / Windows), about 8 GB of free memory
  (measured peak: OpenSearch 4.8 GiB with the embedding model, Fess 2.1 GiB; on Docker Desktop that is the
  memory limit of its VM, under Settings > Resources)
* Network access on the first run: OpenSearch downloads the embedding model (about 490 MB), and the
  one-shot `init-semantic` container installs `curl` and `jq` from the Alpine package index. Later
  `docker compose up -d` runs work offline as long as the model is still deployed
* About 1.5 to 1.7 GB of disk for `data/opensearch` (index, vectors and the model)
* `python3` (standard library only), `curl`, and `git` (only needed to fetch the theme)
* Linux: `vm.max_map_count` of at least `262144` for OpenSearch
  (`sudo sysctl -w vm.max_map_count=262144`); Docker Desktop handles this itself

## Quick Start

```
bash ./bin/setup.sh            # data directories, theme, system.properties, sample files
docker compose up -d           # OpenSearch + embedding model (first run: about 2 minutes), then Fess
bash ./bin/configure.sh        # crawl config + crawl + chunk vectors; prints the number of indexed documents
```

The first `configure.sh` takes about 9 to 16 minutes, depending on the machine: 30 seconds
for the crawl and 8 to 14 minutes for the chunk vectors (see [Hybrid search](#hybrid-search)). Keyword results are
there as soon as the crawl is done; the vector half joins when the indexer has finished.

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
  (see [Developing the theme](#developing-the-theme)). It also creates `data/semantic`,
  where the embedding model id is handed to Fess.
* `docker compose up -d` starts OpenSearch, then the one-shot `init-semantic` service, which
  registers and deploys the embedding model in OpenSearch (about 1.5 minutes, mostly the
  download; seconds on later runs), and only then Fess. `docker compose up -d` returns when the Fess
  container has started; Fess needs another minute or so before it answers (`configure.sh` waits for it).
* `bin/configure.sh` is idempotent and talks to Fess over HTTP only. It waits for
  `/api/v2/health`, signs in to the admin console, makes sure an access token with
  the `admin-api` permission exists, creates the file crawl config `Sample Files`
  for `file:///data/files/` through the Admin API, starts the Default Crawler job
  and waits until the documents are indexed (default timeout 600 s,
  `CRAWL_TIMEOUT=900 bash bin/configure.sh` to change it). Then it enables the Content Chunk
  Vector Indexer job (shipped disabled; the schedule is left as it is), runs it, waits for
  the run to end (`VECTOR_TIMEOUT`, default 1800 s) and prints the indexer's summary line
  (`Processed ... Succeeded ... Failed/Skipped ...`); it stops if the indexer skipped the run. It prints the token, which is only
  meant for this local environment. A re-run takes about a minute: it crawls again and the indexer
  has nothing left to embed.

### Stop, update, reset

```
docker compose down                 # stop (data is kept in ./data)
git pull && bash ./bin/setup.sh && docker compose up -d    # update
```

All state lives in bind mounts under `data/` (there are no named volumes, so
`docker compose down -v` removes nothing). `docker compose up -d` after a `down` reuses the
deployed model (same model id; under 20 seconds, with or without network). To start over, stop the stack and delete
what you want to reset:

```
docker compose --profile smb down
rm -rf data/opensearch data/semantic data/fess/var          # index, model, crawl config, logs
rm -rf data/fess/opt/fess/system.properties                 # system settings back to the template
rm -rf data/fess/usr data/files                             # theme copy and sample files
bash ./bin/setup.sh && docker compose up -d && bash ./bin/configure.sh
```

**Coming from the keyword-only version of this environment** (before hybrid search): the old index
was created with Fess's default vector dimension, 768, and the dimension is fixed when the index is
created. With the 384-dimension model every Content Chunk Vector Indexer run would skip itself and
search would stay keyword-only (`configure.sh` stops with the indexer's message). After `git pull`,
run `docker compose down`, delete `data/opensearch` and `data/fess/var`, and run the Quick Start again.
The same goes for a change of `MODEL_NAME`, `MODEL_DIMENSION` or `CHUNK_SIZE`: chunks and vectors
already stored are not redone, and an incremental crawl skips unchanged files, so only a fresh index
applies the new value.

## Ports and environment variables

`docker compose` and the scripts read a `.env` file in this directory
(`cp .env.example .env`; it is git-ignored). You can also set a variable on the command line.

| Variable | Default | Meaning |
|---|---|---|
| `FESS_HTTP_PORT` | `8080` | Fess on the host (container port 8080) |
| `SEARCH_HTTP_PORT` | `9200` | OpenSearch on the host; bound to `127.0.0.1` only because its security plugin is disabled, and the node hosts ML Commons (anyone reaching the port could register models) |
| `OPENSEARCH_HEAP` | `2g` | OpenSearch heap (`-Xms`/`-Xmx`); the node also hosts the embedding model |
| `FESS_IMAGE` | `ghcr.io/codelibs/fess:snapshot-noble` | Fess image (see [Thumbnails](#thumbnails)) |
| `THEME_NAME` | `filesearch` | Theme directory to sync and mount |
| `FESS_THEMES_DIR` | (unset) | Local fess-themes checkout to copy the theme from |
| `FESS_THEMES_REPO` / `FESS_THEMES_REF` | `https://github.com/codelibs/fess-themes.git` / `main` | Where `setup.sh` clones the theme from when `FESS_THEMES_DIR` is unset |
| `FESS_ADMIN_USER` / `FESS_ADMIN_PASSWORD` | `admin` / `admin` | Account `configure.sh` signs in with |
| `FESS_TOKEN_NAME` / `FESS_CRAWL_CONFIG_NAME` | `filesearch-dev` / `Sample Files` | Names of the access token and of the file crawl config that `configure.sh` creates, or reuses when one of that name exists. With `--smb`, the SMB crawl config is named `<FESS_CRAWL_CONFIG_NAME> (SMB)` |
| `CRAWL_TIMEOUT`, `HEALTH_TIMEOUT` | `600`, `300` | Seconds `configure.sh` waits for the crawl and for Fess |
| `VECTOR_TIMEOUT` | `1800` | Seconds `configure.sh` waits for the Content Chunk Vector Indexer. The job keeps running if the wait times out; run `configure.sh` again to wait for it |
| `MODEL_NAME` / `MODEL_VERSION` | `huggingface/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` / `1.0.1` | Embedding model `init-semantic` registers (a multilingual one, because the sample files are English, Japanese and bilingual) |
| `MODEL_DIMENSION` | `384` | Vector dimension; must match the model. It is fixed in the index mapping when the index is created |
| `MODEL_MAX_WAIT` | `900` | Seconds `init-semantic` waits for each of its two ML tasks, the model download and then the deploy (up to twice that in all) |
| `CHUNK_SIZE` | `500` | Characters per chunk (see [Hybrid search](#hybrid-search)) |
| `SEMANTIC_MIN_SCORE` | `0.35` | Minimum cosine similarity for a file to be returned by the vector half (see [Hybrid search](#hybrid-search)) |
| `RANK_FUSION_ENGINE` | `true` | `false`: Fess fuses the keyword and vector results itself instead of OpenSearch |
| `SEMANTIC_SEARCH` | `true` | `false`: keyword search only (changing it back to `true` needs a Fess restart) |

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

## Hybrid search

A search runs the keyword (BM25) query and a vector query over a multilingual embedding model
together, and OpenSearch fuses the two rankings in one `hybrid` request (Fess 15.9
`rank.fusion.engine.enabled`, reciprocal rank fusion). A question that shares no word with a file
- an English one about a file written only in Japanese, or the other way round - still finds it,
because the model puts both languages in one vector space. The theme is unchanged: it reads
`/api/v2/search` as before.

| Piece | What it does |
|---|---|
| `init-semantic` (one-shot service, `bin/setup-semantic.sh`) | Registers and deploys `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions) in OpenSearch ML Commons and writes the generated model id to `data/semantic/model_id`. The first run downloads the model (about 490 MB; the whole step takes 1.5 to 2 minutes). Later runs find the model, deploy it again if it was undeployed, and otherwise reuse it; with no network they reuse the model of the last run when OpenSearch still has it deployed |
| `fess01` | Starts after `init-semantic` has finished. `bin/fess-entrypoint.sh` adds the model id as `-Dfess.system.content_chunker.embedding.opensearch.model.id`; Fess reads it once, at start |
| Content Chunk Vector Indexer | A Fess job, shipped disabled. `bin/configure.sh` enables it and runs it after the crawl: it splits the text of every file into chunks, embeds them through the model and stores the vectors in the index. The schedule stays the default (daily at 13:00 UTC, the container's time zone). That run covers files added or changed after the scheduled crawl, which stay keyword-only until then, and it also repairs files the first run left out (see Troubleshooting) |
| A search | Fess embeds the query with the same model, and one `hybrid` request carries both the keyword and the vector query; files that both halves match rank higher |

The settings are listed in [The three configuration layers](#the-three-configuration-layers).

### Chunking and what the theme shows

When the indexer processes a file, Fess stores the chunks back into `content` as an array
(`content_length` keeps the original length). Measured on the sample tree, comparing ten keyword
queries (top 10 hits each) before and after the indexer ran:

* **Result snippets** (`content_description`, the highlighted passages the theme shows) keep the
  same form and keep their highlights; `digest`, `content_length` and `has_cache` do not change.
  With `CHUNK_SIZE=500`, 6 of the 59 hits compared show a different matching passage (20 of 58 at 250);
  none is empty. Snippets are cut at chunk boundaries. A hit found only by the vector half has no
  keyword to highlight, so it shows the `digest`, the start of the file.
* **Cache preview** (`/api/v2/cache/{docId}`, the preview pane) is built from the text stored at crawl
  time, not from `content`: 16 documents (two of every file type, PDF and Office included) are
  byte-identical before and after.
* **PDF and Office files** are chunked from the same extracted text as any other file.
* A file that would need more than `content_chunker.max_chunks_per_document` (1000) chunks is marked
  `skipped` and stays whole, keyword-only: with `CHUNK_SIZE=500` that is the 1.7 MB log and one 1.5 MB CSV.

### Tuning: `CHUNK_SIZE` and `SEMANTIC_MIN_SCORE`

The model reads about the first 128 tokens of a chunk, roughly 500 English or 250 Japanese
characters; the rest of the chunk is invisible to the vector half (the keyword half still matches it),
and a sentence inside a long chunk scores lower than the same sentence alone. So smaller chunks find more,
and cost more indexer time. Measured with eight English and Japanese paraphrases of
sentences in the files (`min_score` 0.3):

| `CHUNK_SIZE` | Chunks | Files skipped | Indexer run | Paraphrases that find a file in the other language | Files containing the sentence that score above 0.3 |
|---|---|---|---|---|---|
| 250 | 21,390 | 10 | 11.5 min | 8 of 8 | 87% |
| **500** (default) | 15,930 | 2 | 8.3 min | 8 of 8 | 82% |
| 1000 | 7,901 | 2 | 4.3 min | 8 of 8 | 74% |

500 fits an English chunk into what the model reads. Use 1000 for a faster first run, 250 for the
best recall (on a fresh index: a new size does not redo files that are already chunked).

A vector search returns neighbours even when they are not similar, so `SEMANTIC_MIN_SCORE` decides how
long the tail is. Measured with `CHUNK_SIZE=500`: the same eight paraphrases, nine keyword queries
(`audit`, `Maple Gateway`, `契約`, ...) and five unrelated ones (`weather forecast tomorrow`, ...),
mean number of results per query:

| `SEMANTIC_MIN_SCORE` | Paraphrases that find a file in the other language | Keyword queries | Unrelated queries |
|---|---|---|---|
| (hybrid off) | 0 of 8 | 18 | 0 |
| 0.25 | 8 of 8 | 149 | 37 |
| 0.30 | 8 of 8 | 96 | 15 |
| **0.35** (default) | 8 of 8 | 58 | 7 |
| 0.40 | 6 of 8 | 39 | 1.6 |
| 0.50 | 6 of 8 | 22 | 0 |

0.35 is the highest tested value at which all eight paraphrases still work. A keyword search gains
semantic neighbours (`audit`: 2 files by keyword, 44 with the default); raise the value for a shorter
tail. Scores belong to the model and the chunk size, so measure again after changing either. To try a
value without restarting Fess, put `content_chunker.search.min_score=0.4` into
`data/fess/opt/fess/system.properties` (Fess reads it while running), then move the value to
`SEMANTIC_MIN_SCORE` in `.env` and remove the line.

### Which searches are fused

A typed query in the default relevance order is one `hybrid` request. A folder scope or a filter (the
theme sends them as `ex_q`) is applied to both halves. Other searches are not fused in OpenSearch:

* An explicit `sort`: every sort column of the theme (Name, Modified, Size, Type, Location), and the name
  order it uses when there is no keyword. These are keyword-only (`audit`: 44 files by relevance,
  2 sorted by name).
* Advanced search (`as.*` parameters): Fess runs the two searches and fuses them itself.
* Queries with a quoted phrase of two or more words, a wildcard (`audit*`), an exclusion
  (`audit -summary`), only a field condition (`title:audit`) or an ASCII `?` at the end: keyword-only.
  A question like `how often are fire drills held?` therefore finds nothing: leave the `?` out.
  A quoted single token (for example a Japanese title such as `"契約書"`) is not recognised as a phrase
  and still runs the vector half.

Paging stops at `rank.fusion.pagination_depth` (1000) results.

### Checking that it works

```
curl -s 'http://localhost:8080/api/v2/search?q=How+often+do+employees+rehearse+evacuating+the+building' \
  | python3 -c 'import json,sys; [print(d["searcher"], d["url"]) for d in json.load(sys.stdin)["response"]["data"]]'
```

`searcher` lists the halves that matched each hit: `default` (keyword), `semantic_chunk` (vector) or
both. This question shares no word with the General Affairs files (`総務部`, written in Japanese) about
fire drills, and finds them with `["semantic_chunk"]`. To see that OpenSearch fused the request, log
every search of the index and look for a `hybrid` query with a `default` and a `semantic_chunk` part:

```
curl -X PUT localhost:9200/fess.search/_settings -H 'Content-Type: application/json' \
  -d '{"index.search.slowlog.threshold.query.trace":"0ms"}'
docker compose logs search01 | grep '"hybrid":{"queries"'
curl -X PUT localhost:9200/fess.search/_settings -H 'Content-Type: application/json' \
  -d '{"index.search.slowlog.threshold.query.trace":"-1"}'          # back to off
```

### Switching it off

Put the switch in `.env` and run `docker compose up -d` (it recreates Fess):

* `SEMANTIC_SEARCH=false`: keyword search only, as before. The vectors stay in the index; setting it back to
  `true` and restarting brings the vector half back.
* `RANK_FUSION_ENGINE=false`: the vector half stays, but Fess runs the two searches and fuses them itself
  (the same top results for the eight paraphrases above; from the 100th hit on, a broad query then returns
  keyword hits only).

Chunking has rewritten `content`, so to remove it altogether (and the model) delete the `init-semantic`
service (and its entry in the `depends_on` of `fess01`) and the `content_chunker.*` options from
`compose.yaml`, and reset the index (see [Stop, update, reset](#stop-update-reset)).

For up to a minute after OpenSearch or Fess starts the model is not ready yet and Fess answers with keyword
results only (it logs `Failed to embed query for semantic chunk search; falling back to keyword-only results`);
there is no error.

## The three configuration layers

Fess reads settings from three places; this environment uses all of them.

**1. JVM flags** - in `FESS_JAVA_OPTS` in `compose.yaml`. `-Dfess.config.<key>=<value>` overrides
`fess_config.properties`; `-Dfess.system.<key>=<value>` is the initial value of a system property
(layer 2). Both are read at startup, so `docker compose up -d` after editing. Used here:

| Key | Value | Why |
|---|---|---|
| `adaptive.load.control` | `0` | Never pause the crawler because the host is busy (the default 50 can stall a crawl on a shared machine) |
| `file.role.from.file`, `smb.role.from.file` | `false` | By default (`true`) the owner and group of every file become roles (`1<owner>`, `2<group>`) of its document, and the roles are part of the document id. The sample tree has no meaningful permissions (every file is visible through `{role}guest`), and a bind-mounted directory read by two containers (Fess and the optional Samba service) can show a different owner to Fess from one crawl to the next on Docker Desktop for Mac, so unchanged files were fetched and indexed again on every crawl |
| `query.additional.sort.fields` | `filetype,url` | Allows `sort=filetype.asc` and `sort=url.desc`; they are rejected (HTTP 400) by default |
| `crawler.document.cache.enabled` | `true` | Keep the extracted text for the cache view `/api/v2/cache/{docId}` |
| `crawler.document.cache.supported.mimetypes` | `text/html`, the text-like types (`text/plain`, `text/csv`, `text/x-web-markdown`, `text/x-log`, `application/json`, ...), `application/pdf` and the three Office (OOXML) types | The default is `text/html` only. With these, `has_cache` is true for every sample file except the PNG images. The cache holds the extracted text, which is the only content preview for PDF and Office files. Re-crawl after changing it: documents crawled earlier have no cache |
| `theme.index.frame.ancestors` | empty | The directive `frame-ancestors 'none'` that Fess sends with the theme's pages (default) makes WebKit (Safari) show the preview and cache frames blank: they are `blob:` documents that inherit the policy, and WebKit applies the directive to them. Empty drops the directive; `X-Frame-Options: DENY` is still sent and keeps the pages out of frames. The key exists in Fess builds that include codelibs/fess#3522; older builds ignore it |
| `rank.fusion.engine.enabled` | `true` | One OpenSearch `hybrid` request fuses the keyword and the vector query (Fess default `false`: Fess runs the two searches and fuses them itself). `RANK_FUSION_ENGINE=false` switches it back |
| `query.additional.response.fields`, `query.additional.api.response.fields` | `searcher` | `/api/v2/search` then reports which half matched each hit (`default` = keyword, `semantic_chunk` = vector). Both keys are needed: the first fetches the field, the second allows it in the API response |

The vector half is `content_chunker.*`. It is read **only** from the system-properties channel, so it is set
as `-Dfess.system.*` (`-Dfess.config.content_chunker.*` is ignored):

| Key | Value | Why |
|---|---|---|
| `content_chunker.enabled` | `true` | Chunking and embedding (default `false`) |
| `content_chunker.search.enabled` | `true` | The vector searcher takes part in the search (default `false`; false -> true needs a restart). `SEMANTIC_SEARCH=false` switches it off |
| `content_chunker.embedding.dimension` | `384` | The model's dimension (Fess default `768`); baked into the index mapping when the index is created |
| `content_chunker.length.chunk_size` | `500` | Measured, see [Hybrid search](#hybrid-search) (Fess default `800`) |
| `content_chunker.search.min_score` | `0.35` | Measured, see [Hybrid search](#hybrid-search) (Fess default: no cutoff) |
| `content_chunker.embedding.opensearch.model.id` | generated | Added by `bin/fess-entrypoint.sh` from `data/semantic/model_id`; the built-in `opensearch` embedding provider is the default and needs no other setting |

**2. System properties (`data/fess/opt/fess/system.properties`)** - the values behind
Admin > General, mounted at `/opt/fess/system.properties`. Created from the tracked
template on the first `setup.sh` run; the live file is git-ignored so Fess can
rewrite it and `git pull` never conflicts. Edits are picked up while Fess runs.
Delete it and re-run `setup.sh` to go back to the template. Do not put `content_chunker.*` in it:
a value in this file wins over the `-Dfess.system.*` option, which would leave `.env` without effect
(it is also a handy way to try a `content_chunker.search.min_score` without a restart; remove the line afterwards).

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
* **The search page shows "Part of the search could not be completed; results may be incomplete."** (the
  `/api/v2/search` response has `partial: true` and `shard_failed: true`; it hits a small share of the
  searches, more of them under load): the theme sends `last_modified:[now/d-... TO *]` facet queries with
  every search, and on OpenSearch 3.x concurrent segment search makes some of them fail on a shard
  (`DateRangeIncludingNowQuery ... does not implement createWeight` in `docker compose logs search01`).
  `compose.yaml` sets `search.concurrent_segment_search.mode=none` on `search01`, which costs a one-node demo
  index nothing. If the banner appears, check that the setting is still in place:
  `curl 'http://localhost:9200/_cluster/settings?include_defaults=true&flat_settings=true'` lists
  `search.concurrent_segment_search.mode` with the value `none`.
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
* **`docker compose up -d` stops with `service "init-semantic" didn't complete successfully: exit 1`**: the model
  could not be registered or deployed. Read `docker compose logs init-semantic`. The first run needs network access
  (the model, about 490 MB, and `apk add curl jq`); on a slow connection raise `MODEL_MAX_WAIT`. Run
  `docker compose up -d` again: a model that was already downloaded is reused. Without network a later run still
  starts Fess if the model of the last run is deployed; otherwise it says so and exits.
* **Searches return keyword results only**: check `searcher` in the API response (see
  [Hybrid search](#hybrid-search)). Causes: the Content Chunk Vector Indexer has not run (Admin > System > Scheduler,
  or `bash bin/configure.sh`; a file the indexer skipped or failed has `content_chunk_status` `skipped` or `fail`,
  only a file with no status has not been processed), the first minute after a start (the model is not ready yet),
  `SEMANTIC_SEARCH=false`, a sorted search, or a query ending in an ASCII `?`. The indexer's own summary is the
  `Chunk vector processing result:` line in `data/fess/var/log/fess/fess-chunk.log`.
* **`configure.sh` stops with `The Content Chunk Vector Indexer skipped this run: ...`**: the job log says "ok" even
  when the indexer skipped the whole run, so `configure.sh` reads that summary line. `Embedding provider is not
  available` means the model is not deployed, Fess has no model id or `MODEL_DIMENSION` differs from the model's (the
  first minute after a Fess start counts too: run `configure.sh` again after a minute; `docker compose logs init-semantic`
  and the ERROR lines in `fess-chunk.log` say more); `Embedding dimension mismatch` means the index was created with
  another dimension (see Stop, update, reset: start from a fresh index).
* **`configure.sh` times out waiting for the Content Chunk Vector Indexer**: the indexer needs 8 to 14 minutes,
  more on a smaller or busier machine, and keeps running; run `bash bin/configure.sh` again to wait for it,
  or set `VECTOR_TIMEOUT`.
* **`configure.sh` ends with `Failed/Skipped: 2`, or a few files have no vectors**: on a fresh Quick Start the summary is
  `Processed 309 documents. Succeeded: 307, Failed/Skipped: 2. Failed: 0, skipped: 2, left pending: 0.` and
  `configure.sh` prints no warning. The two are the 1.7 MB log and the 1.5 MB CSV, too big for `content_chunker.max_chunks_per_document` (see
  [Chunking and what the theme shows](#chunking-and-what-the-theme-shows)): they are marked `skipped` for good and stay
  keyword-only, and running `configure.sh` again does not change that (`Processed 0 documents`). It warns only for
  `Failed: n` or `left pending: n` above 0. A pending file kept changing while the indexer wrote to it, or the model was not
  serving for a moment (`fess-chunk.log` has a `leaving ... pending` line for it): run `bash bin/configure.sh` again;
  the indexer picks it up, as does its daily run. A failed file (`content_chunk_status` `fail`) is not selected again
  unless `content_chunker.job.retry_failed` is true; `fess-chunk.log` has the cause.
* **Changing `MODEL_NAME`, `MODEL_DIMENSION` or `CHUNK_SIZE` has no effect or fails**: the vector dimension is part
  of the index mapping, and chunks and vectors that are already stored are not redone. A new `MODEL_NAME` with the
  same dimension would silently mix the old vectors with a query model that does not match them. Reset the index
  (see [Stop, update, reset](#stop-update-reset)) and run the Quick Start again.
* **Linux permission errors in `data/`**: re-run `bash ./bin/setup.sh` (it uses `sudo chown`), or `sudo chown -R 1001`
  the `data/fess` subdirectories and `sudo chown -R 1000` the `data/opensearch` ones.

## Files

| Path | Purpose |
|---|---|
| `compose.yaml` | Fess, OpenSearch, the `init-semantic` model setup and the optional Samba service |
| `.env.example` | Port, image, theme and hybrid-search overrides |
| `bin/setup.sh` | Directories, theme sync, system.properties seed, sample data |
| `bin/configure.sh` | Crawl config, access token, crawl, chunk vectors |
| `bin/setup-semantic.sh` | Run by `init-semantic`: registers and deploys the embedding model, writes `data/semantic/model_id` |
| `bin/fess-entrypoint.sh` | Fess entrypoint wrapper: passes the model id to Fess as a system property |
| `bin/seed-sample.sh`, `bin/generate_sample.py` | The sample file tree |
| `data/fess/opt/fess/system.properties.template` | Tracked system settings |
