import csv
import yaml
import re
from tqdm import tqdm

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
    match = re.search(r'^(\d{9}[0-9X]|\d{12}[0-9X])$', isbn)
    return True if match else False

def valid(isbn):
    # assumes isbn is normalized
    match = re.search(r'^(\d{9})(\d|X)$', isbn)
    if not match:
        return False

    digits = match.group(1)
    check_digit = 10 if match.group(2) == 'X' else int(match.group(2))
    result = sum((i + 1) * int(digit) for i, digit in enumerate(digits))
    return (result % 11) == check_digit

def normalize_from_db(isbn):
    if '(' in isbn:
        isbn = isbn[:isbn.find('(')]
    return normalize_isbn(isbn)

def get_mw_infos(data):
    # todo: handle cases like "8189165275, 9788189165277" which are isbn10, isbn13 of same isbn
    with open('mw-isbn.csv', newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            mw = row[0]
            orig_isbn_str = row[1]
            orig_isbns = re.split(',|;', orig_isbn_str)
            for orig_isbn in orig_isbns:
                normalized_isbn = normalize_from_db(orig_isbn)
                if normalized_isbn not in data["isbn_info"]:
                    data["isbn_info"][normalized_isbn] = {}
                if mw not in data["isbn_info"][normalized_isbn]:
                    data["isbn_info"][normalized_isbn][mw] = {}
                data["isbn_info"][normalized_isbn][mw]["from_db"] = True

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

def analyze_w(w, w_dbinfo, mw, data, stats):
    this_isbn_info = {}
    seen_isbns = []
    for ig, iginfo in w_dbinfo.items():
        volnum = -1
        for imgfname, detections in iginfo.items():
            if imgfname == "n":
                volnum = detections
                continue
            for det in detections:
                if det["t"] == "EAN13":
                    isbn = det["d"]
                    if isbn in seen_isbns:
                        continue
                    else:
                        if seen_isbns:
                            print("two different isbns in "+w)
                        seen_isbns.append(isbn)
                    this_isbn_info[isbn] = {"ig": ig, "fname": imgfname}
                    if isbn not in data["isbn_info"]:
                        data["isbn_info"][isbn] = {}
                    data["isbn_info"][isbn] = {}
                    if mw not in data["isbn_info"][isbn]:
                        data["isbn_info"][isbn][mw] = {}
                    if w not in data["isbn_info"][isbn][mw]:
                        data["isbn_info"][isbn][mw][w] = {}
                    if ig not in data["isbn_info"][isbn][mw][w]:
                        data["isbn_info"][isbn][mw][w][ig] = []
                    data["isbn_info"][isbn][mw][w][ig].append(imgfname)

def handle_duplicates(data, stats):
    for isbn, isbn_data in data["isbn_info"].items():
        mws = isbn_data.keys()
        if len(mws) > 1:
            print(isbn+" present in multiple instances: "+", ".join(mws))
            stats["isbn_used_multiple_times"] += 1


def main():
    db = None
    with open("db.yml", 'r') as stream:
        db = yaml.load(stream, Loader=yaml_loader)
    w_to_mw = get_w_to_mw()
    stats = {
        "total": 0,
        "same_as_db": 0,
        "different_from_db": 0,
        "not_in_db": 0,
        "db_not_found": 0,
        "isbn_used_multiple_times": 0
    }
    data = {
        "new": {},
        "check_different": {},
        "same_isbn": {},
        "isbn_info": {}
    }
    get_mw_infos(data)
    for w in tqdm(db):
        w_dbinfo = db[w]
        if w not in w_to_mw:
            # weird case where some spurious ws are in the db with no data
            continue
        mw = w_to_mw[w]
        analyze_w(w, w_dbinfo, mw, data, stats)
    handle_duplicates(data, stats)
    stats["total"] = len(data["isbn_info"].keys())
    print(stats)

main()