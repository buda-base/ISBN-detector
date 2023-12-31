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
    match = re.search(r'^(\d{9}[0-9X]|\d{13})$', isbn)
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

def addqm(isbn):
    if looksgood(isbn):
        return isbn
    else:
        return isbn+"?"

def join_addqm(isbn_list):
    new_list = []
    for isbn in isbn_list:
        new_list.append(addqm(isbn))
    return ", ".join(new_list)

def equivalent(isbn1, isbn2):
    if isbn1 is None and isbn2 is None:
        return True
    if isbn1 is None or isbn2 is None:
        return False
    if len(isbn1) == len(isbn2):
        return isbn1 == isbn2
    if len(isbn1) not in [10, 13] or len(isbn2) not in [10, 13]:
        return isbn1 == isbn2
    if len(isbn1) == 10:
        return isbn1[:9] == isbn2[3:12]
    else:
        return isbn1[3:12] == isbn2[:9]

def has_equivalent_in(isbn, isbn_list):
    if not isbn_list:
        return False
    for isbn_i in isbn_list:
        if equivalent(isbn_i, isbn):
            return True
    return False

def normalize_from_db(isbn):
    if '(' in isbn:
        isbn = isbn[:isbn.find('(')]
    if '/' in isbn:
        isbn = isbn[:isbn.find('/')]
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
                #if not well_formed(normalized_isbn):
                #    print("ignore from db: mw: "+mw+", isbn: "+normalized_isbn)
                #    continue
                if normalized_isbn not in data["isbn_info"]:
                    data["isbn_info"][normalized_isbn] = {}
                if mw not in data["isbn_info"][normalized_isbn]:
                    data["isbn_info"][normalized_isbn][mw] = {}
                data["isbn_info"][normalized_isbn][mw]["from_db"] = True
                if mw not in data["mw_info"]:
                    data["mw_info"][mw] = {"from_db": [], "from_scans": [], "from_scans": [], "per_ig": {}, "ig_to_vnum": {}}
                data["mw_info"][mw]["from_db"].append(normalized_isbn)

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

def analyze_w(w, w_dbinfo, mw, data, stats):
    for ig, iginfo in w_dbinfo.items():
        seen_isbns = []
        volnum = -1
        for imgfname, detections in iginfo.items():
            if imgfname == "n":
                volnum = detections
                if mw not in data["mw_info"]:
                    data["mw_info"][mw] = {"from_db": [], "from_scans": [], "per_ig": {}, "ig_to_vnum": {}}
                data["mw_info"][mw]["ig_to_vnum"][ig] = volnum
                continue
            isbn = None
            for det in detections:
                if det["t"] != "EAN13":
                    continue
                if (det["d"].startswith("978") or det["d"].startswith("979")) and well_formed(det["d"]):
                    isbn = det["d"]
                else:
                    #print(det["d"]+" is malformed")
                    if isbn is None:
                        isbn = det["d"]
            if isbn is None:
                continue
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
            if mw not in data["mw_info"]:
                data["mw_info"][mw] = {"from_db": [], "from_scans": [], "per_ig": {}, "ig_to_vnum": {}}
            data["mw_info"][mw]["from_scans"].append(isbn)
            if ig not in data["mw_info"][mw]["per_ig"]:
                data["mw_info"][mw]["per_ig"][ig] = []
            if isbn not in data["mw_info"][mw]["per_ig"][ig]:
                data["mw_info"][mw]["per_ig"][ig].append(isbn)

def handle_duplicates(data, stats):
    for isbn, isbn_data in data["isbn_info"].items():
        mws = isbn_data.keys()
        if len(mws) > 1:
            print(isbn+" present in multiple instances: "+", ".join(mws))
            stats["isbn_used_multiple_times"] += 1

