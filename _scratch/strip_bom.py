import pathlib

p = pathlib.Path("pipelines/sec_rag_ingest.py")
data = p.read_bytes()
if data[:3] == b"\xef\xbb\xbf":
    p.write_bytes(data[3:])
    print("BOM stripped")
else:
    print("No BOM found")