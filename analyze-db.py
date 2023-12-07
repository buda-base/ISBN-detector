import csv
import yaml
import re

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
		isbn = isbn[:isbn.lfind('(')]
	return normalize_isbn(isbn)

def get_mw_infos():
    res = {}
    with open('mw-isbn.csv', newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            mw = row[0]
            orig_isbn_str = row[1]
            orig_isbns = re.split(',|;', orig_isbn_str)
            normalized_isbns = []
            for orig_isbn in orig_isbns:
            	normalized_isbns.append(normalize_from_db(orig_isbn))
            res[mw] = normalized_isbns
    return res

def get_w_to_mw():
    res = {}
    with open('mw-w-ig-vn.csv', newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
        	res[row[1]] = row[0]
    return res

def analyze_w(w, mw, existing_isbns, data, stats):
	pass

def main():
	db = None
	with open("db.yml", 'r') as stream:
        db = yaml.load(stream, Loader=yaml_loader)
    from_db = get_mw_infos()
    w_to_mw = get_w_to_mw()
    stats = {
        "total": 0,
    	"same_as_db": 0,
    	"different_from_db": 0,
    	"not_in_db": 0,
    	"db_not_found": 0
    }
    data = {
    	"new": {},
    	"check_different": {},
    	"same_isbn": {}
    }
    for w in tqdm(db):
    	w_dbinfo = db[w]
    	mw = w_to_mw[w]
    	existing_isbns = []
    	if mw in from_db:
    		existing_isbns = from_db[mw]
    	analyze_w(w, mw, existing_isbns, data, stats)
    print(stats)