def handle_differences(data, stats):
    for mw, mw_data in data["mw_info"].items():
        from_db_not_in_scans = set(mw_data["from_db"]) - set(mw_data["from_scans"])
        stats["in_db_not_in_scans"] += len(from_db_not_in_scans)
        from_scans_not_in_db = set(mw_data["from_scans"]) - set(mw_data["from_db"])
        stats["in_scans_not_in_db"] += len(from_scans_not_in_db)
        #if from_db_not_in_scans and from_scans_not_in_db:
        #    print(mw+" has isbns in db not in scans: "+", ".join(from_db_not_in_scans)+" and isbns in scans not in db: "+", ".join(from_scans_not_in_db))
        #elif from_db_not_in_scans:
        #    print(mw+" has isbns in db not in scans: "+", ".join(from_db_not_in_scans))
        #elif from_scans_not_in_db:
        #    print(mw+" has isbns in scans not in db: "+", ".join(from_scans_not_in_db))
        if len(mw_data["from_db"]) == 1 and len(mw_data["from_scans"]) == 1:
            if not well_formed(mw_data["from_db"][0]):
                data["proposed_substitutions_malformed"].append([mw, mw_data["from_db"][0], addqm(mw_data["from_scans"][0])])
            elif mw_data["from_db"][0] != mw_data["from_scans"][0]:
                if equivalent(mw_data["from_db"][0], mw_data["from_scans"][0]):
                    data["new_isbns"].append([mw, addqm(mw_data["from_scans"][0]), mw_data["from_db"][0], ""])
                else:
                    data["proposed_substitutions"].append([mw, mw_data["from_db"][0], addqm(mw_data["from_scans"][0])])
        if len(mw_data["from_db"]) == 1 and len(mw_data["from_scans"]) == 0 and not well_formed(mw_data["from_db"][0]):
            data["malformed_to_review"].append([mw, mw_data["from_db"][0]])
        if len(mw_data["from_db"]) == 0 and len(mw_data["from_scans"]) == 1:
            data["new_isbns"].append([mw, addqm(mw_data["from_scans"][0]), "", ""])


