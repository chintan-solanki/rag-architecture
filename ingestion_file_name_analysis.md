# Analysis: moving fetched files to per-ingestion directories

This is an analysis-only note. No application code was changed while preparing it.

## 1) Current behavior

The current flow encodes the logical metadata into the file name itself:

- upload: `/staging/fetched/{ingestion_id}_{file_name}.pdf`
- filewatcher: same pattern
- URL download: `/staging/fetched/{ingestion_id}_{url-derived-name}.pdf`

The code also sets:

- `ingestion_id`: unique per ingestion job
- `document_id`: currently `"{ingestion_id}_{file_stem}"` in the ingestion service and file watcher

This means every consumer that only sees the file system path has to parse the filename to recover the `ingestion_id` and/or original filename. The repo already does this in `ingestion/src/workers/filewatcher.py` via a regex:

- `DOCUMENT_ID_PREFIX = re.compile(r"^(?P<ingestion_id>[0-9a-fA-F]{32})_(?P<original_file_name>.*)$")`

That is the key smell: the path is being used as a transport format for metadata.

## 2) Why this causes a problem

This design mixes three different concepts into one filename:

1. file identity
2. ingestion job identity
3. user-facing/original file name

That becomes awkward when downstream systems need only the original document name or need to know the ingestion id without parsing the filename. It also makes path-based logic brittle whenever filenames change, contain underscores, paths, or non-standard characters.

In other words, the filename is acting as a serialized event envelope instead of a clean storage path.

## 3) Proposed alternative

The proposed scheme is:

- `/staging/fetched/<ingestion_id>/<original_file_name>.pdf`

This avoids encoding file metadata in the file name and makes the path itself a stable namespace for the ingestion job.

Example:

- `/staging/fetched/8d8a7a8a8b0a4fd4b999f4d6d45cb601/report.pdf`
- `/staging/fetched/8d8a7a8a8b0a4fd4b999f4d6d45cb601/annual-report-2024.pdf`

This is cleaner because:

- the directory identifies the ingestion/job
- the filename stays close to the original document name
- file-system operations no longer require regex parsing
- the LLM-facing metadata can come from structured event fields rather than path manipulation

## 4) What should be passed as metadata instead of filename parsing

The system is already close to the right model: it sends `original_file_name` in Kafka events and stores metadata in documents/ingestion records.

The robust pattern is:

- `ingestion_id` is a job identifier in the ingestion record and Kafka event
- `document_id` is a document identifier used in DB/persisted metadata/indexing
- `original_file_name` is the human-readable file name used for UI and citations
- `dest_file_path` is the storage location and should be treated as a path, not as a business identifier

The important rule is: do not recover business metadata by parsing file names when the same information already exists as explicit fields.

## 5) Should `document_id` simply be the ingestion id?

Short answer: not by default.

### Why it is tempting

It would make the path and document id simpler, and it guarantees uniqueness.

### Why it is risky

This repository already separates the concepts:

- `ingestion_id` is the lifecycle identifier of the ingestion job
- `document_id` is the identity of the document being processed/indexed

The schema in `common/src/common/helpers/dbrepository.py` is structured around that separation:

- `ingestions` table: primary key is `ingestion_id`
- `documents` table: primary key is `document_id`

`document_id` is used across the indexed document model and retrieval metadata; it is not just a convenience label.

If `document_id == ingestion_id`, then:

- every ingestion run would also be the document identity
- duplicate documents or re-ingestion of the same content would all map to a new document id, even when they are effectively the same document
- the system loses the ability to distinguish between "this ingestion job" and "this document entity"
- future features such as deduplication, versioning, comparisons, or re-indexing become harder because the identity is job-scoped rather than document-scoped

This is especially relevant because the code does duplicate-checking by file hash (`find_by_hash`) and then records the associated `document_id` in `documents`.

### Recommendation

Use:

- `ingestion_id`: unique per ingestion job
- `document_id`: a unique identity for the document itself, which may be derived from a hash or a UUID, or it may be `ingestion_id + some stable suffix` if the system intentionally wants a per-document identity that is unique but also includes human-readable metadata

The key point is that the file path should not define the semantics of `document_id`.

## 6) What changes would be required to adopt the directory-based scheme

