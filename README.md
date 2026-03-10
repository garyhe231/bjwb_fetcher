# 北京晚报 Fetcher

Downloads the 北京晚报 (Beijing Evening News) digital edition for a given date — all 版面 merged into one PDF, plus all articles as a plain text file.

## Usage

```bash
# Today's paper (default)
python3 bjwb_fetch.py

# Specific date
python3 bjwb_fetch.py 20260310

# Date range (start end, inclusive)
python3 bjwb_fetch.py 20260301 20260310

# With custom output directory
python3 bjwb_fetch.py 20260301 20260310 --output ~/Downloads/bjwb
```

## Accepted Date Formats

The date argument is flexible — all of the following are equivalent:

| Format | Example |
|---|---|
| `YYYYMMDD` | `20260310` |
| `YYYY-MM-DD` | `2026-03-10` |
| `YYYY/MM/DD` | `2026/03/10` |
| `YYYY.MM.DD` | `2026.03.10` |
| `MM/DD/YYYY` | `03/10/2026` |
| `DD/MM/YYYY` | `10/03/2026` |
| `Month DD YYYY` | `March 10 2026` |
| `Mon DD YYYY` | `Mar 10 2026` |
| `Month DD, YYYY` | `March 10, 2026` |
| `DD Month YYYY` | `10 March 2026` |

Formats with spaces should be quoted:
```bash
python3 bjwb_fetch.py "March 10 2026"
python3 bjwb_fetch.py "Mar 1, 2026" "March 10, 2026"
```

## Output

```
bjwb_YYYYMMDD/
├── bjwb_YYYYMMDD.pdf   # all 版面 merged into one PDF
└── bjwb_YYYYMMDD.txt   # all articles in plain text
```

## Requirements

```bash
pip install pillow fpdf2
```

No other third-party dependencies — uses Python standard library for HTTP requests and HTML parsing.
