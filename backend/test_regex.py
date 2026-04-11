import re

raw_phrases = "hey arni,hey arnie,hey ernie,arni,hey are knee,hey arnee".split(",")
raw_phrases.sort(key=len, reverse=True)
escaped = [re.escape(p) for p in raw_phrases]
pattern = r"\b(?:" + "|".join(escaped) + r")\b\s*(.*)"
regex = re.compile(pattern, re.IGNORECASE)

print(regex.search("Arnie heard you"))
print(regex.search("Arni hello wake up"))
print(regex.search("Wake up arni"))

