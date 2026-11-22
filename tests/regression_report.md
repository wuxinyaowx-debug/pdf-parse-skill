# Regression report (measured, not estimated)

- environment: python 3.12.5; pdftotext=yes; pdftoppm=yes; tesseract=MISSING (OCR paths NOT RUN)
- total checks: 77, passed: 77, failed: 0
- OCR end-to-end: NOT RUN (tesseract missing) — TSV coordinate conversion unit-checked instead

## singlecol — 18/18 checks passed, 0.16s, status=success
- [PASS] text contains: deep parsing of single column articles
- [PASS] text contains: alice example, bob sample
- [PASS] text contains: keywords: layout; parsing; metadata
- [PASS] text contains: doi: 10.1234/jscs.2024.0001
- [PASS] text contains: 3 results reported below illustrate this requireme
- [PASS] reading order (4 anchors)
- [PASS] section found: Abstract
- [PASS] section found: 1 Introduction
- [PASS] section found: 2 Discussion
- [PASS] section found: References
- [PASS] no false heading: 3 results reported below illustrate this
- [PASS] refs count == 2
- [PASS] tables count == 0
- [PASS] equations count == 0
- [PASS] metadata title
- [PASS] metadata doi
- [PASS] metadata keywords
- [PASS] bbox validity (11 boxes)

## twocol — 21/21 checks passed, 0.21s, status=success
- [PASS] text contains: a study of synthetic layout parsing
- [PASS] text contains: jane doe, john smith
- [PASS] text contains: department of testing, example university
- [PASS] reading order (12 anchors)
- [PASS] section found: Abstract
- [PASS] section found: 1 Introduction
- [PASS] section found: 2 Method
- [PASS] section found: 2.1 Layout extraction
- [PASS] section found: 2.2 Structure recognition
- [PASS] section found: 3 Results
- [PASS] section found: 4 Conclusion
- [PASS] section found: References
- [PASS] refs count == 3
- [PASS] tables count == 1
- [PASS] figures count == 1
- [PASS] equations count == 1
- [PASS] running matter removed: journal of synthetic tests, vol. 7
- [PASS] running matter absent from body: journal of synthetic tests, vo
- [PASS] metadata title
- [PASS] metadata authors
- [PASS] bbox validity (25 boxes)

## threecol — 7/7 checks passed, 0.11s, status=success
- [PASS] reading order (6 anchors)
- [PASS] section found: 1 Introduction
- [PASS] section found: 2 Middle Column
- [PASS] section found: 3 Final Column
- [PASS] section found: References
- [PASS] refs count == 1
- [PASS] bbox validity (11 boxes)

## mixedlayout — 7/7 checks passed, 0.11s, status=success
- [PASS] reading order (5 anchors)
- [PASS] section found: 1 Introduction
- [PASS] section found: 2 Early Right
- [PASS] section found: 3 After Band
- [PASS] refs count == 1
- [PASS] tables count == 1
- [PASS] bbox validity (10 boxes)

## table — 11/11 checks passed, 0.11s, status=success
- [PASS] reading order (3 anchors)
- [PASS] tables count == 1
- [PASS] table cell present: 91.2
- [PASS] table cell present: 88.4
- [PASS] table cell present: 93.5
- [PASS] table cell present: 90.1
- [PASS] table cell present: news
- [PASS] table cell present: wiki
- [PASS] table cell present: acc
- [PASS] table cell present: f1
- [PASS] bbox validity (7 boxes)

## equations — 6/6 checks passed, 0.11s, status=success
- [PASS] reading order (3 anchors)
- [PASS] equations count == 2
- [PASS] equation number 1 found
- [PASS] equation number 2 found
- [PASS] prose not misread as equation: see also the earlier review
- [PASS] bbox validity (9 boxes)

## scanned — 2/2 checks passed, 0.13s, status=unreadable
- [PASS] status in ['unreadable', 'partial']
- [PASS] bbox validity (0 boxes)

## mixedlayer — 4/4 checks passed, 0.18s, status=partial
- [PASS] text contains: this page has a normal text layer
- [PASS] status in ['partial', 'success']
- [PASS] image page 2 flagged
- [PASS] bbox validity (4 boxes)

## unit checks
- [PASS] ocr tsv conversion (300dpi px -> pt) — got (72.0, 144.0, 108.0, 158.4), want (72, 144, 108, 158.4)