def handle_multivolumes(data, stats):
    for mw, mwinfo in data["mw_info"].items():
        if len(mwinfo["ig_to_vnum"]) < 2 or len(mwinfo["per_ig"]) == 0:
            continue
        ordered_igs = sorted(mwinfo["ig_to_vnum"].keys(), key=lambda x: mwinfo["ig_to_vnum"][x])
        all_isbns = []
        for ig, isbn_list in mwinfo["per_ig"].items():
            for isbn in isbn_list:
                if isbn in all_isbns:
                    continue
                all_isbns.append(isbn)
        if len(mwinfo["ig_to_vnum"]) == len(mwinfo["per_ig"]):
            stats["found_all_volumes"] += 1
            stats["nb_volumes_found_after_first"] += len(mwinfo["per_ig"])
            if len(all_isbns) == 1:
                if len(mwinfo["from_db"]) == 0:
                    data["new_isbns"].append([mw, isbn_list[0], "", "found on all "+str(len(mwinfo["per_ig"]))+" volumes"])
                elif len(mwinfo["from_db"]) == 1:
                    if mwinfo["from_db"][0] != isbn_list[0]:
                        if equivalent(mwinfo["from_db"][0], isbn_list[0]):
                            data["new_isbns"].append([mw, addqm(isbn_list[0]), mwinfo["from_db"][0], "found on all "+str(len(mwinfo["per_ig"]))+" volumes"])
                        else:
                            data["proposed_substitutions"].append([mw, mwinfo["from_db"][0], addqm(mwinfo["from_scans"][0]), "found on all "+str(len(mwinfo["per_ig"]))+" volumes"])
                else:
                    data["proposed_substitutions"].append([mw, mwinfo["from_db"][0], addqm(mwinfo["from_scans"][0]), "found on all "+str(len(mwinfo["per_ig"]))+" volumes"])
            else:
                if len(mwinfo["from_db"]) == 0 or (len(mwinfo["from_db"]) == 1 and has_equivalent_in(mwinfo["from_db"][0], all_isbns)):
                    data["mutli_volumes_diff_isbn_no_review"][mw] = []
                    for ig in ordered_igs:
                        data["mutli_volumes_diff_isbn_no_review"][mw].append([mwinfo["ig_to_vnum"][ig], join_addqm(mwinfo["per_ig"][ig])])
                else:
                    data["mutli_volumes_diff_isbn_review"][mw] = []
                    for ig in ordered_igs:
                        data["mutli_volumes_diff_isbn_review"][mw].append([mwinfo["ig_to_vnum"][ig], ", ".join(mwinfo["from_db"]), join_addqm(mwinfo["per_ig"][ig])])
        else:
            stats["found_not_all_volumes"] += 1
            stats["nb_volumes_found_after_first"] += len(mwinfo["per_ig"])
            stats["nb_volumes_not_found_after_first"] += len(mwinfo["ig_to_vnum"]) - len(mwinfo["per_ig"])
            volumesfound = []
            for ig in mwinfo["per_ig"]:
                volumesfound.append(mwinfo["ig_to_vnum"][ig])
            volumesfound = sorted(volumesfound)
            volumesfound = [str(x) for x in volumesfound]
            if len(all_isbns) == 1 and len(mwinfo["per_ig"]) > 1:
                if len(mwinfo["from_db"]) == 0:
                    data["new_isbns"].append([mw, isbn_list[0], "", "found on "+str(len(mwinfo["per_ig"]))+"/"+str(len(mwinfo["ig_to_vnum"]))+" volumes"])
                elif len(mwinfo["from_db"]) == 1:
                    if mwinfo["from_db"][0] != isbn_list[0]:
                        if equivalent(mwinfo["from_db"][0], isbn_list[0]):
                            data["new_isbns"].append([mw, addqm(isbn_list[0]), mwinfo["from_db"][0], "found on volumes "+", ".join(volumesfound)+" (no other isbn found)"])
                        else:
                            data["proposed_substitutions"].append([mw, mwinfo["from_db"][0], addqm(mwinfo["from_scans"][0]), "found on volumes "+", ".join(volumesfound)+" (no other isbn found)"])
                else:
                    data["proposed_substitutions"].append([mw, mwinfo["from_db"][0], mwinfo["from_scans"][0], "found on volumes "+", ".join(volumesfound)+" (no other isbn found)"])
            else:
                data["mutli_volumes_diff_isbn_review"][mw] = []
                for ig in ordered_igs:
                    data["mutli_volumes_diff_isbn_review"][mw].append([mwinfo["ig_to_vnum"][ig], ", ".join(mwinfo["from_db"]), join_addqm(mwinfo["per_ig"][ig]) if ig in mwinfo["per_ig"] else "?"])

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
        "isbn_used_multiple_times": 0,
        "in_db_not_in_scans": 0,
        "in_scans_not_in_db": 0,
        "found_all_volumes": 0,
        "found_not_all_volumes": 0,
        "nb_volumes_found_after_first": 0,
        "nb_volumes_not_found_after_first": 0,
    }
    data = {
        "new": {},
        "check_different": {},
        "same_isbn": {},
        "isbn_info": {},
        "mw_info": {},
        "proposed_substitutions": [],
        "proposed_substitutions_malformed": [],
        "malformed_to_review": [],
        "new_isbns": [],
        "mutli_volumes_diff_isbn_no_review": {},
        "mutli_volumes_diff_isbn_review": {}
    }
    get_mw_infos(data)
    for w in tqdm(db):
        w_dbinfo = db[w]
        if w not in w_to_mw:
            # weird case where some spurious ws are in the db with no data
            continue
        mw = w_to_mw[w]
        analyze_w(w, w_dbinfo, mw, data, stats)
    # handle_duplicates(data, stats)
    handle_differences(data, stats)
    handle_multivolumes(data, stats)
    data["proposed_substitutions_malformed"] = sorted(data["proposed_substitutions_malformed"], key=lambda x: x[0])
    data["proposed_substitutions"] = sorted(data["proposed_substitutions"], key=lambda x: x[0])
    data["malformed_to_review"] = sorted(data["malformed_to_review"], key=lambda x: x[0])
    with open('analysis/simple_substitutions_malformed.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
        for row in data["proposed_substitutions_malformed"]:
            writer.writerow(row)
    with open('analysis/simple_substitutions.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
        for row in data["proposed_substitutions"]:
            writer.writerow(row)
    with open('analysis/malformed_toreview.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
        for row in data["malformed_to_review"]:
            writer.writerow(row)
    with open('analysis/new_isbns.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
        for row in data["new_isbns"]:
            writer.writerow(row)
    with open('analysis/mutli_volumes_diff_isbn_review.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
        for mw in sorted(data["mutli_volumes_diff_isbn_review"].keys()):
            for e in data["mutli_volumes_diff_isbn_review"][mw]:
                writer.writerow([mw]+ e)
            writer.writerow([])
    with open('analysis/mutli_volumes_diff_isbn_no_review.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)
        for mw in sorted(data["mutli_volumes_diff_isbn_no_review"].keys()):
            for e in data["mutli_volumes_diff_isbn_no_review"][mw]:
                writer.writerow([mw]+ e)
            writer.writerow([])

    stats["total"] = len(data["isbn_info"].keys())
    print(stats)

main()