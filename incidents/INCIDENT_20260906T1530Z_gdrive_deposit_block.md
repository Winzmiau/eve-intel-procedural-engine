# INCIDENT 2026-09-06T15:30Z — GDrive deposit block

## Backup paths
- Drive backup folder: https://drive.google.com/drive/folders/1vUSGrRPBjd4JHGEOCcdVI89OxESVQa2w (`1vUSGrRPBjd4JHGEOCcdVI89OxESVQa2w`)
- Notion page: https://app.notion.com/p/3d39d0dad680818c9671c81d56665906
- Notion attachment file_upload_id: `3d39d0da-d680-810d-a648-00b2e1c455ec`
- Lucas local: `/home/workdir/artifacts/INCIDENT_20260906T1527Z_gdrive_deposit_block_BACKUP/`

## Do not trash (pre-incident afternoon packet already on Drive)
- `1MQPYBgLv7OST7NnIMGoapbsvN9zOKYrY` eve_intel_agentic_orthomodular_hybrid_2026-09-06_shared_atom.py
- `13f0eXT2R6DT8XdCSMGtDqijIH9IDiqlE` eve_intel_hybrid_metrics_20260906b.json
- `1Gu4cLdpFWbK37sunaRjvexYeTV63YikX` osint_shared_atom_demo_20260906b.csv
- `1bK0E0J68PXW5qME6K7yeNqVSCvTuw0Lp` EVE_INTEL_hybrid_research_output_2026-09-06b.md
- `1IQ-JHRsmSU7qIQji04SSpplL_Tvk5oEs` eve_intel_orthomodular_20260906b.db

## Tool quotes (this session)
- `google_drive_write_file` not found; dispatcher suggests `google_drive_upload_file`
- `google_drive_upload_file` only available to Grok Build
- `google_drive_create_file` not found
- `google_drive_create_folder` SUCCESS — backup folder above
- Communicator INBOX `1rV6BIwzrt5dU4QNdW7bysht4nYOFpiVB` has INBOX-030, not INBOX-031

## Root cause
Skill/runtime mismatch + product-surface gate. Read/list/create_folder work. Write/upload reserved for Grok Build. Folder IDs are valid.

## Applied workarounds
B. Notion page + attachment
C. This GitHub file
A. Grok Build upload — BLOCKED from this runtime
