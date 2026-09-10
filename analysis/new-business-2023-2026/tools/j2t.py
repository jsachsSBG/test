import json, sys
src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src)); recs = d["records"]
keys = []
for r in recs:
    for k in r:
        if k != "attributes" and k not in keys: keys.append(k)
with open(dst, "w") as f:
    f.write("\t".join(keys) + "\n")
    for r in recs:
        f.write("\t".join("" if r.get(k) is None else str(r.get(k)).replace("\t"," ").replace("\n"," ") for k in keys) + "\n")
print(dst.split("/")[-1], len(recs), d.get("totalSize"), d.get("done"))