The required changes are small but spread across a few components. The main ones are:

### A. Storage path creation

Wherever the code writes files to `/staging/fetched`, it should instead create a per-ingestion directory and then write the original-named file inside it.

For example:

- current: `fetched_dir / f"{ingestion_id}_{safe_name}.pdf"`
- proposed: `fetched_dir / ingestion_id / safe_name`

This needs to be done in:

- `api/src/services/ingestion_service.py` for upload API requests
- `ingestion/src/workers/downloader.py` for URL downloads
- `ingestion/src/workers/filewatcher.py` for incoming directory watch behavior

### B. Kafka event payload changes

The event payload already has explicit fields like:

- `ingestion_id`
- `document_id`
- `original_file_name`
- `dest_file_path`

Those fields are already the correct place to carry metadata. The path itself should be a destination, not a metadata encoding scheme.

The main change is only to ensure `dest_file_path` becomes:

- `/staging/fetched/{ingestion_id}/{original_file_name}.pdf`

rather than something like:

- `/staging/fetched/{ingestion_id}_{original_name}.pdf`

No downstream parser should need to infer `ingestion_id` from the basename.

### C. Filewatcher logic

This is the area that currently has the biggest compatibility risk.

`filewatcher.py` contains code that recognizes pre-encoded filenames using a regex to recover:

- `ingestion_id`
- `original_file_name`

That logic would stop matching the new layout, because the folder is now the namespace and the filename is no longer prefixed with the ingestion id.

It would need to be updated to either:

- look for a directory under `/staging/fetched/<ingestion_id>/` rather than a flat filename, or
- use metadata already stored in the ingestion DB/record instead of filename parsing

If the file watcher receives a file dropped into `/staging/incoming`, it can still generate an `ingestion_id` and create the folder before copying.

### D. Migration / compatibility for existing files

The repo currently already writes old-style names in several places. If a deployment moves to the new scheme, old flat files may remain on disk. A migration path is needed if historical files must still be read.

The safest approach is a compatibility window:

- support both old and new path layouts while a migration runs
- emit a warning if a legacy flat file is encountered
- optionally move or rewrite legacy files to the new directory layout once the system is ready

Without this, some old documents may become unreadable when the code expects the new path layout.

## 7) Side effects and risks to watch for

### Low-risk / expected

- Cleaner metadata model
- Easier human debugging of `/staging/fetched`
- Less brittle filename parsing
- Better support for user-visible names without exposing internal IDs in the filename

### Medium-risk / needs care

- `filewatcher.py` regex-based parsing must be updated; otherwise filewatcher may fail to rehydrate client_id or original metadata from a file that already entered the system
- any external tooling or scripts that assume the old flat-file naming convention will need to be updated
- some logs or UI output that currently display `dest_file_name` may need to reflect the actual final path or original file name in a clearer way

### Important semantic risk

Do not conflate `ingestion_id` and `document_id` just because the path layout changes.

The system currently already uses `ingestion_id` and `document_id` differently in the DB, ingestion record, and retrieval metadata. That distinction is useful and should remain.

## 8) Recommended final design

This is the cleanest design for the current architecture:

- keep `ingestion_id` as a unique job identifier
- keep `document_id` as a unique document identifier, not just the ingestion id
- store files under `/staging/fetched/<ingestion_id>/<original_file_name>.pdf`
- pass the original file name via structured metadata (`original_file_name` in Kafka/event/metadata), not by parsing the filename
- keep `dest_file_path` as an absolute path to the file, but never use it as a transport encoding of business metadata

This gives the benefits of the directory scheme without creating a hidden coupling between business IDs and file names.

## 9) Bottom line

Yes, the proposed directory-based scheme is a good idea from a metadata cleanliness and robustness standpoint.

It does not require changing the higher-level concept of `ingestion_id`; it only changes where the file is stored and how the file path is interpreted. That is a good separation of concerns.

I would not recommend making `document_id == ingestion_id` as a general rule. That collapses two different responsibilities into one value and will likely create maintenance problems later when duplicate detection, document lifecycle, and re-ingestion need to be handled cleanly.

The best outcome is:

- storage: directory-based
- metadata: explicit fields instead of file-name parsing
- document identity: separate from ingestion identity

