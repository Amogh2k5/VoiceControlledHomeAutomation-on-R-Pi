import csv, json, collections, re, sys, math
csv_path = r"B:\Home_auto\data\voice_benchmark\segments\benchmark_report.csv"
rows = []
with open(csv_path, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

print("Total rows:", len(rows))
vosk_nonempty = sum(1 for r in rows if r['vosk_text'].strip())
sherpa_nonempty = sum(1 for r in rows if r['sherpa_text'].strip())
print("Vosk non-empty:", vosk_nonempty, "Sherpa non-empty:", sherpa_nonempty)

def tokens(text):
    return re.findall(r"[a-z']+", text.lower())

vosk_tokens = collections.Counter()
sherpa_tokens = collections.Counter()
for r in rows:
    for t in tokens(r['vosk_text']):
        vosk_tokens[t]+=1
    for t in tokens(r['sherpa_text']):
        sherpa_tokens[t]+=1

print("\nTop Vosk tokens:")
for w,c in vosk_tokens.most_common(30):
    print(w,c)
print("\nTop Sherpa tokens:")
for w,c in sherpa_tokens.most_common(30):
    print(w,c)

device_keywords = ["light","lights","fan","tv","ac","plug","geyser","exhaust","garden","kitchen","bedroom","water","pump","guard","hall","office","living","room"]
print("\nVosk device keyword counts:")
for kw in device_keywords:
    cnt = sum(1 for r in rows if kw in r['vosk_text'].lower())
    if cnt:
        print(kw, cnt)
print("\nSherpa device keyword counts:")
for kw in device_keywords:
    cnt = sum(1 for r in rows if kw in r['sherpa_text'].lower())
    if cnt:
        print(kw, cnt)

action_keywords = ["on","off","switch","turn"]
print("\nVosk action counts:")
for kw in action_keywords:
    cnt = sum(1 for r in rows if kw in r['vosk_text'].lower())
    print(kw, cnt)
print("\nSherpa action counts:")
for kw in action_keywords:
    cnt = sum(1 for r in rows if kw in r['sherpa_text'].lower())
    print(kw, cnt)

vosk_success = sum(1 for r in rows if r['vosk_success']=='True')
sherpa_success = sum(1 for r in rows if r['sherpa_success']=='True')
print("\nVosk parse success:", vosk_success)
print("Sherpa parse success:", sherpa_success)

# Identify recurring substitution patterns: compare tokens where both non-empty
pair_tokens = collections.Counter()
for r in rows:
    vt = set(tokens(r['vosk_text']))
    st = set(tokens(r['sherpa_text']))
    # common tokens
    for t in vt & st:
        pair_tokens[t]+=1
print("\nCommon tokens in both:")
for w,c in pair_tokens.most_common(20):
    print(w,c)

# Unique to Vosk
unique_vosk = collections.Counter()
unique_sherpa = collections.Counter()
for r in rows:
    vt = set(tokens(r['vosk_text']))
    st = set(tokens(r['sherpa_text']))
    for t in vt - st:
        unique_vosk[t]+=1
    for t in st - vt:
        unique_sherpa[t]+=1
print("\nTokens unique to Vosk (top 20):")
for w,c in unique_vosk.most_common(20):
    print(w,c)
print("\nTokens unique to Sherpa (top 20):")
for w,c in unique_sherpa.most_common(20):
    print(w,c)

# Gather examples for each major error pattern: e.g., "switch on" recognized but device missed.
# We'll just collect a few segments where parse fails for each model.
vosk_fail_examples = []
sherpa_fail_examples = []
for r in rows:
    if r['vosk_success']!='True' and r['vosk_text'].strip():
        vosk_fail_examples.append((r['segment'], r['vosk_text'], r['vosk_error']))
    if r['sherpa_success']!='True' and r['sherpa_text'].strip():
        sherpa_fail_examples.append((r['segment'], r['sherpa_text'], r['sherpa_error']))

print("\nVosk parse failure examples (first 10):")
for seg, txt, err in vosk_fail_examples[:10]:
    print(seg, txt, err)
print("\nSherpa parse failure examples (first 10):")
for seg, txt, err in sherpa_fail_examples[:10]:
    print(seg, txt, err)