import csv
import yaml
import re
from tqdm import tqdm
import pyisbn

# use yaml.CSafeLoader / if available but don't crash if it isn't
try:
    yaml_loader = yaml.CSafeLoader
except (ImportError, AttributeError):
    yaml_loader = yaml.SafeLoader

try:
    yaml_dumper = yaml.CSafeDumper
except (ImportError, AttributeError):
    yaml_dumper = yaml.SafeDumper

def normalize_isbn(isbn):
    return isbn.upper().replace("-", "").replace(" ", "")

def well_formed(isbn):
    # assumes isbn is normalized
    match = re.search(r'^(\d{9}[0-9X]|\d{7}[0-9X]|\d{13})$', isbn)
    return True if match else False

def valid(isbn):
    # assumes isbn is normalized
    match = re.search(r'^(\d{9}|\d{12})(\d|X)$', isbn)
    if not match:
        return False

    digits = match.group(1)
    check_digit = 10 if match.group(2) == 'X' else int(match.group(2))
    result = sum((i + 1) * int(digit) for i, digit in enumerate(digits))
    if len(isbn) == 10:
        return (result % 11) == check_digit
    else:
        return (result % 10) == check_digit

def looksgood(isbn):
    if not well_formed(isbn):
        return False
    if not isbn.startswith("978") and not isbn.startswith("979"):
        return False
    return pyisbn.validate(isbn)

def comatible(num1, num2):
    if not num1 or not num2:
        return True
    if len(num1) == len(num2):
        return num1 == num2
    shortnum = num1 if len(num1) < len(num2) else num2
    longnum = num2 if len(num1) < len(num2) else num1
    if len(longnum) != 13 or (len(shortnum) != 8 and len(shortnum) != 10):
        return False
    if len(shortnum) == 10:
        return num1[:9] == num2[3:12]
    else:
        return num1[:7] == num2[3:12]

stats = {
    "unique_isbns": {"old": 0, "new": 0},
    "unique_issns": {"old": 0, "new": 0},
}


# reviewed_db has format:
# mw:
#   ean: [...]
#   isbn: [...]
#   issn: [...]
#   volume_numbers = []
#   volume_nums_compatible: bool
#   volumes: (optional)
#      volnum: x
#      ean: [...]
#      isbn: [...]
#      issn: [...]
#      in: [...]

def guess_id_type(num):
    if len(num) == 8:
        return "issn"
    if len(num) == 2:
        return "in"
    if len(num) != 13:
        # case of len(num) == 10 (most common) or anything weird
        return "isbn"
    if num.startswith("977"):
        return "issn"
    if num.startswith("978") or num.startswith("979"):
        return "isbn"
    return "ean"

def keeps_all_compatible(num, nums):
    for n in nums:
        if not comatible(num, n):
            return False
    return True

def add_csv(reviewed_db, path, cols, multi, canhaveean=True):
    with open(path, newline='') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)
        mwinfo = {}
        for row in reader:
            if len(row) < 1 or not row[0] or not row[0].startswith("MW"):
                continue
            mw = row[0]
            if mw not in reviewed_db:
                reviewed_db[mw] = {"ean": set(), "isbn": set(), "issn": set(), "volume_nums_compatible": True, "volumes": {}}
            vnum = row[1] if multi else None
            for col in cols:
                if len(row) <= col or not row[col]:
                    continue
                ids = row[col].split(',')
                for num in ids:
                    num = normalize_isbn(num)
                    t = guess_id_type(num)
                    if t == "ean" and not canhaveean:
                        t = "isbn"
                    if t != "in":
                        if reviewed_db[mw]["volume_nums_compatible"]:
                            reviewed_db[mw]["volume_nums_compatible"] = keeps_all_compatible(num, reviewed_db[mw][t])
                        reviewed_db[mw][t].add(num)
                    if vnum:
                        if vnum not in reviewed_db[mw]["volumes"]:
                            reviewed_db[mw]["volumes"][vnum] = {"ean": set(), "isbn": set(), "issn": set(), "in": set()}
                        reviewed_db[mw]["volumes"][vnum][t].add(num)


