# Retrieval Source Documents

Store only the required Amazon source PDFs for this assessment in this directory.

Expected files:

- `Amazon-2024-Annual-Report.pdf`
- `AMZN-Q3-2025-Earnings-Release.pdf`
- `AMZN-Q2-2025-Earnings-Release.pdf`

The retrieval ingestion layer in `app/retrieval/service.py` is intentionally locked to those three files and their assignment-provided source URLs so later retrieval stories cannot drift to extra documents.
