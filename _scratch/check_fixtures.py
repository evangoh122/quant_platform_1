import json

d = json.load(open("tests/rag/fixtures/sec/submissions_recent.json"))
files = d.get("filings", {}).get("files", [])
for f in files:
    name = f.get("name", "")
    url = f"https://data.sec.gov/submissions/{name}"
    print(f"Name: {name}")
    print(f"URL: {url}")
    print(f"filingFrom: {f.get('filingFrom')}")
    print(f"filingTo: {f.get('filingTo')}")
    print()