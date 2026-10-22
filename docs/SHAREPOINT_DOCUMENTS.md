# SharePoint Documents V0

## Purpose

SharePoint Documents V0 synchronizes one authorized Microsoft Graph drive / SharePoint document library, downloads supported files, extracts deterministic text, and maps document versions into PMWizard SourceRecord objects.

Flow: SharePoint document library → Graph drive delta → SharePoint connector → text extraction → SourceRecord → ConnectorRunner → Ingestion → Evidence.

## Scope and security

One connector configuration targets one drive_id. OAuth secrets and tokens remain outside Project Memory. The connector is read-only and preserves the configured permission_scope on every SourceRecord.

Microsoft Graph documents Files.Read as the least-privileged delegated permission for drive delta and file content download. App-only deployments can use Files.Read.All, while Selected permissions such as Sites.Selected should be evaluated when access must be restricted to explicitly assigned SharePoint resources.

## Incremental synchronization

V0 uses GET /drives/{drive-id}/root/delta and treats @odata.nextLink / @odata.deltaLink as opaque checkpoints. The request sends deltaExcludeParent: true.

Initial sync modes:
- latest (default): establish the current delta token without enumerating the historical library.
- full: enumerate current drive contents so existing supported files can become Evidence.

## Supported content

V0 extracts UTF-8 text from .txt, .md, .csv, .json, .xml, .yaml, .yml, and .log files. DOCX is extracted deterministically from word/document.xml using Python standard-library ZIP/XML parsing.

PDF, XLSX, PPTX, images, OCR, and other binary formats are deferred. Unsupported, deleted, folder, oversized, failed-extraction, and empty-text items are reported as ConnectorSkip records rather than silently discarded.

## Size boundary

The default maximum file size is 10 MiB. Oversized files are skipped before download when Graph metadata supplies size, and the binary HTTP transport also enforces the bound while reading.

## Immutable versions

A SharePoint item keeps its drive item ID when edited, so V0 uses a versioned external identity: <drive-item-id>:<eTag>. A new content version can therefore create new immutable Evidence without overwriting history.

If eTag changes but extracted normalized content is identical, Ingestion V0 deduplicates the version by content hash.

## Deleted items

Delta items with the deleted facet do not delete historical PMWizard Evidence. They are reported as skips. A future source-lifecycle feature may record deletion or move Events explicitly.

## SourceRecord mapping

- source_type: document
- source_system: microsoft_graph_sharepoint
- external_id: drive item ID + eTag/version
- source_reference: SharePoint webUrl
- author: lastModifiedBy user when available
- captured_at/effective_at: lastModifiedDateTime
- content: file name + extracted source text
- permission_scope: configured authorized scope

## Human governance

The connector only creates Evidence. Entity Resolution and Progress Intelligence may later create suggestions, but governed Action Item state still changes only through Human Review.

## Deferred

PDF/Excel/PowerPoint parsing, OCR, source deletion Events, Graph 410 resync orchestration, durable connector configuration/checkpoints, webhook subscriptions, and rate-limit/backoff policies are deferred.

> SharePoint supplies source documents. PMWizard preserves versions, interprets evidence separately, and keeps project truth human-governed.