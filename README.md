# 北京晚报 Fetcher

Downloads the 北京晚报 (Beijing Evening News) digital edition for a given date — all 版面 merged into one PDF, plus all articles as a plain text file.

## Usage

```bash
# Specific date
python3 bjwb_fetch.py 20260310

# Specific date with custom output directory
python3 bjwb_fetch.py 20260310 --output ~/Downloads/bjwb

# Date range (start end, inclusive)
python3 bjwb_fetch.py 20260301 20260310

# Date range with custom output directory
python3 bjwb_fetch.py 20260301 20260310 --output ~/Downloads/bjwb

# Today's paper (default)
python3 bjwb_fetch.py
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