def get_w_to_mw():
    res = {}
    with open('mw-w-ig-vn.csv', newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            res[row[1]] = row[0]
    return res

# data["isbn_info"]
#   isbn:
#      mw:
#        "db": isbn from bdrc
#        w:
#          ig: [imgfname]
# data["mw_info"]
#   mw:
#     from_db: [isbns]
#     from_scans: [isbns]

def normalize_from_db(isbn):
    if '(' in isbn:
        isbn = isbn[:isbn.find('(')]
    if '/' in isbn:
        isbn = isbn[:isbn.find('/')]
    return normalize_isbn(isbn)

def analyze_w(w, w_dbinfo, mw, reviewed_db):
    for ig, iginfo in w_dbinfo.items():
        seen_isbns = []
        volnum = -1
        if "n" in iginfo:
            volnum = iginfo["n"]
        for imgfname, detections in iginfo.items():
            if imgfname == "n":
                continue
            num = None
            for det in detections:
                if det["t"] != "EAN13":
                    continue
                if (det["d"].startswith("977") or det["d"].startswith("978") or det["d"].startswith("979")) and well_formed(det["d"]):
                    num = det["d"]
                else:
                    #print(det["d"]+" is malformed")
                    if num is None:
                        num = det["d"]
            if num is None:
                continue
            if mw not in reviewed_db:
                #print("num for %s not in reviewed_db" % mw)
                return
            t = guess_id_type(num)
            if num in reviewed_db[mw][t]:
                continue
            reviewed_db[mw][t].add(num)
            if not reviewed_db[mw]["volume_nums_compatible"]:
                reviewed_db[mw][t].add(num)
                if volnum not in reviewed_db[mw]["volumes"]:
                    reviewed_db[mw]["volumes"][volnum] = {"ean": set(), "isbn": set(), "issn": set(), "in": set()}
                reviewed_db[mw]["volumes"][volnum][t].add(num)

def get_mw_infos(data):
    # todo: handle cases like "8189165275, 9788189165277" which are isbn10, isbn13 of same isbn
    with open('mw-isbn.csv', newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            mw = row[0]
            orig_isbn_str = row[1]
            orig_isbns = re.split(',|;', orig_isbn_str)
            normalized_isbns = []
            for orig_isbn in orig_isbns:
                normalized_isbn = normalize_from_db(orig_isbn)
                if normalized_isbn:
                    normalized_isbns.append(normalized_isbn)
            if len(normalized_isbns) != 1 or normalized_isbns[0] != orig_isbn_str:
                data[mw] = normalized_isbns

def main():
    db = None
    with open("db.yml", 'r') as stream:
        db = yaml.load(stream, Loader=yaml_loader)
    w_to_mw = get_w_to_mw()
    existing_isbns = {}
    get_mw_infos(existing_isbns)
    reviewed_db = {}
    add_csv(reviewed_db, "reviewed_files/ISBN review step 1 - Karma-malformed (to review).csv", [2], False, False)
    add_csv(reviewed_db, "reviewed_files/ISBN review step 1 - new isbns (review those with ).csv", [1,2], False, True)
    add_csv(reviewed_db, "reviewed_files/ISBN review step 1 - substitutions (to review).csv", [2], False, True)
    add_csv(reviewed_db, "reviewed_files/ISBN review step 1 - new multi volumes ISBN (no review ).csv", [2, 3], True, True)
    add_csv(reviewed_db, "reviewed_files/ISBN review step 1 - multiple volumes (to review).csv", [3], True, True)
    print("reviewed_db has %s mws" % len(reviewed_db))
    for w in tqdm(db):
        w_dbinfo = db[w]
        if w not in w_to_mw:
            # weird case where some spurious ws are in the db with no data
            continue
        mw = w_to_mw[w]
        analyze_w(w, w_dbinfo, mw, reviewed_db)
    for mw, mw_existing_isbns in existing_isbns.items():
        if mw not in reviewed_db:
            reviewed_db[mw] = {"ean": set(), "isbn": set(), "issn": set(), "volume_nums_compatible": True, "volumes": {}}
            for mw_existing_isbn in mw_existing_isbns:
                t = guess_id_type(mw_existing_isbn)
                if t == "in":
                    continue
                reviewed_db[mw][t].add(mw_existing_isbn)
    monovolumes_rows = [] # mw, isbns, issns, eans
    multivolumes_rows = [] # mw, volnum, isbns, issns, eans, ins
    for mw, mwinfo in reviewed_db.items():
        if mwinfo["volume_nums_compatible"] or len(mwinfo["volumes"]) < 2:
            monovolumes_rows.append([mw, ",".join(mwinfo["isbn"]), ",".join(mwinfo["issn"]), ",".join(mwinfo["ean"])])
        else:
            monovolumes_rows.append([mw, "", "", ""])
            for volnum, volinfo in mwinfo["volumes"].items():
                multivolumes_rows.append([mw, volnum, ",".join(volinfo["isbn"]), ",".join(volinfo["issn"]), ",".join(volinfo["ean"]), ",".join(volinfo["in"])])
                #if volinfo["ean"]:
                #    print(volinfo)
    with open('analysis/reviewed_for_versions.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
        for row in monovolumes_rows:
            writer.writerow(row)
    with open('analysis/reviewed_for_outlines.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
        for row in multivolumes_rows:
            writer.writerow(row)

main()
#print(guess_id_type("9787040119916"))